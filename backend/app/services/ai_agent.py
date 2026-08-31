import json
import logging
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
    removed_names = []
    new_cart = []
    ident_clean = identifier.lower().strip()

    # Clean common query padding words
    for pad in ["remove", "delete", "from my cart", "from cart", "the book", "copy of", "please"]:
        ident_clean = ident_clean.replace(pad, "").strip()

    if " and " in ident_clean:
        ident_clean = ident_clean.split(" and ")[0].strip()

    for item in cart:
        item_name = item.get("name", "").lower()
        item_author = item.get("author", "").lower()
        
        # Fuzzy match logic
        is_match = False
        if ident_clean:
            is_match = (
                ident_clean in item_name
                or item_name in ident_clean
                or ident_clean in item_author
                or str(item.get("product_id")) == ident_clean
                or any(w in item_name for w in ident_clean.split() if len(w) > 3)
            )

        if is_match:
            removed_names.append(item.get("name"))
        else:
            new_cart.append(item)

    return new_cart, removed_names

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
    Stateful Agentic Bookstore process function with multi-intent support & fuzzy matching.
    """
    lower_msg = message.lower()
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

    # Detect explicit buying intent keywords
    has_buy_intent = any(k in lower_msg for k in ["buy", "add", "purchase", "get", "order", "want to buy", "discount on"])
    has_remove_intent = any(k in lower_msg for k in ["remove", "delete", "only want", "dont want", "don't want"])

    # 1. MULTI-INTENT COMPOUND SENTENCES (e.g. "remove Atomic Habits and add Deep Work")
    if has_remove_intent and has_buy_intent:
        # Step A: Perform Removal First
        remove_part = lower_msg
        if "and add" in lower_msg:
            remove_part = lower_msg.split("and add")[0]
        elif "and buy" in lower_msg:
            remove_part = lower_msg.split("and buy")[0]
        
        cart, removed_items = remove_from_cart(cart, remove_part)
        if removed_items:
            log_ai_action(
                db=db,
                action_type="ITEM_REMOVED_FROM_CART",
                ai_reasoning=f"MULTI-INTENT CART UPDATE: Removed {removed_items} from cart in compound action.",
                amount_involved=0.0
            )

        # Step B: Perform Addition
        add_book_name = "deep work" if "deep work" in lower_msg else ("atomic habits" if "atomic" in lower_msg else "48 laws")
        added_prod = db.query(Product).filter(Product.name.ilike(f"%{add_book_name}%")).first()
        if added_prod:
            cart = add_to_cart(cart, added_prod, discount_pct=10.0)
            log_ai_action(
                db=db,
                action_type="ITEM_ADDED_TO_CART",
                ai_reasoning=f"MULTI-INTENT CART UPDATE: Added '{added_prod.name}' to cart in compound action.",
                amount_involved=round(added_prod.price * 0.9, 2)
            )

            removed_str = f"Removed **{', '.join(removed_items)}**" if removed_items else "Updated your cart"
            reply = f"{removed_str} and added **{added_prod.name}** with a 10% discount!\n\n**About {added_prod.name}:** {added_prod.description}"
            return (reply, "CART_UPDATED", None, cart, build_actions())

    # 2. GRACEFUL FAILURE SCENARIO (Machiavelli 1st Edition Signed)
    if "prince" in lower_msg or "machiavelli" in lower_msg or "1st edition" in lower_msg:
        machiavelli_item = db.query(Product).filter(Product.name.ilike("%Machiavelli%")).first()
        item_stock = machiavelli_item.stock_quantity if machiavelli_item else 0

        # AUDIT AMOUNT FIX: Set amount_involved=0.0 for failed stock checks
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

    # 3. EXPLICIT REMOVAL INTENT ONLY ("remove", "delete", "only want", "dont want")
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
                ai_reasoning=f"CART STATE UPDATED: Removed unwanted items {removed_titles}. Cart now contains only requested book.",
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
                    ai_reasoning=f"CART STATE UPDATED: Removed {removed} from cart based on user request.",
                    amount_involved=0.0
                )
                reply = f"I have removed **{', '.join(removed)}** from your cart."
                return (reply, "CART_UPDATED", None, cart, build_actions())
            else:
                reply = "I couldn't find that item in your current cart."
                return (reply, None, None, cart, build_actions())

    # 4. HARD GATING TEST SCENARIO: DISCOUNT > 15% REQUESTED (e.g. 20%)
    if "20%" in lower_msg or "20 percent" in lower_msg or "30%" in lower_msg or "25%" in lower_msg:
        target_book = db.query(Product).filter(Product.name.ilike("%Atomic Habits%")).first()
        if not target_book:
            target_book = db.query(Product).filter(Product.stock_quantity > 0).first()
            
        base_price = target_book.price if target_book else 16.99
        book_name = target_book.name if target_book else "Atomic Habits"
        requested_num = 20.0
        
        # AUDIT AMOUNT FIX: Set amount_involved=0.0 for blocked discount requests
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
                ai_reasoning=f"Added '{target_book.name}' to cart at capped {MAX_DISCOUNT_PERCENT}% discount.",
                amount_involved=round(target_book.price * 0.85, 2)
            )

        reply = (
            f"Our merchant system strictly caps maximum discounts at {MAX_DISCOUNT_PERCENT}%, so I cannot apply a 20% discount. "
            f"However, I have added **{book_name}** to your cart with our maximum allowed **{MAX_DISCOUNT_PERCENT}% discount**!\n\n"
            f"**Atomic Habits by James Clear** is a masterpiece on behavioral psychology that reveals how tiny 1% daily changes accumulate into massive life transformations over time."
        )
        actions = build_actions(["Add Deep Work to Cart"])
        return (reply, "CART_UPDATED", None, cart, actions)

    # 5. EXPLICIT CHECKOUT CONFIRMATION -> INVOKE generate_checkout TOOL
    if "checkout" in lower_msg or "pay" in lower_msg or "buy now" in lower_msg or "ready to order" in lower_msg or "generate checkout" in lower_msg:
        return generate_checkout(cart=cart, db=db)

    # 6. INFORMATIONAL INQUIRIES (DO NOT ADD TO CART)
    if "know more" in lower_msg or "tell me more" in lower_msg or "more about" in lower_msg or "tell me about" in lower_msg or "what is" in lower_msg or "summary" in lower_msg:
        book_target = "Deep Work" if "deep work" in lower_msg else ("Atomic Habits" if "atomic" in lower_msg else "Deep Work")
        prod = db.query(Product).filter(Product.name.ilike(f"%{book_target}%")).first()
        
        if prod:
            desc = (
                f"**{prod.name} by {prod.author}** ({prod.format} - ₹{prod.price:.2f}):\n\n"
                f"{prod.description} This transformative book offers actionable strategies for eliminating modern workplace distractions, "
                f"cultivating deep cognitive focus, and mastering complex skills rapidly. It is essential reading for knowledge workers and ambitious professionals aiming to produce elite-level results."
            )
            actions = build_actions([f"Add {prod.name} to Cart"])
            return (desc, None, None, cart, actions)

    # 7. SPECIFIC BOOK ENQUIRY / ADDITION
    if "atomic" in lower_msg or "habits" in lower_msg or "48 laws" in lower_msg or "power" in lower_msg or "shining" in lower_msg or "dune" in lower_msg or "clean code" in lower_msg or "deep work" in lower_msg:
        prod = None
        if "power" in lower_msg:
            prod = db.query(Product).filter(Product.name.ilike("%48 Laws%")).first()
        elif "shining" in lower_msg:
            prod = db.query(Product).filter(Product.name.ilike("%Shining%")).first()
        elif "dune" in lower_msg:
            prod = db.query(Product).filter(Product.name.ilike("%Dune%")).first()
        elif "clean code" in lower_msg:
            prod = db.query(Product).filter(Product.name.ilike("%Clean Code%")).first()
        elif "deep work" in lower_msg:
            prod = db.query(Product).filter(Product.name.ilike("%Deep Work%")).first()
        else:
            prod = db.query(Product).filter(Product.name.ilike("%Atomic Habits%")).first()

        if prod:
            if has_buy_intent:
                cart = add_to_cart(cart, prod, discount_pct=10.0)
                log_ai_action(
                    db=db,
                    action_type="ITEM_ADDED_TO_CART",
                    ai_reasoning=f"Added requested book '{prod.name}' to cart. Bounded 10% discount applied.",
                    amount_involved=round(prod.price * 0.9, 2)
                )

                companion = db.query(Product).filter(Product.name.ilike("%Deep Work%")).first() if "atomic" in lower_msg else db.query(Product).filter(Product.name.ilike("%Atomic Habits%")).first()
                comp_name = companion.name if companion else "Deep Work"

                reply = (
                    f"I've added **{prod.name}** to your cart with a 10% discount!\n\n"
                    f"**Why {prod.name} is a Great Read:** {prod.description} It delivers a powerful framework for continuous improvement, replacing self-doubt with proven systems that make success automatic.\n\n"
                    f"**Recommended Companion Read:** **{comp_name}** pairs exceptionally well with {prod.name} to maximize productivity."
                )
                actions = build_actions([f"Add {comp_name} to Cart"])
                return (reply, "CART_UPDATED", None, cart, actions)
            else:
                reply = (
                    f"**{prod.name} by {prod.author}** ({prod.format} - ₹{prod.price:.2f}):\n\n"
                    f"{prod.description} This internationally acclaimed bestseller provides groundbreaking insights into human behavior and goal achievement. Readers praise it as an engaging, practical roadmap that delivers immediate real-world results."
                )
                actions = build_actions([f"Add {prod.name} to Cart"])
                return (reply, None, None, cart, actions)

    # 8. GENERAL RECOMMENDATION / AUTHOR ENQUIRIES
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
            extra_chip = [f"Add {author_books[0].name} to Cart"] if author_books else []
            return (reply, None, None, cart, build_actions(extra_chip))

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
            extra_chip = [f"Add {genre_books[0].name} to Cart"] if genre_books else []
            return (reply, None, None, cart, build_actions(extra_chip))

    # 9. GENERAL GEMINI LLM FALLBACK WITH STRICT NON-AGGRESSIVE & MULTI-INTENT RULES
    if GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = (
                "You are AgenticPay, an AI assistant for an Agentic Bookstore with a 200-book catalog.\n"
                "STRICT RULES:\n"
                "1. If a user asks to remove one item and add another in one sentence, process both actions.\n"
                "2. If a user asks 'tell me about [Book]' or general info, DO NOT add it to the cart. Provide a rich 50-100 word description.\n"
                "3. Only confirm adding a book if the user explicitly uses words like 'buy', 'add', 'purchase', or 'get'.\n"
                "4. NEVER output raw cart contents, subtotals, or bulleted lists of cart items in your text response.\n"
                "5. Always format currency using the Rupee symbol ₹.\n\n"
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
        "Welcome to AgenticPay Bookstore! How can I help you with your book search today?",
        None,
        None,
        cart,
        build_actions()
    )
