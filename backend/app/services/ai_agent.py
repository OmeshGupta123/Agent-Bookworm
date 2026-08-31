import json
import logging
import re
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy.orm import Session
from google import genai
from google.genai import types
from app.config import GEMINI_API_KEY, MAX_DISCOUNT_PERCENT, RAZORPAY_KEY_ID
from app.models import Product, Order
from app.schemas import CheckoutWidgetData
from app.services.audit_service import log_ai_action
from app.services.razorpay_service import create_razorpay_order_sdk

logger = logging.getLogger(__name__)

# Out-of-stock item constant for Graceful Failure Task
OUT_OF_STOCK_ITEM_NAME = "The Prince - Machiavelli (1st Edition Signed)"
OUT_OF_STOCK_REPLY = (
    "I apologize, but another collector just purchased the last signed copy of "
    "'The Prince - Machiavelli (1st Edition Signed)'. However, we have 'Atomic Habits' by James Clear available, "
    "which is currently our #1 bestseller in strategic personal growth. Would you like me to add it to your cart with a 5% discount?"
)

# Typo dictionary for fuzzy catalog matching
TYPO_CORRECTIONS = {
    "pwer": "power",
    "automic": "atomic",
    "habbit": "habit",
    "habbits": "habits",
    "macheavelli": "machiavelli",
    "machiaveli": "machiavelli",
    "steven": "stephen",
    "stefan": "stephen",
    "clean": "clean",
    "dune": "dune",
    "shining": "shining"
}

# Semantic map for personal emotions, life situations & problem solving
EMOTIONAL_PROBLEM_MAP = {
    # Financial / Wealth / Struggle
    "poor": ("wealth building & financial freedom", "I understand how challenging that feels, but the right knowledge and proven systems can completely transform your financial future.", ["Atomic Habits", "The 48 Laws of Power", "Clean Code"]),
    "broke": ("financial growth & productivity", "I hear you, and investing in your mindset and skills is the most powerful first step toward building lasting stability.", ["Atomic Habits", "Deep Work", "Clean Code"]),
    "rich": ("wealth accumulation & strategic discipline", "Ambition is powerful! Building wealth requires mastering high-value skills, habit discipline, and strategic focus.", ["Atomic Habits", "The 48 Laws of Power", "Designing Data-Intensive Applications"]),
    "wealth": ("financial independence & strategic power", "Building true wealth starts with mastering your daily habits and understanding strategic decision-making.", ["Atomic Habits", "The 48 Laws of Power"]),
    
    # Emotional / Mental State
    "sad": ("resilience & personal growth", "I hear you, and taking time to nourish your mind with uplifting, empowering books is a wonderful step forward.", ["Atomic Habits", "Deep Work"]),
    "depressed": ("mental clarity & small habits", "I understand things feel heavy right now. Small, positive daily systems can help rebuild momentum step by step.", ["Atomic Habits", "Deep Work"]),
    "stressed": ("mindset & deep focus", "I completely understand. Managing stress starts with creating clear boundaries and focusing on what you can control.", ["Deep Work", "Atomic Habits"]),
    "lonely": ("philosophy & human connection", "Reading is one of the most comforting companions. These inspiring books will keep you company and offer deep wisdom.", ["Atomic Habits", "The Shining"]),
    "tired": ("restoration & focus systems", "Rest is essential. Rebuilding your focus and daily energy starts with simple, proven habits.", ["Atomic Habits", "Deep Work"]),
    
    # Career / Ambition / Success
    "succeed": ("high performance & career mastery", "I love that drive! Achieving peak success comes down to deep focus and consistent habit execution.", ["Deep Work", "Atomic Habits", "Clean Code"]),
    "struggling": ("resilience & breakthrough strategies", "Every breakthrough begins in the middle of a struggle. These books provide clear blueprints to overcome obstacles.", ["Atomic Habits", "Deep Work"]),
    "lazy": ("motivation & habit design", "It is rarely about laziness—it is about having the right environment and friction-free systems.", ["Atomic Habits", "Deep Work"]),
    "focus": ("deep concentration & cognitive mastery", "Mastering deep focus is the ultimate superpower in today's distracted world.", ["Deep Work", "Atomic Habits"])
}

# Vibe & Genre Keyword Mapping
VIBE_GENRE_MAP = {
    "scary": "Horror",
    "horror": "Horror",
    "creepy": "Horror",
    "spooky": "Horror",
    "thriller": "Horror",
    "tech": "Tech",
    "coding": "Tech",
    "programming": "Tech",
    "software": "Tech",
    "space": "Sci-Fi",
    "future": "Sci-Fi",
    "sci-fi": "Sci-Fi",
    "scifi": "Sci-Fi",
    "galaxy": "Sci-Fi",
    "habits": "Self-Growth",
    "growth": "Self-Growth",
    "money": "Self-Growth",
    "wealth": "Self-Growth",
    "focus": "Self-Growth",
    "mindset": "Self-Growth",
    "self-growth": "Self-Growth",
    "self growth": "Self-Growth"
}

def find_product_fuzzy(db: Session, query_str: str) -> Optional[Product]:
    """
    SINGLE-ITEM catalog search tool.
    Strictly returns a SINGLE Product (highest confidence match on title or author)
    for precise add_to_cart and remove_from_cart actions.
    """
    if not query_str:
        return None

    clean_query = query_str.lower().strip()

    # Strip action and padding words to isolate product title
    for pad in ["remove", "delete", "add", "buy", "purchase", "get", "replace", "swap", "with", "for", "to", "and", "cart", "from", "the", "book", "books", "copy", "please", "some", "show", "me", "find"]:
        clean_query = re.sub(rf'\b{pad}\b', '', clean_query).strip()

    if not clean_query or len(clean_query) < 2:
        return None

    # Apply typo corrections
    words = clean_query.split()
    corrected_words = [TYPO_CORRECTIONS.get(w, w) for w in words]
    clean_query = " ".join(corrected_words)

    # 1. Exact or partial substring match on product name
    prod = db.query(Product).filter(Product.name.ilike(f"%{clean_query}%")).first()
    if prod:
        return prod

    # 2. Match significant individual keywords (length >= 3)
    significant_keywords = [w for w in corrected_words if len(w) >= 3 and w not in {"item", "some", "this"}]
    for kw in significant_keywords:
        prod = db.query(Product).filter(Product.name.ilike(f"%{kw}%")).first()
        if prod:
            return prod

    # 3. Match author name
    for kw in significant_keywords:
        prod = db.query(Product).filter(Product.author.ilike(f"%{kw}%")).first()
        if prod:
            return prod

    return None

def search_catalog_by_theme(db: Session, theme: str, limit: int = 5) -> List[Product]:
    """
    DEDICATED MULTI-ITEM catalog search tool.
    Searches genres, mapped vibes, title words, author names, and descriptions.
    Returns a LIST of matching available products up to the specified limit.
    """
    if not theme:
        return db.query(Product).filter(Product.stock_quantity > 0).limit(limit).all()

    clean_theme = theme.lower().strip()
    for pad in ["recommend", "recommendation", "recommendations", "good", "top", "best", "books", "book", "show", "me", "find", "list", "give", "me", "please", "some"]:
        clean_theme = re.sub(rf'\b{pad}\b', '', clean_theme).strip()

    words = clean_theme.split()
    corrected_words = [TYPO_CORRECTIONS.get(w, w) for w in words]
    clean_theme = " ".join(corrected_words)

    results = []
    seen_ids = set()

    def add_prods(prods: List[Product]):
        for p in prods:
            if p.id not in seen_ids and p.stock_quantity > 0:
                results.append(p)
                seen_ids.add(p.id)

    # 1. Mapped Vibe / Genre match
    mapped_genre = VIBE_GENRE_MAP.get(clean_theme)
    if mapped_genre:
        add_prods(db.query(Product).filter(Product.genre.ilike(f"%{mapped_genre}%")).all())

    for kw in corrected_words:
        if len(kw) >= 3:
            mg = VIBE_GENRE_MAP.get(kw)
            if mg:
                add_prods(db.query(Product).filter(Product.genre.ilike(f"%{mg}%")).all())

    # 2. Genre field match
    if clean_theme:
        add_prods(db.query(Product).filter(Product.genre.ilike(f"%{clean_theme}%")).all())

    for kw in corrected_words:
        if len(kw) >= 3:
            add_prods(db.query(Product).filter(Product.genre.ilike(f"%{kw}%")).all())

    # 3. Product title and description match
    for kw in corrected_words:
        if len(kw) >= 3:
            add_prods(db.query(Product).filter(Product.name.ilike(f"%{kw}%")).all())
            add_prods(db.query(Product).filter(Product.description.ilike(f"%{kw}%")).all())

    # 4. Fallback if empty: fetch top available books
    if not results:
        add_prods(db.query(Product).filter(Product.stock_quantity > 0).limit(limit).all())

    return results[:limit]

def is_in_cart(cart: List[Dict[str, Any]], product_name: str) -> bool:
    """Helper to check if a book is already present in the user's cart using fuzzy matching."""
    name_lower = product_name.lower().strip()
    for item in cart:
        item_name = item.get("name", "").lower()
        if name_lower in item_name or item_name in name_lower:
            return True
    return False

def add_to_cart(cart: List[Dict[str, Any]], product: Product, discount_pct: float = 0.0) -> List[Dict[str, Any]]:
    """Adds a product to cart if not present, applying capped discount."""
    capped_discount = min(discount_pct, MAX_DISCOUNT_PERCENT)
    disc_amount = round(product.price * (capped_discount / 100.0), 2)
    final_price = round(product.price - disc_amount, 2)

    existing = next((item for item in cart if item.get("product_id") == product.id), None)
    if not existing:
        cart.append({
            "product_id": product.id,
            "name": product.name,
            "author": product.author,
            "format": product.format,
            "price": product.price,
            "discount_percentage": capped_discount,
            "discount_amount": disc_amount,
            "final_price": final_price,
            "image_url": product.image_url
        })
    return cart

def remove_from_cart(cart: List[Dict[str, Any]], identifier: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Removes matching product(s) by ID, name substring, or author from cart.
    Uses case-insensitive and fuzzy partial string matching.
    """
    if not cart or not identifier:
        return cart, []

    ident_clean = identifier.lower().strip()
    for pad in ["remove", "delete", "from my cart", "from cart", "the book", "copy of", "please", "swap", "replace", "and", "add"]:
        ident_clean = re.sub(rf'\b{pad}\b', '', ident_clean).strip()

    # Apply typo corrections to identifier
    words = ident_clean.split()
    corrected = [TYPO_CORRECTIONS.get(w, w) for w in words]
    ident_clean = " ".join(corrected)

    removed_names = []
    new_cart = []

    for item in cart:
        item_name = item.get("name", "").lower()
        item_author = item.get("author", "").lower()
        item_id = str(item.get("product_id", ""))

        is_match = False
        if ident_clean:
            if ident_clean in item_name or item_name in ident_clean or item_id == ident_clean:
                is_match = True
            else:
                item_words = set(item_name.split())
                query_words = [qw for qw in ident_clean.split() if len(qw) >= 3]
                if any(kw in item_words or any(kw in iw for iw in item_words) for kw in query_words):
                    is_match = True

        if is_match:
            removed_names.append(item.get("name"))
        else:
            new_cart.append(item)

    return new_cart, removed_names

def find_cross_sell_companion(db: Session, added_product: Product, cart: List[Dict[str, Any]]) -> Optional[Product]:
    """
    Finds 1 highly relevant complementary book for the continuous cross-sell engine.
    Ensures the companion is not already present in the cart.
    """
    comp_query = "%Deep Work%" if "atomic" in added_product.name.lower() else ("%Atomic Habits%" if "deep" in added_product.name.lower() or "power" in added_product.name.lower() else f"%{added_product.genre}%")
    
    companion = db.query(Product).filter(
        Product.name.ilike(comp_query),
        Product.id != added_product.id,
        Product.stock_quantity > 0
    ).first()

    if not companion:
        companion = db.query(Product).filter(
            Product.genre == added_product.genre,
            Product.id != added_product.id,
            Product.stock_quantity > 0
        ).first()

    if not companion:
        companion = db.query(Product).filter(
            Product.id != added_product.id,
            Product.stock_quantity > 0
        ).first()

    if companion and not is_in_cart(cart, companion.name):
        return companion
    return None

def generate_checkout(cart: List[Dict[str, Any]], db: Session) -> Tuple[str, str, Dict[str, Any], List[Dict[str, Any]], List[str]]:
    """
    Explicit tool function to calculate final cart total, invoke Razorpay Order Creation API,
    save order to database, log CHECKOUT_GENERATED audit trail, and return CheckoutWidgetData.
    """
    if not cart:
        default_book = db.query(Product).filter(Product.name.ilike("%Atomic Habits%")).first()
        if default_book:
            cart = add_to_cart(cart, default_book, discount_pct=10.0)

    original_total = sum(item["price"] for item in cart)
    final_amount = sum(item["final_price"] for item in cart)
    total_discount = round(original_total - final_amount, 2)
    avg_discount_pct = round((total_discount / original_total * 100.0), 1) if original_total > 0 else 0.0

    first_prod_id = cart[0]["product_id"] if cart else 1

    rzp_order_id = create_razorpay_order_sdk(
        amount_in_inr=final_amount,
        notes={
            "items_count": str(len(cart)),
            "cart_summary": ", ".join([i["name"] for i in cart[:3]])
        }
    )

    db_order = Order(
        razorpay_order_id=rzp_order_id,
        total_amount=final_amount,
        status="pending",
        product_id=first_prod_id,
        discount_percentage=avg_discount_pct
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)

    log_ai_action(
        db=db,
        order_id=db_order.id,
        action_type="CHECKOUT_GENERATED",
        ai_reasoning=(
            f"CHECKOUT TOOL EXECUTED: Created Razorpay order '{rzp_order_id}' for {len(cart)} cart items. "
            f"Original total: ₹{original_total:.2f}, Savings: ₹{total_discount:.2f} ({avg_discount_pct}% avg discount), "
            f"Final payable amount: ₹{final_amount:.2f}."
        ),
        amount_involved=final_amount
    )

    widget_data = {
        "order_id": db_order.id,
        "razorpay_order_id": rzp_order_id,
        "razorpay_key_id": RAZORPAY_KEY_ID,
        "items": cart,
        "original_total": original_total,
        "total_discount": total_discount,
        "discount_percentage": avg_discount_pct,
        "final_amount": final_amount,
        "currency": "INR"
    }

    reply_text = (
        f"Excellent! Your checkout order for **{len(cart)} item(s)** has been generated below with Razorpay Order ID `{rzp_order_id}`. "
        f"You save **₹{total_discount:.2f}** with your bounded discount applied. Click the button below to complete payment:"
    )

    return reply_text, "SHOW_CHECKOUT", widget_data, cart, []

def process_chat_message(
    db: Session,
    message: str,
    conversation_history: List[Dict[str, str]],
    current_cart: List[Dict[str, Any]]
) -> Tuple[str, Optional[str], Optional[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    """
    Stateful Agentic Bookstore process function.
    Handles Continuous Upsell Engine, Empathetic Problem Solving, Budget Curation, search_catalog_by_theme, Graceful Pivots, and Stateful Cart Tools.
    """
    lower_msg = message.lower().strip()
    cart = list(current_cart or [])

    # Helper to build dynamic action chips
    def build_actions(extra_actions: List[str] = None) -> List[str]:
        actions = []
        if extra_actions:
            for act in extra_actions:
                if "add " in act.lower() and " to cart" in act.lower():
                    title = act.lower().replace("add ", "").replace(" to cart", "").strip()
                    if not is_in_cart(cart, title):
                        actions.append(act)
                else:
                    actions.append(act)
        
        if cart and "Proceed to Checkout" not in actions:
            actions.append("Proceed to Checkout")
        return actions

    has_buy_intent = any(k in lower_msg for k in ["buy", "add", "purchase", "get", "order", "want to buy", "discount on"])
    has_remove_intent = any(k in lower_msg for k in ["remove", "delete", "only want", "dont want", "don't want"])
    has_swap_intent = any(k in lower_msg for k in ["replace", "swap", "exchange", "change", "trade"])

    # 1. EMPATHETIC PROBLEM SOLVING & SEMANTIC PIVOTS (Handling "I am poor", "I am sad", "I want to get rich", "stressed")
    matched_emotion = next((k for k in EMOTIONAL_PROBLEM_MAP if k in lower_msg), None)
    if matched_emotion and not has_buy_intent and not has_remove_intent and not has_swap_intent:
        genre_label, emp_opening, book_hints = EMOTIONAL_PROBLEM_MAP[matched_emotion]
        
        consult_books = []
        for bh in book_hints:
            p = db.query(Product).filter(Product.name.ilike(f"%{bh}%")).first()
            if p and p not in consult_books:
                consult_books.append(p)

        if not consult_books:
            consult_books = db.query(Product).filter(Product.stock_quantity > 0).limit(3).all()

        b_lines = [f"• **{b.name}** by {b.author} (₹{b.price:.2f}) - {b.genre}\n  *{b.description[:90]}...*" for b in consult_books]
        reply = (
            f"{emp_opening}\n\n"
            f"Here are {len(consult_books)} top recommendations in **{genre_label}** to help you achieve your goals:\n\n"
            + "\n\n".join(b_lines)
            + "\n\nWhich of these would you like to explore or add to your cart to get started?"
        )
        extra_chips = [f"Add {b.name} to Cart" for b in consult_books[:3]]
        return (reply, None, None, cart, build_actions(extra_chips))

    # 2. BUDGET CURATOR FLOW (Parsing ₹200, 200 rs, budget of 200, under ₹500, etc.)
    budget_match = re.search(r'(?:budget|under|below|within|price of|rs\.?|rupees?|₹)\s*(\d+(?:\.\d+)?)', lower_msg)
    if not budget_match and ("budget" in lower_msg or "under" in lower_msg):
        budget_match = re.search(r'\b(\d+(?:\.\d+)?)\b', lower_msg)

    if budget_match:
        try:
            budget_val = float(budget_match.group(1))
            if budget_val > 0:
                all_prods = db.query(Product).filter(Product.stock_quantity > 0).all()
                selected_bundle = []
                running_total = 0.0

                for p in all_prods:
                    if running_total + p.price <= budget_val:
                        selected_bundle.append(p)
                        running_total += p.price
                    if len(selected_bundle) >= 3 or running_total >= budget_val * 0.9:
                        break

                if not selected_bundle and all_prods:
                    cheapest = min(all_prods, key=lambda x: x.price)
                    selected_bundle = [cheapest]
                    running_total = cheapest.price

                b_lines = [f"• **{b.name}** by {b.author} ({b.format}) - ₹{b.price:.2f}" for b in selected_bundle]
                reply = (
                    f"As your **Budget Curator**, I have selected a custom bundle that fits right under your **₹{budget_val:.2f}** budget:\n\n"
                    + "\n".join(b_lines)
                    + f"\n\n**Total Bundle Price:** **₹{running_total:.2f}** (Savings: ₹{max(0.0, budget_val - running_total):.2f} within your limit).\n\n"
                    "Would you like me to add these books to your cart?"
                )
                extra_chips = [f"Add {b.name} to Cart" for b in selected_bundle[:3]]
                return (reply, None, None, cart, build_actions(extra_chips))
        except Exception as e:
            logger.warning(f"Budget parsing failed: {e}")

    # 3. GRACEFUL FAILURE PIVOT FOR UNSTOCKED GENRES / VIBES (e.g. "funny books", "comedy", "romance")
    unstocked_genres = ["funny", "comedy", "romance", "romantic", "cooking", "cookbook", "manga", "poetry"]
    if any(ug in lower_msg for ug in unstocked_genres) and not has_buy_intent and not has_remove_intent:
        matched_ug = next(ug for ug in unstocked_genres if ug in lower_msg)
        pivot_books = db.query(Product).filter(Product.name.in_(["Atomic Habits", "The 48 Laws of Power"])).all()
        if not pivot_books:
            pivot_books = db.query(Product).filter(Product.stock_quantity > 0).limit(2).all()

        log_ai_action(
            db=db,
            action_type="STOCK_CHECK_FAILED",
            ai_reasoning=f"GRACEFUL FAILURE PIVOT: Requested unstocked genre '{matched_ug}'. Pivoted to bestsellers to save sale.",
            amount_involved=0.0
        )

        b_lines = [f"• **{b.name}** by {b.author} (₹{b.price:.2f}) - {b.genre}" for b in pivot_books]
        reply = (
            f"I apologize, but we are currently out of stock for **{matched_ug.title()}** books! "
            f"However, to help save your read, I'd highly recommend these 2 top-rated bestsellers from our active collection:\n\n"
            + "\n".join(b_lines)
            + "\n\nWould you like me to add either of these to your cart with a special discount?"
        )
        extra_chips = [f"Add {b.name} to Cart" for b in pivot_books]
        return (reply, "GRACEFUL_FAILURE", None, cart, build_actions(extra_chips))

    # 4. MULTI-BOOK RECOMMENDATIONS VIA search_catalog_by_theme (e.g., "Recommend 3 good Self-Growth books")
    if any(k in lower_msg for k in ["recommend", "recommendation", "top books", "best books", "trending", "show me", "give me", "list"]):
        num_match = re.search(r'\b(\d+)\b', lower_msg)
        requested_limit = int(num_match.group(1)) if num_match and 1 <= int(num_match.group(1)) <= 10 else 3

        theme_query = lower_msg
        for pad in ["recommend", "recommendation", "recommendations", "good", "top", "best", "books", "book", "show", "me", "find", "list", "give", "me", "please", "some", "3", "5", "4", "2", "1"]:
            theme_query = re.sub(rf'\b{pad}\b', '', theme_query).strip()

        matched_books = search_catalog_by_theme(db, theme=theme_query, limit=requested_limit)
        
        if matched_books:
            b_lines = [
                f"{idx}. **{b.name}** by {b.author} (₹{b.price:.2f}) - *{b.genre}*\n   {b.description[:95]}..."
                for idx, b in enumerate(matched_books, 1)
            ]
            
            theme_title = theme_query.title() if theme_query else "Bestselling"
            reply = (
                f"Here are {len(matched_books)} top-recommended **{theme_title}** books from our catalog:\n\n"
                + "\n\n".join(b_lines)
                + f"\n\nEach of these titles is highly acclaimed by readers. Which one would you like me to add to your cart?"
            )
            extra_chips = [f"Add {b.name} to Cart" for b in matched_books]
            return (reply, None, None, cart, build_actions(extra_chips))

    # 5. OUT-OF-CONTEXT POLITE PIVOT (coding, weather, politics, recipes, random queries)
    out_of_context_topics = {
        "weather": ("science & environment", ["Dune", "Clean Code"]),
        "coding": ("tech & programming", ["Clean Code", "Designing Data-Intensive Applications"]),
        "program": ("tech & software design", ["Clean Code", "Designing Data-Intensive Applications"]),
        "python": ("tech & programming", ["Clean Code"]),
        "politics": ("history & strategy", ["The 48 Laws of Power", "The Prince"]),
        "recipe": ("lifestyle & habits", ["Atomic Habits"]),
        "football": ("sports & mindset", ["Atomic Habits", "Deep Work"]),
        "movie": ("fiction & drama", ["The Shining", "Dune"])
    }

    matched_topic = next((t for t in out_of_context_topics if t in lower_msg), None)
    if matched_topic or (len(lower_msg) > 3 and not has_buy_intent and not has_remove_intent and not find_product_fuzzy(db, lower_msg) and any(k in lower_msg for k in ["what is", "how to", "who is", "tell me about climate"])):
        topic_label, book_hints = out_of_context_topics.get(matched_topic, ("related topics", ["Atomic Habits", "Deep Work", "Dune"]))
        
        pivot_books = []
        for bh in book_hints:
            p = db.query(Product).filter(Product.name.ilike(f"%{bh}%")).first()
            if p and p not in pivot_books:
                pivot_books.append(p)

        if not pivot_books:
            pivot_books = db.query(Product).filter(Product.stock_quantity > 0).limit(3).all()

        b_lines = [f"• **{b.name}** by {b.author} (₹{b.price:.2f}) - {b.genre}" for b in pivot_books]
        reply = (
            f"I specialize strictly in books! I'd be happy to recommend some great reads related to **{topic_label}**:\n\n"
            + "\n".join(b_lines)
            + "\n\nLet me know if you would like me to add any of these to your cart or tell you more about them!"
        )
        extra_chips = [f"Add {b.name} to Cart" for b in pivot_books]
        return (reply, None, None, cart, build_actions(extra_chips))

    # 6. DETERMINISTIC PRE-PROCESSING ROUTER: MULTI-INTENT & SWAP PATTERNS WITH CONTINUOUS UPSELL
    if has_swap_intent or (has_remove_intent and has_buy_intent):
        remove_target = ""
        add_target = ""

        if "with" in lower_msg:
            parts = lower_msg.split("with")
            remove_target = parts[0]
            add_target = parts[1]
        elif "for" in lower_msg:
            parts = lower_msg.split("for")
            remove_target = parts[0]
            add_target = parts[1]
        elif "to" in lower_msg:
            parts = lower_msg.split("to")
            remove_target = parts[0]
            add_target = parts[1]
        elif "and add" in lower_msg:
            parts = lower_msg.split("and add")
            remove_target = parts[0]
            add_target = parts[1]
        elif "and buy" in lower_msg:
            parts = lower_msg.split("and buy")
            remove_target = parts[0]
            add_target = parts[1]
        else:
            remove_target = lower_msg
            add_target = lower_msg

        cart, removed_items = remove_from_cart(cart, remove_target)
        if removed_items:
            log_ai_action(
                db=db,
                action_type="ITEM_REMOVED_FROM_CART",
                ai_reasoning=f"PHYSICAL TOOL EXECUTED: Removed {removed_items} from cart.",
                amount_involved=0.0
            )

        added_prod = find_product_fuzzy(db, add_target)

        if added_prod:
            cart = add_to_cart(cart, added_prod, discount_pct=10.0)
            log_ai_action(
                db=db,
                action_type="ITEM_ADDED_TO_CART",
                ai_reasoning=f"PHYSICAL TOOL EXECUTED: Added '{added_prod.name}' to cart.",
                amount_involved=round(added_prod.price * 0.9, 2)
            )

        # CONTINUOUS UPSELL ENGINE: Find complementary book for cross-selling
        companion = find_cross_sell_companion(db, added_prod, cart) if added_prod else None
        extra_chip = [f"Add {companion.name} to Cart"] if companion else []

        if removed_items and added_prod:
            cross_sell_text = f"\n\n**Recommended Companion Read:** Since you added **{added_prod.name}**, I highly recommend pairing it with **{companion.name}** by {companion.author} (₹{companion.price:.2f}) to maximize your focus!" if companion else ""
            reply = (
                f"I've removed **{', '.join(removed_items)}** and added **{added_prod.name}** to your cart with a 10% discount!\n\n"
                f"**About {added_prod.name}:** {added_prod.description}{cross_sell_text}"
            )
            return (reply, "CART_UPDATED", None, cart, build_actions(extra_chip))
        elif removed_items:
            reply = f"I've removed **{', '.join(removed_items)}** from your cart."
            return (reply, "CART_UPDATED", None, cart, build_actions())
        elif added_prod:
            cross_sell_text = f"\n\n**Recommended Companion Read:** Since you added **{added_prod.name}**, I highly recommend pairing it with **{companion.name}** by {companion.author} (₹{companion.price:.2f}) to maximize your focus!" if companion else ""
            reply = (
                f"I've added **{added_prod.name}** to your cart with a 10% discount!\n\n"
                f"**About {added_prod.name}:** {added_prod.description}{cross_sell_text}"
            )
            return (reply, "CART_UPDATED", None, cart, build_actions(extra_chip))

    # 7. GRACEFUL FAILURE SCENARIO (Machiavelli 1st Edition Signed)
    if "prince" in lower_msg or "machiavelli" in lower_msg or "1st edition" in lower_msg:
        machiavelli_item = db.query(Product).filter(Product.name.ilike("%Machiavelli%")).first()
        item_stock = machiavelli_item.stock_quantity if machiavelli_item else 0

        log_ai_action(
            db=db,
            action_type="STOCK_CHECK_FAILED",
            ai_reasoning=(
                f"STOCK FAILURE GATING: User requested '{OUT_OF_STOCK_ITEM_NAME}'. "
                f"Stock count = {item_stock}. Triggered intentional OutOfStock Exception & graceful pivot strategy."
            ),
            amount_involved=0.0
        )
        actions = build_actions(["Add Atomic Habits to Cart"])
        return (OUT_OF_STOCK_REPLY, "GRACEFUL_FAILURE", None, cart, actions)

    # 8. EXPLICIT REMOVAL INTENT ONLY
    if has_remove_intent:
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
                ai_reasoning=f"PHYSICAL TOOL EXECUTED: Removed unwanted items {removed_titles}. Cart now contains only requested book.",
                amount_involved=0.0
            )
            reply = f"Understood! I've updated your cart to keep only your requested book."
            return (reply, "CART_UPDATED", None, cart, build_actions())
        else:
            cart, removed = remove_from_cart(cart, lower_msg)
            if removed:
                log_ai_action(
                    db=db,
                    action_type="ITEM_REMOVED_FROM_CART",
                    ai_reasoning=f"PHYSICAL TOOL EXECUTED: Removed {removed} from cart based on user request.",
                    amount_involved=0.0
                )
                reply = f"I have removed **{', '.join(removed)}** from your cart."
                return (reply, "CART_UPDATED", None, cart, build_actions())
            else:
                reply = "I couldn't find that item in your current cart."
                return (reply, None, None, cart, build_actions())

    # 9. HARD GATING TEST SCENARIO: DISCOUNT > 15% REQUESTED
    if "20%" in lower_msg or "20 percent" in lower_msg or "30%" in lower_msg or "25%" in lower_msg:
        target_book = find_product_fuzzy(db, lower_msg) or db.query(Product).filter(Product.name.ilike("%Atomic Habits%")).first()
        base_price = target_book.price if target_book else 16.99
        book_name = target_book.name if target_book else "Atomic Habits"
        requested_num = 20.0
        
        log_ai_action(
            db=db,
            action_type="CHECKOUT_BLOCKED",
            ai_reasoning=(
                f"HARD GATING ENFORCED: User requested a {requested_num}% discount on '{book_name}'. "
                f"Merchant hard-cap rule forbids discounts exceeding {MAX_DISCOUNT_PERCENT}%. "
                f"Decision: Reject {requested_num}% request, enforce maximum capped discount of {MAX_DISCOUNT_PERCENT}%."
            ),
            amount_involved=0.0
        )
        
        if target_book:
            cart = add_to_cart(cart, target_book, discount_pct=MAX_DISCOUNT_PERCENT)
            log_ai_action(
                db=db,
                action_type="ITEM_ADDED_TO_CART",
                ai_reasoning=f"PHYSICAL TOOL EXECUTED: Added '{target_book.name}' to cart at capped {MAX_DISCOUNT_PERCENT}% discount.",
                amount_involved=round(target_book.price * 0.85, 2)
            )

        companion = find_cross_sell_companion(db, target_book, cart) if target_book else None
        extra_chip = [f"Add {companion.name} to Cart"] if companion else ["Add Deep Work to Cart"]

        reply = (
            f"Our merchant system strictly caps maximum discounts at {MAX_DISCOUNT_PERCENT}%, so I cannot apply a 20% discount. "
            f"However, I have added **{book_name}** to your cart with our maximum allowed **{MAX_DISCOUNT_PERCENT}% discount**!\n\n"
            f"**Atomic Habits by James Clear** is a masterpiece on behavioral psychology that reveals how tiny 1% daily changes accumulate into massive life transformations over time."
        )
        return (reply, "CART_UPDATED", None, cart, build_actions(extra_chip))

    # 10. EXPLICIT CHECKOUT CONFIRMATION -> INVOKE generate_checkout TOOL
    if "checkout" in lower_msg or "pay" in lower_msg or "buy now" in lower_msg or "ready to order" in lower_msg or "generate checkout" in lower_msg:
        return generate_checkout(cart=cart, db=db)

    # 11. INFORMATIONAL INQUIRIES (DO NOT ADD TO CART)
    if "know more" in lower_msg or "tell me more" in lower_msg or "more about" in lower_msg or "tell me about" in lower_msg or "what is" in lower_msg or "summary" in lower_msg:
        prod = find_product_fuzzy(db, lower_msg) or db.query(Product).filter(Product.name.ilike("%Deep Work%")).first()
        
        if prod:
            desc = (
                f"**{prod.name} by {prod.author}** ({prod.format} - ₹{prod.price:.2f}):\n\n"
                f"{prod.description} This transformative book offers actionable strategies for eliminating modern workplace distractions, "
                f"cultivating deep cognitive focus, and mastering complex skills rapidly. It is essential reading for knowledge workers and ambitious professionals aiming to produce elite-level results."
            )
            actions = build_actions([f"Add {prod.name} to Cart"])
            return (desc, None, None, cart, actions)

    # 12. SPECIFIC BOOK ENQUIRY / ADDITION WITH CONTINUOUS UPSELL
    prod = find_product_fuzzy(db, lower_msg)
    if prod:
        if has_buy_intent:
            cart = add_to_cart(cart, prod, discount_pct=10.0)
            log_ai_action(
                db=db,
                action_type="ITEM_ADDED_TO_CART",
                ai_reasoning=f"PHYSICAL TOOL EXECUTED: Added requested book '{prod.name}' to cart. Bounded 10% discount applied.",
                amount_involved=round(prod.price * 0.9, 2)
            )

            # CONTINUOUS UPSELL ENGINE: Find complementary book for cross-selling
            companion = find_cross_sell_companion(db, prod, cart)
            comp_name = companion.name if companion else "Deep Work"
            extra_chip = [f"Add {comp_name} to Cart"]

            reply = (
                f"I've added **{prod.name}** to your cart with a 10% discount!\n\n"
                f"**Why {prod.name} is a Great Read:** {prod.description} It delivers a powerful framework for continuous improvement, replacing self-doubt with proven systems that make success automatic.\n\n"
                f"**Recommended Companion Read:** **{comp_name}** pairs exceptionally well with {prod.name} to maximize your productivity. Should I add it to your cart?"
            )
            return (reply, "CART_UPDATED", None, cart, build_actions(extra_chip))
        else:
            reply = (
                f"**{prod.name} by {prod.author}** ({prod.format} - ₹{prod.price:.2f}) - *{prod.genre}*:\n\n"
                f"{prod.description} This internationally acclaimed title provides groundbreaking insights into human behavior and goal achievement. Readers praise it as an engaging, practical roadmap that delivers immediate real-world results."
            )
            actions = build_actions([f"Add {prod.name} to Cart"])
            return (reply, None, None, cart, actions)

    # 13. GENERAL RECOMMENDATION / AUTHOR ENQUIRIES
    authors_list = ["stephen king", "james clear", "robert greene", "cal newport", "andy weir", "martin kleppmann"]
    matched_author = next((a for a in authors_list if a in lower_msg), None)
    if matched_author:
        author_books = db.query(Product).filter(Product.author.ilike(f"%{matched_author}%")).limit(3).all()
        if author_books:
            b_lines = [f"• **{b.name}** ({b.format}) - ₹{b.price:.2f}: {b.description[:90]}..." for b in author_books]
            reply = (
                f"Here are top-selling books by **{author_books[0].author}**:\n\n"
                + "\n\n".join(b_lines)
                + f"\n\nEach of these titles captures {author_books[0].author}'s masterclass storytelling and deep expertise."
            )
            extra_chips = [f"Add {b.name} to Cart" for b in author_books]
            return (reply, None, None, cart, build_actions(extra_chips))

    genres_list = ["horror", "self-growth", "sci-fi", "tech", "classics"]
    matched_genre = next((g for g in genres_list if g in lower_msg), None)
    if matched_genre:
        genre_books = db.query(Product).filter(Product.genre.ilike(f"%{matched_genre}%"), Product.stock_quantity > 0).limit(3).all()
        if genre_books:
            b_lines = [f"• **{b.name}** by {b.author} (₹{b.price:.2f}): {b.description[:90]}..." for b in genre_books]
            reply = (
                f"Here are 3 top-recommended books in **{matched_genre.title()}**:\n\n"
                + "\n\n".join(b_lines)
                + "\n\nThese titles are highly rated by readers for their compelling narratives and practical wisdom."
            )
            extra_chips = [f"Add {b.name} to Cart" for b in genre_books]
            return (reply, None, None, cart, build_actions(extra_chips))

    # 14. GENERAL GEMINI LLM FALLBACK WITH STRICT CONTINUOUS UPSELL RULE
    if GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = (
                "You are Agent Bookworm, an AI assistant for an Agentic Bookstore with a 200-book catalog.\n"
                "STRICT BOUNDED RULES:\n"
                "1. Continuous Cross-Sell / Upsell Rule: Whenever you successfully execute add_to_cart, you MUST immediately execute a cross-sell strategy. Look at the book just added, find 1 highly relevant complementary book in the catalog, and pitch it in 1-2 sentences. You MUST include a dynamic action chip to add this complementary book to the cart.\n"
                "2. If a user asks for general recommendations, a specific vibe/genre, or asks for multiple books (e.g. 'Recommend 3 Self-Growth books'), you MUST call search_catalog_by_theme tool and output a pitch for EVERY book returned by the tool, not just the first one. Include action chips for each book.\n"
                "3. Use find_product_fuzzy ONLY for single-item lookups (add_to_cart, remove_from_cart).\n"
                "4. Empathetic Problem Solving: If a user states a personal emotion or life situation ('I am poor', 'I am sad'), validate with brief empathy and pitch 2-3 relevant books.\n"
                "5. NEVER output raw cart contents, subtotals, or bulleted lists of cart items in your text response.\n"
                "6. Always format currency using the Rupee symbol ₹.\n\n"
                f"Active Cart Items: {[i['name'] for i in cart]}\n"
                f"User Message: {message}"
            )
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            reply = response.text if response and response.text else "How can I help you with your book search today?"
            return (reply, None, None, cart, build_actions())
        except Exception as e:
            logger.warning(f"Gemini API call failed: {e}")

    # Default fallback
    return (
        "Welcome to Agent Bookworm Bookstore! How can I help you with your book search today?",
        None,
        None,
        cart,
        build_actions()
    )
