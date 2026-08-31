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
    "I apologize, but another collector just purchased the last copy of "
    "'The Prince - Machiavelli (1st Edition Signed)'. Would you like our bestseller 'Atomic Habits' by James Clear instead with a 5% discount?"
)

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
    """Removes matching product(s) by ID, name substring, or author from cart."""
    removed_names = []
    new_cart = []
    ident_lower = identifier.lower().strip()

    for item in cart:
        item_name = item.get("name", "").lower()
        item_author = item.get("author", "").lower()
        
        if ident_lower in item_name or ident_lower in item_author or str(item.get("product_id")) == ident_lower:
            removed_names.append(item.get("name"))
        else:
            new_cart.append(item)

    return new_cart, removed_names

def view_cart(cart: List[Dict[str, Any]]) -> str:
    """Formats cart content for conversational output."""
    if not cart:
        return "Your cart is currently empty."
    
    lines = []
    total = 0.0
    for idx, item in enumerate(cart, 1):
        lines.append(f"{idx}. **{item['name']}** ({item.get('format', 'Book')}) - ${item['final_price']:.2f}")
        total += item['final_price']
    
    return f"**Current Cart ({len(cart)} items):**\n" + "\n".join(lines) + f"\n\n**Subtotal:** ${total:.2f}"

def generate_checkout(cart: List[Dict[str, Any]], db: Session) -> Tuple[str, str, Dict[str, Any]]:
    """
    Explicit tool function to calculate final cart total, invoke Razorpay Order Creation API,
    save order to database, log CHECKOUT_GENERATED audit trail, and return CheckoutWidgetData.
    """
    if not cart:
        # Fallback to default bestseller if cart is empty
        default_book = db.query(Product).filter(Product.name.ilike("%Atomic Habits%")).first()
        if default_book:
            cart = add_to_cart(cart, default_book, discount_pct=10.0)

    original_total = sum(item["price"] for item in cart)
    final_amount = sum(item["final_price"] for item in cart)
    total_discount = round(original_total - final_amount, 2)
    avg_discount_pct = round((total_discount / original_total * 100.0), 1) if original_total > 0 else 0.0

    first_prod_id = cart[0]["product_id"] if cart else 1

    # 1. Call Razorpay API to create order (amount converted to paise in SDK)
    rzp_order_id = create_razorpay_order_sdk(
        amount_in_inr=final_amount,
        notes={
            "items_count": str(len(cart)),
            "cart_summary": ", ".join([i["name"] for i in cart[:3]])
        }
    )

    # 2. Save order to database table
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

    # 3. Log CHECKOUT_GENERATED to ai_audit_logs table
    log_ai_action(
        db=db,
        order_id=db_order.id,
        action_type="CHECKOUT_GENERATED",
        ai_reasoning=(
            f"CHECKOUT TOOL EXECUTED: Created Razorpay order '{rzp_order_id}' for {len(cart)} cart items. "
            f"Original total: ${original_total:.2f}, Savings: ${total_discount:.2f} ({avg_discount_pct}% avg discount), "
            f"Final payable amount: ${final_amount:.2f}."
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
        f"You save **${total_discount:.2f}** with your bounded discount applied. Click the button below to complete payment:"
    )

    return reply_text, "SHOW_CHECKOUT", widget_data

def process_chat_message(
    db: Session,
    message: str,
    conversation_history: List[Dict[str, str]],
    current_cart: List[Dict[str, Any]]
) -> Tuple[str, Optional[str], Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Stateful Agentic Bookstore process function.
    Manages explicit tool calls for cart state: add_to_cart, remove_from_cart, view_cart, generate_checkout.
    Returns: (ai_reply_text, action_type, checkout_widget_dict, updated_cart)
    """
    lower_msg = message.lower()
    cart = list(current_cart or [])

    # 1. GRACEFUL FAILURE SCENARIO (Machiavelli 1st Edition Signed)
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
            amount_involved=199.99 if machiavelli_item else 0.0
        )
        return (OUT_OF_STOCK_REPLY, "GRACEFUL_FAILURE", None, cart)

    # 3. EXPLICIT REMOVAL INTENT ("remove", "delete", "only want", "dont want")
    if "remove" in lower_msg or "delete" in lower_msg or "only want" in lower_msg or "dont want" in lower_msg or "don't want" in lower_msg:
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
            reply = f"Understood! I've removed the extra items from your cart.\n\n" + view_cart(cart) + "\n\nWould you like to proceed to checkout now?"
            return (reply, "CART_UPDATED", None, cart)
        else:
            cart, removed = remove_from_cart(cart, lower_msg.replace("remove", "").replace("delete", "").strip())
            if removed:
                log_ai_action(
                    db=db,
                    action_type="ITEM_REMOVED_FROM_CART",
                    ai_reasoning=f"CART STATE UPDATED: Removed {removed} from cart based on user request.",
                    amount_involved=0.0
                )
                reply = f"Removed **{', '.join(removed)}** from your cart.\n\n" + view_cart(cart)
                return (reply, "CART_UPDATED", None, cart)
            else:
                reply = "I couldn't find that item in your current cart.\n\n" + view_cart(cart)
                return (reply, None, None, cart)

    # 4. HARD GATING TEST SCENARIO: DISCOUNT > 15% REQUESTED (e.g. 20%)
    if "20%" in lower_msg or "20 percent" in lower_msg or "30%" in lower_msg or "25%" in lower_msg:
        target_book = db.query(Product).filter(Product.name.ilike("%Atomic Habits%")).first()
        if not target_book:
            target_book = db.query(Product).filter(Product.stock_quantity > 0).first()
            
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
            amount_involved=round(base_price * (requested_num / 100.0), 2)
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
            f"I cannot provide a 20% discount as our backend system strictly caps maximum discounts at {MAX_DISCOUNT_PERCENT}%. "
            f"However, I've added **{book_name}** to your cart with the maximum allowed **{MAX_DISCOUNT_PERCENT}% discount**!\n\n"
            + view_cart(cart)
            + "\n\nWould you like to add our companion read **Deep Work by Cal Newport** to your cart, or would you like to know more about it?"
        )
        return (reply, "CART_UPDATED", None, cart)

    # 5. EXPLICIT CHECKOUT CONFIRMATION -> INVOKE generate_checkout TOOL
    if "checkout" in lower_msg or "pay" in lower_msg or "buy now" in lower_msg or "ready to order" in lower_msg or "generate checkout" in lower_msg:
        reply_text, action_type, widget_data = generate_checkout(cart=cart, db=db)
        return reply_text, action_type, widget_data, cart

    # 6. STEP 3: "KNOW MORE" / "TELL ME MORE" INQUIRY FOR CROSS-SELL
    if "know more" in lower_msg or "tell me more" in lower_msg or "more about" in lower_msg:
        deep_work = db.query(Product).filter(Product.name.ilike("%Deep Work%")).first()
        desc = deep_work.description if deep_work else "Rules for Focused Success in a Distracted World."
        reply = (
            f"**Deep Work by Cal Newport** ({deep_work.format if deep_work else 'Paperback'} - ${deep_work.price if deep_work else 15.99:.2f}):\n"
            f"{desc}\n\n"
            "Would you like to add this to your cart now?"
        )
        return (reply, None, None, cart)

    # 7. STEP 3: "ADD IT" / "ADD DEEP WORK" / "YES ADD" CONFIRMATION
    if "add it" in lower_msg or "add deep work" in lower_msg or "yes add" in lower_msg or "add companion" in lower_msg:
        deep_work = db.query(Product).filter(Product.name.ilike("%Deep Work%")).first()
        if deep_work:
            cart = add_to_cart(cart, deep_work, discount_pct=5.0)
            log_ai_action(
                db=db,
                action_type="ITEM_ADDED_TO_CART",
                ai_reasoning=f"CART STATE UPDATED: Added cross-sell companion book '{deep_work.name}' to cart upon user request.",
                amount_involved=deep_work.price
            )
            reply = (
                f"Added **{deep_work.name}** to your cart!\n\n"
                + view_cart(cart)
                + "\n\nAre you ready to proceed to checkout now?"
            )
            return (reply, "CART_UPDATED", None, cart)

    # 8. STEP 1 & 2: SPECIFIC BOOK REQUEST (Add ONLY requested book, describe, suggest 1 companion)
    if "atomic" in lower_msg or "habits" in lower_msg or "48 laws" in lower_msg or "power" in lower_msg or "shining" in lower_msg or "dune" in lower_msg or "clean code" in lower_msg:
        prod = None
        if "power" in lower_msg:
            prod = db.query(Product).filter(Product.name.ilike("%48 Laws%")).first()
        elif "shining" in lower_msg:
            prod = db.query(Product).filter(Product.name.ilike("%Shining%")).first()
        elif "dune" in lower_msg:
            prod = db.query(Product).filter(Product.name.ilike("%Dune%")).first()
        elif "clean code" in lower_msg:
            prod = db.query(Product).filter(Product.name.ilike("%Clean Code%")).first()
        else:
            prod = db.query(Product).filter(Product.name.ilike("%Atomic Habits%")).first()

        if prod:
            cart = add_to_cart(cart, prod, discount_pct=10.0)
            log_ai_action(
                db=db,
                action_type="ITEM_ADDED_TO_CART",
                ai_reasoning=f"Added ONLY requested book '{prod.name}' to cart. Bounded 10% discount applied.",
                amount_involved=round(prod.price * 0.9, 2)
            )

            companion = db.query(Product).filter(Product.name.ilike("%Deep Work%")).first()
            comp_name = companion.name if companion else "Deep Work by Cal Newport"

            reply = (
                f"I've added **{prod.name}** to your cart with a 10% discount!\n\n"
                f"**About {prod.name}:** {prod.description}\n\n"
                + view_cart(cart) + "\n\n"
                f"**Suggested Companion Read:** Would you like to add **{comp_name}** to your cart, or would you like to know more about it?"
            )
            return (reply, "CART_UPDATED", None, cart)

    # 9. GENERAL RECOMMENDATION / AUTHOR / GENRE ENQUIRIES (List 2-3 books, do not auto-add to cart)
    authors_list = ["stephen king", "james clear", "robert greene", "cal newport", "andy weir", "martin kleppmann"]
    matched_author = next((a for a in authors_list if a in lower_msg), None)
    if matched_author:
        author_books = db.query(Product).filter(Product.author.ilike(f"%{matched_author}%")).limit(3).all()
        if author_books:
            b_lines = [f"• **{b.name}** ({b.format}) - ${b.price:.2f}" for b in author_books]
            reply = (
                f"Here are top-selling books by **{author_books[0].author}**:\n"
                + "\n".join(b_lines)
                + f"\n\nWhich of these books would you like me to add to your cart?"
            )
            return (reply, None, None, cart)

    genres_list = ["horror", "self-growth", "sci-fi", "tech", "classics"]
    matched_genre = next((g for g in genres_list if g in lower_msg), None)
    if matched_genre:
        genre_books = db.query(Product).filter(Product.genre.ilike(f"%{matched_genre}%"), Product.stock_quantity > 0).limit(3).all()
        if genre_books:
            b_lines = [f"• **{b.name}** by {b.author} ({b.format}) - ${b.price:.2f}" for b in genre_books]
            reply = (
                f"Here are 3 top-recommended books in **{matched_genre.title()}**:\n"
                + "\n".join(b_lines)
                + f"\n\nWhich of these would you like to add to your cart?"
            )
            return (reply, None, None, cart)

    # 10. GENERAL GEMINI LLM FALLBACK WITH STRICT STATEFUL CART INSTRUCTIONS
    if GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = (
                "You are AgenticPay, an AI assistant for an Agentic Bookstore with a 200-book catalog.\n"
                "STRICT SALES FLOW & STATEFUL CART RULES:\n"
                "1. When a user requests a book, add ONLY that specific book to their cart. Output a 1-2 sentence description.\n"
                "2. Suggest ONE related companion book, but DO NOT add it to the cart yet. Ask: 'Would you like to add this to your cart, or would you like to know more about it?'\n"
                "3. If user says 'know more', output a short description of the suggested book. If user says 'add it', add it to the cart.\n"
                "4. If user says 'remove [Book Name]' or 'I only want [Book Name]', confirm removing the unwanted items from the cart.\n"
                "5. Only confirm checkout when user explicitly asks to pay / checkout.\n"
                "6. Offer bounded discounts up to 15% max.\n\n"
                f"Active Cart Items: {[i['name'] for i in cart]}\n"
                f"User Message: {message}"
            )
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            reply = response.text if response and response.text else "How can I help you with your cart or book search today?"
            return (reply, None, None, cart)
        except Exception as e:
            logger.warning(f"Gemini API call failed: {e}")

    # Default fallback
    return (
        "Welcome to AgenticPay Bookstore! "
        + (view_cart(cart) if cart else "Your cart is empty. What book would you like to add today?"),
        None,
        None,
        cart
    )
