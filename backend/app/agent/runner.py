# app/agent/runner.py
# ---------------------------------------------------------------------------
# The Agentic Loop — the heart of the new architecture.
#
# Flow:
#   1. Run deterministic guardrails (discount cap, stock, pivots)
#      If a guardrail fires → return immediately (no LLM needed)
#   2. Build system prompt with live cart state + catalog context
#   3. Call Gemini with conversation history + BOOKSTORE_TOOLS (Function Calling)
#   4. If Gemini returns a function_call → dispatch to the matching Python tool
#   5. Feed tool result back to Gemini for a natural language reply
#   6. Return (reply, action_type, widget_data, updated_cart, suggested_actions)
# ---------------------------------------------------------------------------
import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.config import MAX_DISCOUNT_PERCENT, GROQ_MODEL
from app.models import Product
from app.services.audit_service import log_ai_action
from app.agent.client import get_groq_client
from app.agent.declarations import BOOKSTORE_TOOLS
from app.agent.tools import (
    analyze_and_bundle,
    cart_add,
    cart_remove,
    find_product,
    get_cart_summary,
    initiate_checkout,
    is_in_cart,
    reconcile_cart,
    search_catalog,
)
from app.agent.catalog_data import BOOK_HIGHLIGHTS, generate_book_pitch
from app.agent.guardrails import (
    check_affirmation,
    check_book_details_inquiry,
    check_budget_request,
    check_catalog_discovery,
    check_cart_summary_intent,
    check_direct_add_intent,
    check_direct_remove_intent,
    check_emotional_context,
    check_out_of_stock_item,
    check_out_of_context,
    check_swap_intent,
    check_unstocked_genre,
    enforce_discount_cap,
)

logger = logging.getLogger(__name__)

AgentResult = tuple[str, str | None, dict | None, list[dict[str, Any]], list[str]]


# ---------------------------------------------------------------------------
# Intent flags helper
# ---------------------------------------------------------------------------

def _intent(lower_msg: str) -> dict[str, bool]:
    is_discount = any(
        k in lower_msg for k in ["discount", "deal", "cheaper", "lower price", "price is high", "off"]
    ) or bool(re.search(r'(\d+)\s*(?:%|percent)', lower_msg))
    return {
        "buy": (not is_discount) and any(
            k in lower_msg for k in [
                "buy", "add", "purchase", "get", "order", "want to buy",
                "put it in", "put this in", "put that in", "i'll take", "i will take",
                "take it",
            ]
        ),
        "remove": any(
            k in lower_msg for k in [
                "remove", "delete", "only want", "dont want", "don't want",
                "take it out", "take this out", "take that out",
            ]
        ),
        "swap": any(k in lower_msg for k in ["replace", "swap", "exchange", "change", "trade"]),
        "discount": is_discount,
        "checkout": any(k in lower_msg for k in ["checkout", "pay", "buy now", "ready to order", "generate checkout", "draft checkout", "payment link"]),
    }


def _build_actions(cart: list[dict], extra: list[str] | None = None) -> list[str]:
    actions = list(extra or [])
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
# System prompt builder
# ---------------------------------------------------------------------------

def _build_system_prompt(cart: list[dict], db: Session) -> str:
    summary = get_cart_summary(cart)
    if summary["empty"]:
        cart_info = "Cart: Empty"
    else:
        items_str = "; ".join(
            f"{i['name']} (qty:{i['quantity']}, INR {i['final_price']:.2f}, disc:{i['discount_percentage']:.0f}%)"
            for i in summary["items"]
        )
        cart_info = (
            f"Cart: {items_str} | "
            f"Total: INR {summary['final_total']:.2f} | "
            f"Savings: INR {summary['savings']:.2f}"
        )

    return f"""You are Agent Bookworm, a high-converting, revenue-driven enterprise AI commerce assistant for an agentic bookstore.

REVENUE GROWTH PERSONA & BUNDLE STRATEGY:
Your primary goal is to grow the merchant's cart value. After adding an item requested by the user, immediately use the `analyze_and_bundle` tool to find complementary items. Pitch these items as a personalized bundle, and proactively offer a small (e.g., 5-10%) discount on the bundle to incentivize the upsell before they ask to checkout. Always prioritize items with high stock_quantity when making these recommendations.

CORE ARCHITECTURAL RULES (Strictly Enforce):
1. NO LLM MATH: Never calculate or quote a checkout total yourself. The server creates checkout only after the buyer explicitly asks to checkout, then recalculates catalog prices, quantities, stock and discounts before it creates a Razorpay order.
2. BOUNDED DISCOUNT CONSTRAINT: The maximum allowable merchant discount is {MAX_DISCOUNT_PERCENT:.0f}%. If a larger discount is requested, explain the cap; never claim to have applied a larger one.
3. HUMAN GATE FOR BULK ORDERS: If the pre-discount total exceeds INR 1,00,000, the server saves it as `PENDING_APPROVAL`. Explain that a human manager must review it before payment.
4. GRACEFUL FAILURE: If checkout creation or a tool call returns an error (for example, a payment gateway error), do NOT break character or crash. Acknowledge the temporary issue smoothly, reassure the customer, and offer to preserve their cart.
5. REAL INVENTORY ONLY: Search and recommend books strictly from the catalog via `search_catalog`, `find_product`, and `analyze_and_bundle`. Never hallucinate non-existent books.
6. TOOL EMISSION RULE: Use tools for catalog search, cart changes, cart status, and bundle discovery. Checkout is performed only by the server after an explicit buyer request.
7. EXPLAINABLE AUDIT TRAIL: Whenever you execute a cart action or checkout, you MUST provide a 1-2 sentence explanation in the ai_reasoning parameter detailing exactly why you chose that action, why you applied a specific discount, or how it benefits the merchant's revenue.

SPECIFIC SCENARIO INSTRUCTIONS:
- REVENUE UPSELL & BUNDLE DISCOVERY:
  Whenever a user adds an item to their cart, you MUST immediately call analyze_and_bundle using the semantic theme of their purchase. Proactively pitch this bundle to the user with a customized 5-10% discount to incentivize a larger cart size before they ask to checkout.

- BUDGET CURATION & EVALUATION:
  When the user mentions a budget, spending limit, or price ceiling (e.g. "I have INR 500", "books under ₹1000", "find me a bundle under ₹400"):
  1. Call `search_catalog` or `analyze_and_bundle` to discover available in-stock books with their live prices and genres.
  2. Dynamically evaluate the catalog results and curate a selection or bundle of books whose combined prices fit within the user's budget.
  3. Present the recommended books with their titles, authors, and prices. Explain why they fit the user's interests and show how the bundle respects their budget.
  4. Offer to add the curated bundle to their cart.

- SWAPS & REPLACEMENTS:
  When the user asks to swap, replace, or exchange an item (e.g. "swap X for Y", "replace X with Y", "I don't want X, give me Y instead"):
  1. Call `remove_from_cart` with identifier 'X' (and a clear `ai_reasoning`).
  2. Call `find_product` with query 'Y' to get the product ID, then call `add_to_cart` to add 'Y' (with `ai_reasoning` and any applicable discount up to {MAX_DISCOUNT_PERCENT:.0f}%).
  3. Clearly confirm the swap in your reply, describe the newly added book, and optionally suggest complementary companion reads using `analyze_and_bundle`.

- EMOTIONAL & LIFE CONTEXT (Empathetic Problem Solving):
  When the user expresses personal feelings, emotional states, life situations, or struggles (e.g. feeling sad, stressed, broke, wanting to build wealth, seeking focus, career growth):
  1. Respond with genuine empathy, warmth, and supportive encouragement.
  2. Call `search_catalog` or `analyze_and_bundle` with relevant themes, genres, or keywords (e.g. Self-Growth, Tech, Sci-Fi, productivity, mindset, habits, resilience).
  3. Thoughtfully recommend 2-3 matching books, explaining specifically how each book will help address their situation or goals.

- CART OPERATIONS & DISCOUNTS:
  - Adding to cart: Call `find_product` then `add_to_cart` with `ai_reasoning`. Immediately follow up with `analyze_and_bundle` to pitch a high-margin companion bundle.
  - Removing from cart: Call `remove_from_cart` with `ai_reasoning`.
  - Cart status/total: Call `get_cart_summary` to provide an exact breakdown of items, totals, and savings.
- Checkout: State that the secure checkout is created only after the buyer explicitly asks to checkout. Do not claim a payment order was created unless the server reports one.

UNIQUE COMPELLING & WITTY PITCH RULE FOR ALL OFFERED BOOKS:
1. NEVER USE MARKDOWN TABLES (do NOT use `| col1 | col2 |`).
2. For EVERY book you offer or recommend (including companion offers when a user adds a book to cart), you MUST write a clever, witty, and unique pitch explaining why the reader will love or benefit from it. Pitches can be funny, charming, and relatable!
3. NEVER use the words or label "💡 Pitch:" or "Pitch:". State the pitch naturally in italics right beneath the book.
4. ALWAYS format book recommendations as clean, well-spaced Markdown bullet points:
   - **Book Title** by Author Name — INR Price (Genre · Format)
     *[Your unique, funny, or insightful pitch directly in italics]*
5. Use a blank line between each book recommendation so the text is open and readable.
6. Remind the user: "Want more info on any title? Just ask 'Tell me more about [Book Name]'!"

BOOK DETAIL INQUIRIES (CRITICAL: 30-50 WORDS):
When a user asks for more information or details about a book (e.g. "Tell me more about X", "What is X about?", "Summary of X"):
1. Call `get_book_details` or `find_product` with the book name.
2. Provide a concise, engaging summary of the book mentioned in about 30 TO 50 WORDS (do not write overly long essays).
3. Include its format, genre, price, and a witty pitch.
4. Ask if they would like you to add it to their cart.

LIVE CART STATE:
{cart_info}

You have access to these tools: search_catalog, find_product, get_book_details, add_to_cart, remove_from_cart, get_cart_summary, analyze_and_bundle."""


def _clean_response_formatting(text: str) -> str:
    """
    Ensures markdown generated by the LLM renders cleanly in chat:
    1. Removes any '💡 Pitch:' or 'Pitch:' label prefix so pitches are natural.
    2. Fixes broken single-line markdown tables by splitting rows across lines.
    3. Ensures table headers have newlines before and after.
    4. Normalizes line breaks for clean readability.
    """
    if not text:
        return text

    # Remove any stray "💡 Pitch:" or "Pitch:" labels
    text = re.sub(r'[*_]?\s*💡?\s*Pitch:\s*[*_]?', '', text, flags=re.IGNORECASE)

    # Split mashed table cells e.g. "| 40 | | 2 |" -> "| 40 |\n| 2 |"
    text = re.sub(r'\|\s*\|\s*([^\n|]+)\s*\|', r'|\n| \1 |', text)
    # Split mashed table header separator e.g. "| Stock | |---|---|" -> "| Stock |\n|---|---|"
    text = re.sub(r'\|\s*\|([-:\s|]+)\|', r'|\n|\1|', text)

    return text.strip()


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------

def _dispatch_tool(
    tool_name: str,
    tool_args: dict[str, Any],
    cart: list[dict[str, Any]],
    db: Session,
    *,
    allow_add: bool,
    allow_remove: bool,
) -> tuple[Any, list[dict[str, Any]], str | None, dict | None]:
    """
    Executes the tool Gemini requested. Returns (tool_result, updated_cart, action_type, widget).
    """
    action_type = None
    widget = None

    if tool_name == "search_catalog":
        query = tool_args.get("query") or tool_args.get("theme", "")
        limit = int(tool_args.get("limit", 5))
        tool_result = search_catalog(db, query=query, limit=limit)

    elif tool_name in ("find_product", "get_book_details"):
        prod = find_product(db, tool_args.get("query", ""))
        if prod:
            lower_name = prod.name.lower()
            highlight = next((data for key, data in BOOK_HIGHLIGHTS.items() if key in lower_name), None)
            tool_result = {
                "id": prod.id,
                "name": prod.name,
                "author": prod.author,
                "genre": prod.genre,
                "format": prod.format,
                "price": prod.price,
                "max_discount": getattr(prod, "max_discount", MAX_DISCOUNT_PERCENT),
                "stock": prod.stock_quantity,
                "description": prod.description,
                "pitch": highlight["pitch"] if highlight else generate_book_pitch(prod.name, prod.genre, prod.author, prod.description),
                "key_takeaways": highlight.get("key_takeaways", []) if highlight else [],
                "why_read": highlight.get("why_read", prod.description) if highlight else prod.description,
            }
        else:
            tool_result = {"error": "Product not found in catalog."}

    elif tool_name == "add_to_cart":
        if not allow_add:
            tool_result = {"error": "Cart additions require an explicit buyer request."}
        else:
            product_id = tool_args.get("product_id")
            prod = db.query(Product).filter(Product.id == product_id).first()
            if not prod:
                tool_result = {"error": f"Product ID {product_id} not found."}
            else:
                discount = float(tool_args.get("discount_pct", 0.0))
                quantity = int(tool_args.get("quantity", 1))
                ai_reasoning = tool_args.get("ai_reasoning") or tool_args.get("reasoning", "")
                cart = cart_add(cart, prod, discount_pct=discount, quantity=quantity, ai_reasoning=ai_reasoning, db=db)
                action_type = "CART_UPDATED"
                tool_result = {
                    "success": True,
                    "added": prod.name,
                    "final_price": round(prod.price * (1 - discount / 100), 2),
                    "cart_item_count": len(cart),
                }

    elif tool_name == "remove_from_cart":
        if not allow_remove:
            tool_result = {"error": "Cart removals require an explicit buyer request."}
        else:
            identifier = tool_args.get("identifier", "")
            ai_reasoning = tool_args.get("ai_reasoning") or tool_args.get("reasoning", "")
            cart, removed = cart_remove(cart, identifier, ai_reasoning=ai_reasoning, db=db)
            if removed:
                action_type = "CART_UPDATED"
            tool_result = {
                "removed": removed,
                "cart_item_count": len(cart),
                "success": bool(removed),
            }

    elif tool_name == "get_cart_summary":
        tool_result = get_cart_summary(cart)

    elif tool_name == "analyze_and_bundle":
        theme = tool_args.get("theme", "")
        max_budget = tool_args.get("max_budget")
        if max_budget is not None:
            try:
                max_budget = float(max_budget)
            except (ValueError, TypeError):
                max_budget = None
        bundles = analyze_and_bundle(
            db,
            cart=cart,
            theme=theme,
            max_budget=max_budget,
        )
        tool_result = {
            "bundle_count": len(bundles),
            "theme": theme,
            "max_budget": max_budget,
            "recommended_bundle": [
                {
                    "id": b["id"],
                    "name": b["name"],
                    "author": b["author"],
                    "price": b["price"],
                    "description": b["description"],
                }
                for b in bundles
            ],
        }

    else:
        tool_result = {"error": f"Unknown tool: {tool_name}"}

    return tool_result, cart, action_type, widget


def _offline_catalog_fallback(
    db: Session,
    message: str,
    cart: list[dict[str, Any]],
) -> AgentResult:
    """Serve catalog-backed help when Gemini is unavailable; never call it again."""
    catalog_matches = search_catalog(db, query=message, limit=3)
    if catalog_matches:
        book_lines = "\n\n".join(
            f"- **{b['name']}** by {b['author']} (₹{b['price']:.2f}) — {b['genre']}"
            for b in catalog_matches
        )
        actions = [f"Add {b['name']} to cart" for b in catalog_matches[:2]]
        return (
            f"Here are matching books from our catalog:\n\n{book_lines}\n\nWould you like me to add any to your cart?",
            None,
            None,
            cart,
            _build_actions(cart, actions),
        )
    return (
        "Gemini is temporarily unavailable, but I can still help from the live catalog. "
        "Ask for a genre, author, budget, cart summary, or a specific title.",
        None,
        None,
        cart,
        _build_actions(cart),
    )


# ---------------------------------------------------------------------------
# Main agentic loop
# ---------------------------------------------------------------------------

def run_agent(
    db: Session,
    message: str,
    conversation_history: list[dict[str, str]],
    current_cart: list[dict[str, Any]],
) -> AgentResult:
    """
    Entry point for the agentic loop.
    Returns (reply, action_type, widget_data, updated_cart, suggested_actions).
    """
    lower_msg = message.lower().strip()
    # The browser owns display state, not pricing or inventory truth. Rebuild
    # every incoming line from the catalog before any guardrail or tool sees it.
    cart = reconcile_cart(db, current_cart)
    intent = _intent(lower_msg)

    # ------------------------------------------------------------------
    # PHASE 1: Hard deterministic guardrails & Pre-Intercepts
    # ------------------------------------------------------------------

    # 1a. Conversational affirmation (yes/sure/ok after a recommendation)
    result = check_affirmation(db, message, lower_msg, conversation_history, cart, intent["remove"], intent["swap"])
    if result:
        return result["reply"], result["action_type"], result["widget"], result["cart"], result["suggested_actions"]

    # 1b. Out-of-stock special item (Machiavelli) — graceful failure testing
    result = check_out_of_stock_item(db, lower_msg, cart)
    if result:
        return result["reply"], result["action_type"], result["widget"], result["cart"], result["suggested_actions"]

    # These common commerce actions are deterministic by design. This makes
    # short follow-ups such as "remove it", "what is my total?" and a known
    # product purchase reliable even if Gemini is rate-limited or unavailable.
    deterministic_checks = (
        lambda: enforce_discount_cap(db, lower_msg, cart, intent["remove"], intent["swap"]),
        lambda: check_book_details_inquiry(db, lower_msg, cart),
        lambda: check_cart_summary_intent(lower_msg, cart, intent["buy"], intent["remove"], intent["swap"]),
        lambda: check_swap_intent(db, lower_msg, cart, intent["swap"]),
        lambda: check_direct_remove_intent(db, lower_msg, cart, intent["remove"], intent["swap"]),
        lambda: check_direct_add_intent(
            db, message, lower_msg, cart, conversation_history,
            intent["buy"], intent["remove"], intent["swap"], intent["discount"]
        ),
        lambda: check_unstocked_genre(db, lower_msg, cart, intent["buy"], intent["remove"]),
        lambda: check_budget_request(db, lower_msg, cart),
        lambda: check_catalog_discovery(
            db, lower_msg, cart, intent["buy"], intent["remove"], intent["swap"], intent["discount"]
        ),
        lambda: check_emotional_context(db, lower_msg, cart, intent["buy"], intent["remove"], intent["swap"]),
        lambda: check_out_of_context(db, lower_msg, cart, intent["buy"], intent["remove"], bool(find_product(db, lower_msg))),
    )
    for check in deterministic_checks:
        result = check()
        if result:
            return result["reply"], result["action_type"], result["widget"], result["cart"], result["suggested_actions"]

    if intent["checkout"]:
        checkout = initiate_checkout(cart, db)
        return (
            checkout["reply"],
            checkout["action_type"],
            checkout["widget"],
            checkout["cart"],
            _build_actions(checkout["cart"]),
        )

    # ------------------------------------------------------------------
    # PHASE 2: Agentic Groq Loop with Function Calling
    # ------------------------------------------------------------------
    client = get_groq_client()
    if not client:
        return _offline_catalog_fallback(db, message, cart)

    system_prompt = _build_system_prompt(cart, db)

    # Build messages in OpenAI format for Groq
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt}
    ]
    for turn in (conversation_history or []):
        role = turn.get("role", "user")
        if role not in ("user", "assistant"):
            role = "assistant" if role == "model" else "user"
        messages.append({"role": role, "content": turn.get("content", "")})

    # Append current user query
    messages.append({"role": "user", "content": message})

    final_action_type: str | None = None
    final_widget: dict | None = None
    reply = "How can I help you with your book search today?"

    try:
        # Four rounds cover the normal find -> add -> bundle -> reply sequence.
        for _round in range(4):
            completion = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                temperature=0.7,
                max_completion_tokens=2048,
                tools=BOOKSTORE_TOOLS,
                tool_choice="auto",
            )

            choice = completion.choices[0] if completion.choices else None
            if not choice or not choice.message:
                break

            message_obj = choice.message
            tool_calls = getattr(message_obj, "tool_calls", None)

            if not tool_calls:
                reply = message_obj.content or reply
                break

            # Append the assistant's tool call turn with clean supported properties
            messages.append({
                "role": "assistant",
                "content": message_obj.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            })

            # Execute all function calls in this round
            for tc in tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except Exception:
                    tool_args = {}
                logger.info(f"[Agent] Groq calls tool: {tool_name}({tool_args})")

                tool_result, cart, action_type, widget = _dispatch_tool(
                    tool_name,
                    tool_args,
                    cart,
                    db,
                    allow_add=intent["buy"],
                    allow_remove=intent["remove"] or intent["swap"],
                )

                if action_type:
                    final_action_type = action_type
                if widget:
                    final_widget = widget

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({"result": tool_result}),
                })

    except Exception as exc:
        logger.warning(f"[Agent] Groq API unavailable or rate-limited ({exc}). Falling back to deterministic catalog search.")
        return _offline_catalog_fallback(db, message, cart)

    # Never infer a state or payment action from generated prose. A cart or
    # checkout can change only through a successful explicit tool call, and
    # checkout itself is handled by the deterministic gate above. Correct a
    # misleading payment claim rather than letting a shopper believe money
    # moved when no verified order exists.
    checkout_claim = re.search(
        r"(?:checkout|razorpay)[^.\n]*(?:generated|created|ready)|(?:generated|created)[^.\n]*(?:checkout|razorpay)",
        reply,
        re.IGNORECASE,
    )
    if checkout_claim and not final_widget:
        reply = (
            "I have not created a checkout or payment order yet, and your cart has not changed. "
            "When you're ready, say **Proceed to Checkout** and I will create a catalog-verified Razorpay order."
        )

    reply = _clean_response_formatting(reply)
    return reply, final_action_type, final_widget, cart, _build_actions(cart)

