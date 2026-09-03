# app/agent/guardrails.py
# ---------------------------------------------------------------------------
# Deterministic pre-checks that run BEFORE Gemini is invoked.
# These handle situations that must NEVER be left to AI judgment:
#   - Discount cap enforcement  (merchant rule — hard legal boundary)
#   - Out-of-stock item gate    (inventory truth — system of record)
#   - Graceful failure pivots   (unstocked genres, out-of-context queries)
#   - Budget curator            (deterministic bin-packing, not language generation)
#
# Each function returns None if the guardrail does not apply, or a full
# AgentResult dict if it fires and should short-circuit the agentic loop.
# ---------------------------------------------------------------------------
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.config import MAX_DISCOUNT_PERCENT
from app.models import Product
from app.services.audit_service import log_ai_action
from app.agent.catalog_data import (
    BOOK_HIGHLIGHTS,
    EMOTIONAL_PROBLEM_MAP,
    OUT_OF_CONTEXT_TOPICS,
    OUT_OF_STOCK_ITEM_NAME,
    OUT_OF_STOCK_REPLY,
    UNSTOCKED_GENRES,
    generate_book_pitch,
    get_book_30_50_word_detail,
)
from app.agent.tools import (
    analyze_and_bundle,
    cart_add,
    cart_remove,
    find_product,
    get_cart_summary,
    is_in_cart,
    search_catalog,
)


logger = logging.getLogger(__name__)

AgentResult = dict[str, Any]  # {reply, action_type, widget, cart, suggested_actions}

# Affirmative follow-up terms
_AFFIRMATIVE_TERMS = [
    "yes", "sure", "add them", "add it", "do it", "ok", "okay",
    "add all", "add both", "please add", "add bundle", "add recommended",
    "yep", "yeah",
]


def _build_actions(cart: list[dict[str, Any]], extra: list[str] | None = None) -> list[str]:
    actions: list[str] = list(extra or [])
    # Filter out add-to-cart chips for items already in cart
    filtered = []
    for act in actions:
        if "add " in act.lower() and " to cart" in act.lower():
            title = act.lower().replace("add ", "").replace(" to cart", "").strip()
            if not is_in_cart(cart, title):
                filtered.append(act)
        else:
            filtered.append(act)
    if cart and "Proceed to Checkout" not in filtered:
        filtered.append("Proceed to Checkout")
    return filtered


# ---------------------------------------------------------------------------
# Guardrail 0: Conversational affirmation follow-up (yes/sure/ok)
# ---------------------------------------------------------------------------

def check_affirmation(
    db: Session,
    message: str,
    lower_msg: str,
    conversation_history: list[dict[str, str]],
    cart: list[dict[str, Any]],
    has_remove_intent: bool,
    has_swap_intent: bool,
) -> AgentResult | None:
    """
    If the user says 'yes', 'sure', 'add them', etc., find the books
    mentioned in the last assistant message and add them to the cart.
    This runs deterministically without needing a Gemini call.
    """
    is_affirmative = any(
        re.search(rf"(?<!\w){re.escape(term)}(?!\w)", lower_msg)
        for term in _AFFIRMATIVE_TERMS
    )
    if not is_affirmative or has_remove_intent or has_swap_intent:
        return None

    last_assistant = ""
    for turn in reversed(conversation_history or []):
        if turn.get("role") in ("assistant", "model") and turn.get("content"):
            last_assistant = turn["content"]
            break

    if not last_assistant:
        return None

    # Extract **Book Title** patterns from the last assistant message
    bold_titles = re.findall(r'\*\*([^*]+)\*\*', last_assistant)
    _ignored = {
        "budget curator", "5-book discovery pitch", "total bundle price:",
        "recommended companion read:", "about ",
    }

    added_prods = []
    for bt in bold_titles:
        clean = bt.strip()
        if any(ign in clean.lower() for ign in _ignored):
            continue
        if clean.startswith("INR") or clean.startswith("₹") or clean.isdigit():
            continue
        p = (
            find_product(db, clean)
            or db.query(Product).filter(Product.name.ilike(f"%{clean}%")).first()
        )
        if p and p not in added_prods and not is_in_cart(cart, p.name):
            added_prods.append(p)

    if not added_prods:
        return None

    # "Yes" after a list that explicitly asks the buyer to choose one is not
    # clear consent to add every title. Keep the choice with the buyer.
    short_yes = lower_msg.strip() in {"yes", "sure", "ok", "okay", "yep", "yeah"}
    if len(added_prods) > 1 and short_yes and any(
        phrase in last_assistant.lower() for phrase in ("add one", "add either", "which of these")
    ):
        return _result(
            reply="I found a few good options. Which title should I add, or say **add all** if you want the full set?",
            cart=cart,
            extra_chips=[f"Add {p.name} to Cart" for p in added_prods],
        )

    offered_match = re.search(r"\b(\d+(?:\.\d+)?)\s*%\s*(?:discount|off)\b", last_assistant.lower())
    offered_discount = min(float(offered_match.group(1)), MAX_DISCOUNT_PERCENT) if offered_match else 0.0

    for p in added_prods:
        cart = cart_add(cart, p, discount_pct=offered_discount)
        log_ai_action(
            db=db,
            action_type="ITEM_ADDED_TO_CART",
            ai_reasoning=(
                f"AFFIRMATION FOLLOW-UP: Added '{p.name}' after user said '{message}'"
                f" with the previously offered {offered_discount:.0f}% discount."
            ),
            amount_involved=round(p.price * (1 - offered_discount / 100), 2),
        )

    names = [", ".join(f"**{p.name}**" for p in added_prods)]
    discount_text = f" with the promised {offered_discount:.0f}% discount" if offered_discount else ""
    comp_text, comp_chips = get_companion_recommendations(db, cart, reference_genre=added_prods[-1].genre if added_prods else "", count=2)
    comp_block = ""
    if comp_text:
        comp_block = (
            f"\n\n🎁 **Special Companion Offers (2 Related Books):**\n\n"
            f"{comp_text}\n\n"
            "Would you like me to add either to your cart with a special 10% bundle discount?"
        )
    reply = f"I've added {names[0]} to your cart{discount_text}.{comp_block}"
    return _result(reply=reply, cart=cart, action_type="CART_UPDATED", extra_chips=comp_chips)


# ---------------------------------------------------------------------------
# Pre-Intercept 1: Cart summary / total query
# ---------------------------------------------------------------------------

def check_cart_summary_intent(
    lower_msg: str,
    cart: list[dict[str, Any]],
    has_buy_intent: bool,
    has_remove_intent: bool,
    has_swap_intent: bool,
) -> AgentResult | None:
    if has_buy_intent or has_remove_intent or has_swap_intent:
        return None

    is_cart_summary = any(k in lower_msg for k in [
        "cart total", "total cart", "cart sum", "cart amount", "cart value",
        "total in my cart", "total price", "how much is my cart", "what is my cart total",
        "what's my cart total", "what is the cart total", "how much does my cart cost",
        "view cart", "show cart", "cart summary", "total in cart", "my cart total", "cart status"
    ])

    if not is_cart_summary:
        return None

    summary = get_cart_summary(cart)
    if summary["empty"]:
        reply = "Your shopping cart is currently empty! Ask me for book recommendations to add items to your cart."
        return _result(reply=reply, cart=cart, action_type="CART_EMPTY")

    detail_lines = []
    for item in summary["items"]:
        disc_str = f" ({item['discount_percentage']:.0f}% OFF)" if item["discount_percentage"] > 0 else ""
        qty_str = f" (x{item['quantity']})" if item["quantity"] > 1 else ""
        detail_lines.append(f"• **{item['name']}**{qty_str} - INR {item['subtotal']:.2f}{disc_str}")

    savings_str = f"\n\n**Total Savings:** INR {summary['savings']:.2f}" if summary["savings"] > 0 else ""

    reply = (
        f"Your current cart total is **INR {summary['final_total']:.2f}** for **{summary['item_count']} item(s)**:\n\n"
        + "\n".join(detail_lines)
        + f"{savings_str}\n\n"
        "Would you like to proceed to checkout or add more books to your cart?"
    )
    return _result(reply=reply, cart=cart, action_type="CART_SUMMARY", extra_chips=["Proceed to Checkout"])


# ---------------------------------------------------------------------------
# Pre-Intercept 2: Swap intent (replace X with Y)
# ---------------------------------------------------------------------------

def check_swap_intent(
    db: Session,
    lower_msg: str,
    cart: list[dict[str, Any]],
    has_swap_intent: bool,
) -> AgentResult | None:
    if not has_swap_intent:
        return None

    remove_target = ""
    add_target = ""
    for delim in ["with", "for", "to", "and add", "and buy"]:
        if delim in lower_msg:
            parts = lower_msg.split(delim, 1)
            remove_target = parts[0]
            add_target = parts[1]
            break
    if not remove_target:
        remove_target = lower_msg
        add_target = lower_msg

    cart, removed = cart_remove(cart, remove_target)
    if removed:
        log_ai_action(
            db=db,
            action_type="ITEM_REMOVED_FROM_CART",
            ai_reasoning=f"DETERMINISTIC INTENT INTERCEPT: Removed {removed} during swap.",
            amount_involved=0.0,
        )

    target = find_product(db, add_target)
    if target:
        cart = cart_add(cart, target, discount_pct=10.0)
        log_ai_action(
            db=db,
            action_type="ITEM_ADDED_TO_CART",
            ai_reasoning=f"DETERMINISTIC INTENT INTERCEPT: Added '{target.name}' during swap.",
            amount_involved=round(target.price * 0.9, 2),
        )

    if removed and target:
        bundles = analyze_and_bundle(db, cart, theme=target.genre)
        companion_name = bundles[0]["name"] if bundles else None
        extra_chip = [f"Add {companion_name} to Cart"] if companion_name else []
        reply = (
            f"I've removed **{', '.join(removed)}** and added **{target.name}** to your cart with a 10% discount!\n\n"
            f"**About {target.name}:** {target.description}"
        )
        return _result(reply=reply, cart=cart, action_type="CART_UPDATED", extra_chips=extra_chip)
    elif removed:
        reply = f"I've removed **{', '.join(removed)}** from your cart."
        return _result(reply=reply, cart=cart, action_type="CART_UPDATED")
    elif target:
        reply = f"I've added **{target.name}** to your cart with a 10% discount!"
        return _result(reply=reply, cart=cart, action_type="CART_UPDATED")

    return None


def get_companion_recommendations(
    db: Session,
    cart: list[dict[str, Any]],
    reference_genre: str = "",
    count: int = 2,
) -> tuple[str, list[str]]:
    """
    Finds `count` related in-stock books that are NOT present in the cart,
    and formats them with unique, interesting, witty pitches.
    Returns (formatted_markdown_lines, extra_chips).
    """
    query = db.query(Product).filter(Product.stock_quantity > 0)
    all_in_stock = query.all()

    candidates: list[Product] = []

    # Prioritize same genre if available
    if reference_genre:
        for p in all_in_stock:
            if p.genre and reference_genre.lower() in p.genre.lower():
                if not is_in_cart(cart, p.name) and p not in candidates:
                    candidates.append(p)

    # Add other distinct in-stock books not in cart
    other_books = [p for p in all_in_stock if not is_in_cart(cart, p.name) and p not in candidates]
    import random
    random.shuffle(other_books)
    candidates.extend(other_books)

    selected = candidates[:count]
    if not selected:
        return "", []

    book_lines = []
    extra_chips = []
    for b in selected:
        pitch = generate_book_pitch(b.name, b.genre, b.author, b.description)
        author_str = f" by {b.author}" if b.author else ""
        book_lines.append(
            f"- **{b.name}**{author_str} — INR {b.price:.2f} ({b.genre} · {b.format})\n"
            f"  *{pitch}*"
        )
        extra_chips.append(f"Add {b.name} to Cart")
        if len(extra_chips) < 4:
            extra_chips.append(f"Tell me more about {b.name}")

    formatted_text = "\n\n".join(book_lines)
    return formatted_text, extra_chips


# ---------------------------------------------------------------------------
# Pre-Intercept 3: Direct Remove intent
# ---------------------------------------------------------------------------

def check_direct_remove_intent(
    db: Session,
    lower_msg: str,
    cart: list[dict[str, Any]],
    has_remove_intent: bool,
    has_swap_intent: bool,
) -> AgentResult | None:
    if not has_remove_intent or has_swap_intent:
        return None

    if "only want" in lower_msg:
        keep_book_name = "atomic" if "atomic" in lower_msg else ("power" if "power" in lower_msg else "")
        new_cart = []
        removed_titles = []
        for item in cart:
            if keep_book_name and keep_book_name in item["name"].lower():
                new_cart.append(item)
            else:
                removed_titles.append(item["name"])
        cart = new_cart
        log_ai_action(
            db=db,
            action_type="ITEM_REMOVED_FROM_CART",
            ai_reasoning=f"DETERMINISTIC INTENT INTERCEPT: Kept only requested book. Removed {removed_titles}.",
            amount_involved=0.0,
        )
        comp_text, comp_chips = get_companion_recommendations(db, cart, count=2)
        comp_block = f"\n\n✨ **Here are 2 great companion reads you might love instead:**\n\n{comp_text}\n\nWould you like me to add either to your cart?" if comp_text else ""
        reply = f"Understood! I've updated your cart to keep only your requested book.{comp_block}"
        return _result(reply=reply, cart=cart, action_type="CART_UPDATED", extra_chips=comp_chips)

    cart, removed = cart_remove(cart, lower_msg, db=db)
    if removed:
        removed_str = ", ".join(f"**{r}**" for r in removed)
        empty_note = " Your cart is now empty." if len(cart) == 0 else f" ({len(cart)} item(s) remaining in your cart)."

        comp_text, comp_chips = get_companion_recommendations(db, cart, count=2)
        comp_block = ""
        if comp_text:
            comp_block = (
                f"\n\n✨ **Here are 2 great companion reads you might love instead:**\n\n"
                f"{comp_text}\n\n"
                "Would you like me to add either to your cart?"
            )

        reply = f"Done! I've removed {removed_str} from your cart.{empty_note}{comp_block}"
        return _result(reply=reply, cart=cart, action_type="CART_UPDATED", extra_chips=comp_chips)
    else:
        reply = "I couldn't find that item in your current cart."
        return _result(reply=reply, cart=cart)


# ---------------------------------------------------------------------------
# Pre-Intercept 4: Direct Add intent
# ---------------------------------------------------------------------------

def check_direct_add_intent(
    db: Session,
    message: str,
    lower_msg: str,
    cart: list[dict[str, Any]],
    conversation_history: list[dict[str, str]] | None,
    has_buy_intent: bool,
    has_remove_intent: bool,
    has_swap_intent: bool,
    has_discount_intent: bool,
) -> AgentResult | None:
    if not has_buy_intent or has_remove_intent or has_swap_intent or has_discount_intent:
        return None

    target = find_product(db, lower_msg)
    if not target:
        return None

    # A button such as "Add Atomic Habits to Cart" can follow an explicit
    # offer. Carry that offer forward only when the preceding assistant turn
    # names the same product and a bounded percentage; never invent a discount.
    offered_discount = 0.0
    for turn in reversed(conversation_history or []):
        if turn.get("role") not in ("assistant", "model"):
            continue
        previous_reply = turn.get("content", "").lower()
        if target.name.lower() in previous_reply:
            offered_match = re.search(r"\b(\d+(?:\.\d+)?)\s*%\s*(?:discount|off)\b", previous_reply)
            if offered_match:
                offered_discount = min(float(offered_match.group(1)), MAX_DISCOUNT_PERCENT)
        break

    already_in_cart = any(
        i.get("product_id") == target.id or i.get("name", "").lower() == target.name.lower()
        for i in cart
    )
    multi_qty = bool(re.search(r'\b([2-9]|\d{2,})\s*(?:copies|copy|books)?\b', lower_msg) or "another" in lower_msg)

    cart = cart_add(
        cart,
        target,
        discount_pct=offered_discount,
        allow_increment=(not already_in_cart or multi_qty),
    )
    log_ai_action(
        db=db,
        action_type="ITEM_ADDED_TO_CART",
        ai_reasoning=(
            f"DETERMINISTIC INTENT INTERCEPT: Added requested book '{target.name}' "
            f"with the previously offered {offered_discount:.0f}% discount."
            if offered_discount
            else f"DETERMINISTIC INTENT INTERCEPT: Added requested book '{target.name}' at catalog price."
        ),
        amount_involved=round(target.price * (1 - offered_discount / 100), 2),
    )

    comp_text, comp_chips = get_companion_recommendations(db, cart, reference_genre=target.genre, count=2)
    comp_block = ""
    if comp_text:
        comp_block = (
            f"\n\n🎁 **Special Companion Offers (2 Related Books):**\n\n"
            f"{comp_text}\n\n"
            "Would you like me to add either of these to your cart with a special 10% bundle discount?"
        )

    reply = (
        f"I've added **{target.name}** to your cart"
        + (f" with the promised **{offered_discount:.0f}% discount**" if offered_discount else "")
        + "!\n\n"
        f"**Why {target.name} is a Great Read:** {target.description}{comp_block}"
    )
    return _result(reply=reply, cart=cart, action_type="CART_UPDATED", extra_chips=comp_chips)



def _result(
    reply: str,
    cart: list[dict[str, Any]],
    action_type: str | None = None,
    widget: dict | None = None,
    extra_chips: list[str] | None = None,
) -> AgentResult:
    return {
        "reply": reply,
        "action_type": action_type,
        "widget": widget,
        "cart": cart,
        "suggested_actions": _build_actions(cart, extra_chips),
    }


# ---------------------------------------------------------------------------
# Guardrail 1: Graceful failure for the out-of-stock special item
# ---------------------------------------------------------------------------

def check_out_of_stock_item(
    db: Session,
    lower_msg: str,
    cart: list[dict[str, Any]],
) -> AgentResult | None:
    """Intercepts requests for the known-OOS Machiavelli 1st edition."""
    if not any(k in lower_msg for k in ["prince", "machiavelli", "1st edition"]):
        return None

    item = db.query(Product).filter(Product.name.ilike("%Machiavelli%")).first()
    stock = item.stock_quantity if item else 0

    log_ai_action(
        db=db,
        action_type="STOCK_CHECK_FAILED",
        ai_reasoning=(
            f"STOCK FAILURE GATING: User requested '{OUT_OF_STOCK_ITEM_NAME}'. "
            f"Stock = {stock}. Graceful pivot to Atomic Habits."
        ),
        amount_involved=0.0,
    )
    return _result(
        reply=OUT_OF_STOCK_REPLY,
        cart=cart,
        action_type="GRACEFUL_FAILURE",
        extra_chips=["Add Atomic Habits to Cart"],
    )


# ---------------------------------------------------------------------------
# Guardrail 2: Unstocked genre graceful pivot
# ---------------------------------------------------------------------------

def check_unstocked_genre(
    db: Session,
    lower_msg: str,
    cart: list[dict[str, Any]],
    has_buy_intent: bool,
    has_remove_intent: bool,
) -> AgentResult | None:
    if has_buy_intent or has_remove_intent:
        return None
    matched = next((g for g in UNSTOCKED_GENRES if g in lower_msg), None)
    if not matched:
        return None

    pivot = db.query(Product).filter(
        Product.name.in_(["Atomic Habits", "The 48 Laws of Power"])
    ).all() or db.query(Product).filter(Product.stock_quantity > 0).limit(2).all()

    log_ai_action(
        db=db,
        action_type="STOCK_CHECK_FAILED",
        ai_reasoning=f"GRACEFUL FAILURE PIVOT: Genre '{matched}' not stocked. Pivoted to bestsellers.",
        amount_involved=0.0,
    )

    lines = [f"- **{b.name}** by {b.author} (INR {b.price:.2f}) — {b.genre}" for b in pivot]
    reply = (
        f"I apologise — we are currently out of stock for **{matched.title()}** books. "
        "However, here are 2 top-rated bestsellers from our active collection:\n\n"
        + "\n\n".join(lines)
        + "\n\nWould you like me to add either to your cart with a special discount?"
    )
    return _result(
        reply=reply,
        cart=cart,
        action_type="GRACEFUL_FAILURE",
        extra_chips=[f"Add {b.name} to Cart" for b in pivot],
    )


# ---------------------------------------------------------------------------
# Guardrail 3: Budget curation (without an LLM dependency)
# ---------------------------------------------------------------------------

def check_budget_request(
    db: Session,
    lower_msg: str,
    cart: list[dict[str, Any]],
) -> AgentResult | None:
    match = re.search(
        r"\b(?:under|within|below|max|budget(?: of)?|less than)\s+(?:inr|rs\.?|₹)?\s*(\d+(?:\.\d{1,2})?)",
        lower_msg,
    )
    if not match:
        return None

    budget = float(match.group(1))
    products = db.query(Product).filter(Product.stock_quantity > 0).order_by(Product.price.asc()).all()
    bundle: list[Product] = []
    running = 0.0
    for p in products:
        if running + p.price <= budget:
            bundle.append(p)
            running += p.price
        if len(bundle) >= 3:
            break

    if not bundle:
        cheapest_price = db.query(func.min(Product.price)).filter(Product.stock_quantity > 0).scalar()
        if cheapest_price is not None:
            return _result(
                reply=(
                    f"I couldn't find an in-stock book within **INR {budget:.2f}**. "
                    f"Our least expensive available title is **INR {cheapest_price:.2f}**."
                ),
                cart=cart,
            )
        return _result(reply="Our catalog is temporarily unavailable. Please try again shortly.", cart=cart)

    lines = [
        f"- **{b.name}** by {b.author} ({b.format}) — INR {b.price:.2f}\n  *{generate_book_pitch(b.name, b.genre, b.author, b.description)}*"
        for b in bundle
    ]
    reply = (
        f"As your **Budget Curator**, I've selected a custom bundle fitting under "
        f"**INR {budget:.2f}**:\n\n"
        + "\n\n".join(lines)
        + f"\n\n**Total:** INR {running:.2f} "
        f"(INR {max(0.0, budget - running):.2f} remaining in your budget)\n\n"
        "Would you like me to add these books to your cart?"
    )
    chips = ["Add Bundle to Cart"] + [f"Add {b.name} to Cart" for b in bundle[:3]]
    return _result(reply=reply, cart=cart, extra_chips=chips)


# ---------------------------------------------------------------------------
# Guardrail 3a2: Book details and deep-dive inquiry
# ---------------------------------------------------------------------------

def check_book_details_inquiry(
    db: Session,
    lower_msg: str,
    cart: list[dict[str, Any]],
) -> AgentResult | None:
    """
    Handles requests when a user wants more information, a synopsis,
    key takeaways, or 'tell me more about' a specific title.
    """
    # If query is off-topic or unstocked genre, let respective pivots handle it
    if any(topic in lower_msg for topic in OUT_OF_CONTEXT_TOPICS):
        return None
    if any(genre in lower_msg for genre in UNSTOCKED_GENRES):
        return None

    inquiry_patterns = [
        r"(?:tell me more about|more details (?:on|about)|more info(?:rmation)? (?:on|about)|what is|what's|summary of|synopsis of|why should i read|tell me about)\s+['\"]?([^'\"?.!]+)['\"]?",
    ]

    candidate_query = None
    for pattern in inquiry_patterns:
        m = re.search(pattern, lower_msg)
        if m:
            candidate_query = m.group(1).strip()
            if candidate_query in {"your store", "the store", "the bookstore", "discounts", "shipping", "books", "yourself", "this", "it"}:
                return None
            break

    if not candidate_query:
        return None

    prod = find_product(db, candidate_query)
    if not prod:
        return None

    # Verify that the candidate query actually refers to this product's title or author
    clean_cand = candidate_query.lower()
    cand_words = [w for w in clean_cand.split() if len(w) >= 3 and w not in {"the", "and", "for", "book", "about"}]
    name_lower = prod.name.lower()
    author_lower = prod.author.lower()
    if not (clean_cand in name_lower or clean_cand in author_lower or any(w in name_lower or w in author_lower for w in cand_words)):
        return None

    detail_30_50 = get_book_30_50_word_detail(prod)
    pitch = generate_book_pitch(prod.name, prod.genre, prod.author, prod.description)

    reply_parts = [
        f"### 📖 **{prod.name}** by {prod.author}",
        f"**Format:** {prod.format} · **Genre:** {prod.genre} · **Price:** INR {prod.price:.2f} *(In Stock: {prod.stock_quantity} copies)*",
        f"{detail_30_50}",
        f"*{pitch}*",
        f"Would you like me to add **{prod.name}** to your cart?",
    ]

    reply = "\n\n".join(reply_parts)
    chips = [f"Add {prod.name} to Cart"]
    if is_in_cart(cart, prod.name):
        chips = ["Proceed to Checkout"]
    return _result(reply=reply, cart=cart, extra_chips=chips)


# ---------------------------------------------------------------------------
# Guardrail 3b: Catalog discovery without an LLM dependency
# ---------------------------------------------------------------------------

def check_catalog_discovery(
    db: Session,
    lower_msg: str,
    cart: list[dict[str, Any]],
    has_buy_intent: bool,
    has_remove_intent: bool,
    has_swap_intent: bool,
    has_discount_intent: bool,
) -> AgentResult | None:
    """Answer ordinary catalog discovery deterministically from live inventory.

    Recommending stocked titles or showing an author's work with compelling pitches.
    """
    if has_buy_intent or has_remove_intent or has_swap_intent or has_discount_intent:
        return None

    discovery_words = (
        "recommend", "recommendation", "show me", "find me", "what else",
        "what books", "which books", "looking for", "suggest", "list ",
        "sci-fi", "scifi", "horror", "tech", "self-growth", "self growth",
    )
    known_product = find_product(db, lower_msg)
    if not any(term in lower_msg for term in discovery_words) and not known_product:
        return None

    requested_count = re.search(r"\b([1-5])\s+(?:good |best |book)", lower_msg)
    limit = int(requested_count.group(1)) if requested_count else 3
    generic_request = any(term in lower_msg for term in ("recommend", "suggest", "show me", "list")) and not any(
        term in lower_msg for term in ("stephen", "king", "horror", "tech", "sci-fi", "scifi", "self-growth", "growth")
    )
    products = search_catalog(
        db,
        query=lower_msg,
        limit=limit,
        fallback_to_catalog=generic_request,
    )
    if not products:
        return _result(
            reply="I couldn't find an in-stock catalog match for that. Try a title, author, or genre such as Horror, Tech, Sci-Fi, or Self-Growth.",
            cart=cart,
        )

    lines = [
        f"- **{product['name']}** by {product['author']} — INR {product['price']:.2f} ({product['genre']} · {product['format']})\n  *{generate_book_pitch(product['name'], product['genre'], product['author'], product['description'])}*"
        for product in products
    ]
    reply = (
        "Here are in-stock picks from our live catalog:\n\n"
        + "\n\n".join(lines)
        + "\n\nWould you like me to add one to your cart, or ask me for more details on any title?"
    )
    chips = [f"Add {p['name']} to Cart" for p in products[:2]] + [f"Tell me more about {products[0]['name']}"]
    return _result(
        reply=reply,
        cart=cart,
        extra_chips=chips,
    )


# ---------------------------------------------------------------------------
# Guardrail 4: Empathetic problem solving
# ---------------------------------------------------------------------------

def check_emotional_context(
    db: Session,
    lower_msg: str,
    cart: list[dict[str, Any]],
    has_buy_intent: bool,
    has_remove_intent: bool,
    has_swap_intent: bool,
) -> AgentResult | None:
    if has_buy_intent or has_remove_intent or has_swap_intent:
        return None
    matched = next((k for k in EMOTIONAL_PROBLEM_MAP if k in lower_msg), None)
    if not matched:
        return None

    genre_label, opener, hints = EMOTIONAL_PROBLEM_MAP[matched]
    books: list[Product] = []
    for hint in hints:
        p = db.query(Product).filter(Product.name.ilike(f"%{hint}%")).first()
        if p and p not in books:
            books.append(p)
    if not books:
        books = db.query(Product).filter(Product.stock_quantity > 0).limit(3).all()

    lines = [
        f"- **{b.name}** by {b.author} — INR {b.price:.2f} ({b.genre} · {b.format})\n  *{generate_book_pitch(b.name, b.genre, b.author, b.description)}*"
        for b in books
    ]
    reply = (
        f"{opener}\n\n"
        f"Here are {len(books)} top recommendations in **{genre_label}**:\n\n"
        + "\n\n".join(lines)
        + "\n\nWhich of these would you like to explore or add to your cart? You can also ask for more details on any book!"
    )
    chips = [f"Add {b.name} to Cart" for b in books[:2]] + [f"Tell me more about {books[0].name}"]
    return _result(reply=reply, cart=cart, extra_chips=chips)


# ---------------------------------------------------------------------------
# Guardrail 5: Out-of-context polite pivot
# ---------------------------------------------------------------------------

def check_out_of_context(
    db: Session,
    lower_msg: str,
    cart: list[dict[str, Any]],
    has_buy_intent: bool,
    has_remove_intent: bool,
    found_product: bool,
) -> AgentResult | None:
    if has_buy_intent or has_remove_intent or found_product:
        return None

    matched_topic = next((t for t in OUT_OF_CONTEXT_TOPICS if t in lower_msg), None)
    general_oos = any(k in lower_msg for k in ["what is", "how to", "who is", "tell me about climate"])
    if not matched_topic and not general_oos:
        return None

    topic_label, hints = OUT_OF_CONTEXT_TOPICS.get(
        matched_topic, ("related topics", ["Atomic Habits", "Deep Work", "Dune"])
    )
    books: list[Product] = []
    for hint in hints:
        p = db.query(Product).filter(Product.name.ilike(f"%{hint}%")).first()
        if p and p not in books:
            books.append(p)
    if not books:
        books = db.query(Product).filter(Product.stock_quantity > 0).limit(3).all()

    lines = [f"- **{b.name}** by {b.author} (INR {b.price:.2f}) — {b.genre}" for b in books]
    reply = (
        f"I specialise strictly in books! Here are great reads from our catalog related to **{topic_label}**:\n\n"
        + "\n\n".join(lines)
        + "\n\nLet me know if you'd like to add any of these to your cart!"
    )
    chips = [f"Add {b.name} to Cart" for b in books]
    return _result(reply=reply, cart=cart, extra_chips=chips)


# ---------------------------------------------------------------------------
# Guardrail 6: Discount cap enforcement (hard monetary gate)
# ---------------------------------------------------------------------------

def enforce_discount_cap(
    db: Session,
    lower_msg: str,
    cart: list[dict[str, Any]],
    has_remove_intent: bool,
    has_swap_intent: bool,
) -> AgentResult | None:
    """
    Handles ALL explicit percentage discount requests deterministically.
    - If requested% > MAX_DISCOUNT_PERCENT: block, log, apply cap, return reply.
    - If requested% <= MAX_DISCOUNT_PERCENT AND a product is found: apply it, log, return reply.
    - If no percentage is specified: return None (let Gemini handle vague discount chat).
    This is a HARD gate — Gemini must never override the cap enforcement.
    """
    is_discount_query = any(
        k in lower_msg for k in ["discount", "deal", "cheaper", "lower price", "price is high", "off"]
    ) or bool(re.search(r'(\d+)\s*(?:%|percent)', lower_msg))

    if not is_discount_query or has_remove_intent or has_swap_intent:
        return None

    pct_match = re.search(r'(\d+)\s*(?:%|percent)', lower_msg)
    if not pct_match:
        # Vague discount request (no percentage) — ask which book / which % they want
        # Try to identify a specific book first
        from app.agent.tools import find_product as _find_product
        target = _find_product(db, lower_msg)
        if target:
            return _result(
                reply=f"I'd be happy to help with a discount on **{target.name}**! What percentage discount are you looking for? (Maximum allowed: {MAX_DISCOUNT_PERCENT:.0f}%)",
                cart=cart,
            )
        return _result(
            reply=f"Which book would you like a discount on? Please specify the book title and desired percentage (up to {MAX_DISCOUNT_PERCENT:.0f}% maximum).",
            cart=cart,
        )

    requested = float(pct_match.group(1))

    # Strip percentage expression before product lookup (% is not a word char, so use direct sub)
    query_for_lookup = re.sub(r'\d+\s*%|\d+\s*percent', '', lower_msg).strip()
    from app.agent.tools import find_product as _find_product
    target = _find_product(db, query_for_lookup)

    if not target and cart:
        # Check if query matches any book already in the user's cart
        for item in cart:
            c_name = item.get("name", "").lower()
            if c_name in query_for_lookup or any(w in query_for_lookup for w in c_name.split() if len(w) >= 3):
                target = _find_product(db, item["name"])
                if target:
                    break
        if not target and len(cart) == 1:
            target = _find_product(db, cart[0]["name"])

    if not target:
        return _result(
            reply="Which book would you like a discount on? Please specify the title from our catalog!",
            cart=cart,
        )

    already_in_cart = any(
        i.get("product_id") == target.id or i.get("name", "").lower() == target.name.lower()
        for i in cart
    )

    if requested > MAX_DISCOUNT_PERCENT:
        # Hard cap violation
        log_ai_action(
            db=db,
            action_type="CHECKOUT_BLOCKED",
            ai_reasoning=(
                f"HARD GATING ENFORCED: User requested {requested:.0f}% on '{target.name}'. "
                f"Merchant cap is {MAX_DISCOUNT_PERCENT}%. Capped and applied."
            ),
            amount_involved=0.0,
            log_metadata={
                "status": "Blocked",
                "purchased_items": [target.name],
                "failure_reason": f"Discount {requested:.0f}% > cap {MAX_DISCOUNT_PERCENT}%.",
            },
        )
        cart = cart_add(cart, target, discount_pct=MAX_DISCOUNT_PERCENT, allow_increment=False)
        log_ai_action(
            db=db,
            action_type="ITEM_ADDED_TO_CART",
            ai_reasoning=f"Applied capped {MAX_DISCOUNT_PERCENT}% discount on '{target.name}'.",
            amount_involved=round(target.price * (1 - MAX_DISCOUNT_PERCENT / 100), 2),
        )
        action_verb = "updated" if already_in_cart else "added"
        reply = (
            f"Our merchant system caps maximum discounts at **{MAX_DISCOUNT_PERCENT:.0f}%**, "
            f"so I cannot apply {requested:.0f}%. I've {action_verb} **{target.name}** at the "
            f"maximum **{MAX_DISCOUNT_PERCENT:.0f}% discount** instead!\n\n"
            f"**About {target.name}:** {target.description}"
        )
    else:
        # Valid within-cap discount — apply directly without duplicate quantity increment
        cart = cart_add(cart, target, discount_pct=requested, allow_increment=False)
        log_ai_action(
            db=db,
            action_type="ITEM_ADDED_TO_CART",
            ai_reasoning=f"Applied user-requested {requested:.0f}% discount on '{target.name}'.",
            amount_involved=round(target.price * (1 - requested / 100), 2),
        )
        final_price = round(target.price * (1 - requested / 100), 2)
        action_verb = "applied your discount to" if already_in_cart else "applied your discount and added"
        reply = (
            f"Great news! I've {action_verb} **{target.name}** at the **{requested:.0f}% discount** "
            f"(**INR {final_price:.2f}**)!\n\n"
            f"**About {target.name}:** {target.description}"
        )

    return _result(reply=reply, cart=cart, action_type="CART_UPDATED")

