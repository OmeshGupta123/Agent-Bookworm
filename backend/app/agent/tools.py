# app/agent/tools.py
# ---------------------------------------------------------------------------
# Pure Python tool functions — the real implementations that Gemini can call.
# Each function is self-contained, testable, and has no dependency on the
# Gemini SDK. The runner dispatches Gemini's function_call responses here.
# ---------------------------------------------------------------------------
import logging
import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.config import MAX_DISCOUNT_PERCENT, HUMAN_GATE_THRESHOLD, RAZORPAY_KEY_ID
from app.models import Order, Product
from app.services.audit_service import log_ai_action, log_tool_audit
from app.services.razorpay_service import create_razorpay_order_sdk, create_razorpay_payment_link
from app.agent.catalog_data import TYPO_CORRECTIONS, VIBE_GENRE_MAP

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _apply_typos(text: str) -> str:
    words = text.split()
    return " ".join(TYPO_CORRECTIONS.get(w, w) for w in words)


def _strip_padding(text: str, extra_pads: list[str] | None = None) -> str:
    """Remove common filler words to isolate the meaningful search term."""
    pads = [
        "remove", "delete", "add", "buy", "purchase", "get", "replace", "swap",
        "with", "for", "to", "and", "cart", "from", "book", "books", "copy",
        "please", "some", "show", "me", "find", "discount", "discounts", "can",
        "give", "price", "is", "high", "percent", "off", "deal", "on",
        "recommend", "recommendation", "recommendations", "good", "top", "best",
        "list",
    ]
    if extra_pads:
        pads.extend(extra_pads)
    for pad in pads:
        text = re.sub(rf'\b{re.escape(pad)}\b', '', text).strip()
    return text


def _safe_int(value: Any, default: int = 1) -> int:
    """Parse an untrusted quantity without letting bad browser input crash chat."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Parse an untrusted monetary field without trusting it as a price."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def reconcile_cart(db: Session, raw_cart: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Rebuild a browser-supplied cart from catalog records.

    Cart state is sent by the browser on every chat request. Prices, titles,
    stock labels and discounts in that payload are therefore only hints, never
    a source of truth. The helper accepts only catalog identities, reads the
    canonical price/details from the database, clamps quantity and merchant
    discount policy, and coalesces duplicate lines.
    """
    normalized: list[dict[str, Any]] = []
    for raw_item in raw_cart or []:
        if not isinstance(raw_item, dict):
            continue

        product = None
        product_id = raw_item.get("product_id", raw_item.get("id"))
        try:
            if product_id is not None:
                product = db.query(Product).filter(Product.id == int(product_id)).first()
        except (TypeError, ValueError):
            product = None

        # Preserve carts from older frontend versions, but resolve each name to
        # a live catalog product before it can affect a monetary calculation.
        if not product and raw_item.get("name"):
            product = find_product(db, str(raw_item["name"]))
        if not product:
            continue

        quantity = max(1, min(_safe_int(raw_item.get("quantity"), 1), 50))
        discount_pct = max(
            0.0,
            min(_safe_float(raw_item.get("discount_percentage"), 0.0), MAX_DISCOUNT_PERCENT),
        )
        cart_add(normalized, product, discount_pct=discount_pct, quantity=quantity)

    return normalized


# ---------------------------------------------------------------------------
# Catalog search tools
# ---------------------------------------------------------------------------

def find_product(db: Session, query: str) -> Product | None:
    """
    Single-item fuzzy catalog lookup.
    Used for precise add/remove actions where we need exactly one book.
    Preserves numbers so 'The 48 Laws of Power' resolves correctly.
    """
    if not query or len(query.strip()) < 2:
        return None

    clean = query.lower().strip()
    # Strip common punctuation (e.g. question marks, commas, quotes)
    clean = re.sub(r'[?!.,;:()"\']', ' ', clean).strip()
    # Strip common action/padding words but NOT numbers
    clean = _strip_padding(clean)
    clean = _apply_typos(clean)

    if not clean or len(clean) < 2:
        return None

    # 1. Exact substring match on title
    prod = db.query(Product).filter(Product.name.ilike(f"%{clean}%")).first()
    if prod:
        return prod

    # 2. Multi-keyword matching: score candidates by how many keywords they match
    _stop = {
        "the", "and", "for", "with", "from", "item", "some", "this", "book", "books",
        "vol", "volume", "that", "have", "what", "which", "will", "can", "get", "give", "you", "out"
    }
    raw_keywords = [re.sub(r'\W+', '', w) for w in clean.split()]
    keywords = [w for w in raw_keywords if len(w) >= 3 and w not in _stop]

    if keywords:
        candidates = db.query(Product).all()
        best_prod = None
        best_score = 0
        for p in candidates:
            p_name_lower = p.name.lower()
            score = sum(1 for kw in keywords if kw in p_name_lower)
            if score > best_score:
                best_score = score
                best_prod = p

        if best_prod and best_score >= min(2, len(keywords)):
            return best_prod

    # 3. Author name match
    for kw in sorted(keywords, key=len, reverse=True):
        prod = db.query(Product).filter(Product.author.ilike(f"%{kw}%")).first()
        if prod:
            return prod

    return None


def search_catalog(
    db: Session,
    query: str = "",
    theme: str = "",
    limit: int = 5,
    fallback_to_catalog: bool = True,
) -> list[dict[str, Any]]:
    """
    Multi-item catalog search across genres, vibes, titles, authors, descriptions.
    Returns up to *limit* in-stock products with base_price and max_discount.
    """
    search_term = query or theme or ""
    clean = search_term.lower().strip()
    clean = _strip_padding(clean)
    clean = _apply_typos(clean)

    results: list[Product] = []
    seen: set[int] = set()

    def add_prods(prods: list[Product]) -> None:
        for p in prods:
            if p.id not in seen and p.stock_quantity > 0:
                results.append(p)
                seen.add(p.id)

    if not clean:
        add_prods(db.query(Product).filter(Product.stock_quantity > 0).limit(limit).all())
    else:
        words = clean.split()

        # 1. Vibe keyword -> genre
        mapped_genre = VIBE_GENRE_MAP.get(clean)
        if mapped_genre:
            add_prods(db.query(Product).filter(Product.genre.ilike(f"%{mapped_genre}%")).all())
        for kw in words:
            if len(kw) >= 3:
                mg = VIBE_GENRE_MAP.get(kw)
                if mg:
                    add_prods(db.query(Product).filter(Product.genre.ilike(f"%{mg}%")).all())

        # 2. Genre field direct match
        if clean:
            add_prods(db.query(Product).filter(Product.genre.ilike(f"%{clean}%")).all())
            add_prods(db.query(Product).filter(Product.name.ilike(f"%{clean}%")).all())
            add_prods(db.query(Product).filter(Product.author.ilike(f"%{clean}%")).all())
            add_prods(db.query(Product).filter(Product.description.ilike(f"%{clean}%")).all())

        # 3. Title, author and description keyword matches. Author matching is
        # important for conversational queries such as "What else has Stephen
        # King written?", where the full sentence is not a title.
        for kw in words:
            if len(kw) >= 3:
                add_prods(db.query(Product).filter(Product.name.ilike(f"%{kw}%")).all())
                add_prods(db.query(Product).filter(Product.author.ilike(f"%{kw}%")).all())
                add_prods(db.query(Product).filter(Product.description.ilike(f"%{kw}%")).all())

        # 4. Fallback
        if not results and fallback_to_catalog:
            add_prods(db.query(Product).filter(Product.stock_quantity > 0).limit(limit).all())

    prods_out = [
        {
            "id": p.id,
            "title": p.name,
            "name": p.name,
            "author": p.author,
            "genre": p.genre,
            "format": p.format,
            "base_price": p.price,
            "price": p.price,
            "currency": "INR",
            "max_discount": getattr(p, "max_discount", MAX_DISCOUNT_PERCENT),
            "stock_quantity": p.stock_quantity,
            "description": p.description,
            "image_url": p.image_url,
        }
        for p in results[:limit]
    ]

    log_tool_audit(
        db=db,
        tool_name="search_catalog",
        input_params={"query": query, "theme": theme, "limit": limit},
        output_result={"count": len(prods_out), "results": [p["title"] for p in prods_out]},
        status="SUCCESS",
        ai_reasoning=f"Catalog search for query='{search_term}' returned {len(prods_out)} items."
    )

    return prods_out


# ---------------------------------------------------------------------------
# Cart tools
# ---------------------------------------------------------------------------

def is_in_cart(cart: list[dict[str, Any]], product_name: str) -> bool:
    name_lower = product_name.lower().strip()
    return any(
        name_lower in item.get("name", "").lower() or
        item.get("name", "").lower() in name_lower
        for item in cart
    )


def cart_add(
    cart: list[dict[str, Any]],
    product: Product,
    discount_pct: float = 0.0,
    quantity: int = 1,
    ai_reasoning: str = "",
    db: Session | None = None,
    allow_increment: bool = True,
) -> list[dict[str, Any]]:
    """
    Adds product to cart (or increments quantity if already present and allow_increment is True).
    Applies the merchant discount cap automatically.
    Logs explainable audit entries to audit_logs if db session is provided.
    """
    quantity = max(1, min(_safe_int(quantity, 1), 50))
    capped = max(0.0, min(_safe_float(discount_pct, 0.0), MAX_DISCOUNT_PERCENT))
    disc_amount = round(product.price * (capped / 100.0), 2)
    final_price = round(product.price - disc_amount, 2)

    existing = next(
        (i for i in cart if i.get("product_id") == product.id or
         i.get("name", "").lower() == product.name.lower()),
        None,
    )
    if existing:
        if allow_increment:
            existing["quantity"] = existing.get("quantity", 1) + quantity
        existing["discount_percentage"] = capped
        existing["discount_amount"] = disc_amount
        existing["final_price"] = final_price
    else:
        cart.append({
            "product_id": product.id,
            "name": product.name,
            "author": product.author,
            "format": product.format,
            "price": product.price,
            "quantity": quantity,
            "discount_percentage": capped,
            "discount_amount": disc_amount,
            "final_price": final_price,
            "image_url": product.image_url,
        })

    if db:
        explanation = ai_reasoning or f"Added '{product.name}' (qty={quantity}, disc={capped}%)."
        amount = round(final_price * quantity, 2)
        log_ai_action(
            db=db,
            action_type="ITEM_ADDED_TO_CART",
            ai_reasoning=explanation,
            amount_involved=amount,
        )
        log_tool_audit(
            db=db,
            tool_name="add_to_cart",
            input_params={"product_id": product.id, "discount_pct": discount_pct, "quantity": quantity, "ai_reasoning": ai_reasoning},
            output_result={"added": product.name, "final_price": final_price, "quantity": quantity},
            status="SUCCESS",
            ai_reasoning=explanation,
            amount_involved=amount,
        )

    return cart


def cart_remove(
    cart: list[dict[str, Any]],
    identifier: str,
    ai_reasoning: str = "",
    db: Session | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Removes items from cart by name/ID using fuzzy matching.
    Returns (new_cart, list_of_removed_names).
    Logs explainable audit entries to audit_logs if db session is provided.
    """
    if not cart or not identifier:
        return cart, []

    clean = identifier.lower().strip()
    clean = _strip_padding(clean, extra_pads=["from my cart", "from cart", "the book", "copy of"])
    words = clean.split()
    corrected = [TYPO_CORRECTIONS.get(w, w) for w in words]
    clean = " ".join(corrected)

    removed: list[str] = []
    new_cart: list[dict[str, Any]] = []

    for item in cart:
        item_name = item.get("name", "").lower()
        item_id = str(item.get("product_id", ""))
        is_match = False

        if clean:
            if clean in item_name or item_name in clean or item_id == clean:
                is_match = True
            else:
                item_words = set(item_name.split())
                query_words = [w for w in clean.split() if len(w) >= 3]
                if any(kw in item_words or any(kw in iw for iw in item_words) for kw in query_words):
                    is_match = True

        if is_match:
            removed.append(item.get("name", ""))
        else:
            new_cart.append(item)

    if db and removed:
        explanation = ai_reasoning or f"Removed {removed} from cart based on user request."
        log_ai_action(
            db=db,
            action_type="ITEM_REMOVED_FROM_CART",
            ai_reasoning=explanation,
            amount_involved=0.0,
        )
        log_tool_audit(
            db=db,
            tool_name="remove_from_cart",
            input_params={"identifier": identifier, "ai_reasoning": ai_reasoning},
            output_result={"removed": removed},
            status="SUCCESS",
            ai_reasoning=explanation,
            amount_involved=0.0,
        )

    return new_cart, removed


def get_cart_summary(cart: list[dict[str, Any]]) -> dict[str, Any]:
    """Returns a structured summary of the current cart for display/Gemini context."""
    if not cart:
        return {"empty": True, "items": [], "item_count": 0, "original_total": 0.0, "final_total": 0.0, "savings": 0.0}

    items_out = []
    orig = 0.0
    final = 0.0
    for item in cart:
        qty = item.get("quantity", 1)
        p = item.get("price", 0.0)
        fp = item.get("final_price", p)
        disc = item.get("discount_percentage", 0.0)
        orig += p * qty
        final += fp * qty
        items_out.append({
            "product_id": item.get("product_id"),
            "id": item.get("product_id"),
            "name": item.get("name"),
            "author": item.get("author"),
            "quantity": qty,
            "unit_price": p,
            "price": p,
            "final_price": fp,
            "discount_percentage": disc,
            "subtotal": round(fp * qty, 2),
        })

    return {
        "empty": False,
        "items": items_out,
        "item_count": sum(i["quantity"] for i in items_out),
        "original_total": round(orig, 2),
        "final_total": round(final, 2),
        "savings": round(max(0.0, orig - final), 2),
    }


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Bundle Discovery tool
# ---------------------------------------------------------------------------

def analyze_and_bundle(
    db: Session,
    cart: list[dict[str, Any]],
    theme: str,
    max_budget: float | None = None,
) -> list[dict[str, Any]]:
    """
    Analyzes the user's current cart and chat context to curate a high-margin,
    2-to-3 book bundle.
    1. Extracts all product_ids currently in the cart to NEVER recommend books already held.
    2. Uses theme string to perform a fuzzy query against genre, description, and name fields.
    3. Filters for items where stock_quantity > 0.
    4. Sorts/prioritizes results by highest price (to maximize merchant revenue) while
       keeping the combined total under max_budget if provided.
    5. Returns top 2-3 items as a list of dicts with id, name, author, price, description.
    """
    # 1. Extract all product_ids currently in the cart to ensure no duplicates
    cart_ids = {item.get("product_id") for item in (cart or []) if item.get("product_id")}
    cart_names = [item.get("name", "").lower() for item in (cart or []) if item.get("name")]

    clean_theme = (theme or "").lower().strip()
    clean_theme = _strip_padding(clean_theme)
    clean_theme = _apply_typos(clean_theme)

    seen: set[int] = set()
    candidates: list[Product] = []

    def eligible(p: Product) -> bool:
        if not p or p.stock_quantity <= 0:
            return False
        if p.id in cart_ids or p.id in seen:
            return False
        pl = p.name.lower()
        if any(cn in pl or pl in cn for cn in cart_names):
            return False
        return True

    def add_prods(prods: list[Product]) -> None:
        for p in prods:
            if eligible(p):
                candidates.append(p)
                seen.add(p.id)

    # 2. Fuzzy query against genre, description, and name fields using theme
    if clean_theme:
        words = clean_theme.split()

        # Vibe / genre mapping check
        mapped_genre = VIBE_GENRE_MAP.get(clean_theme)
        if mapped_genre:
            add_prods(db.query(Product).filter(Product.genre.ilike(f"%{mapped_genre}%")).all())
        for kw in words:
            if len(kw) >= 3:
                mg = VIBE_GENRE_MAP.get(kw)
                if mg:
                    add_prods(db.query(Product).filter(Product.genre.ilike(f"%{mg}%")).all())

        # Direct fuzzy matches across genre, name, description, author
        add_prods(db.query(Product).filter(Product.genre.ilike(f"%{clean_theme}%")).all())
        add_prods(db.query(Product).filter(Product.name.ilike(f"%{clean_theme}%")).all())
        add_prods(db.query(Product).filter(Product.description.ilike(f"%{clean_theme}%")).all())
        add_prods(db.query(Product).filter(Product.author.ilike(f"%{clean_theme}%")).all())

        for kw in words:
            if len(kw) >= 3:
                add_prods(db.query(Product).filter(Product.genre.ilike(f"%{kw}%")).all())
                add_prods(db.query(Product).filter(Product.name.ilike(f"%{kw}%")).all())
                add_prods(db.query(Product).filter(Product.description.ilike(f"%{kw}%")).all())

    # Fallback to in-stock catalog if fewer than 3 candidates
    if len(candidates) < 3:
        add_prods(db.query(Product).filter(Product.stock_quantity > 0).all())

    # 3 & 4. Sort by highest price (to maximize merchant revenue)
    candidates.sort(key=lambda p: (p.price, p.stock_quantity), reverse=True)

    # Select 2-3 items keeping the combined total under max_budget if provided
    selected: list[Product] = []
    current_total = 0.0

    for p in candidates:
        if max_budget is not None and max_budget > 0:
            if current_total + p.price <= max_budget:
                selected.append(p)
                current_total += p.price
            elif not selected and p.price <= max_budget:
                selected.append(p)
                current_total += p.price
        else:
            selected.append(p)

        if len(selected) >= 3:
            break

    # If strict budget filtering left us with 0 items, pick single cheapest item under budget
    if not selected and candidates and max_budget is not None and max_budget > 0:
        cheapest = min(candidates, key=lambda p: p.price)
        if cheapest.price <= max_budget:
            selected = [cheapest]

    if not selected and not (max_budget is not None and max_budget > 0):
        selected = candidates[:3]

    # 5. Return list of dictionaries containing id, name, author, price, and description
    bundle_items = [
        {
            "id": p.id,
            "name": p.name,
            "author": p.author,
            "price": p.price,
            "description": p.description,
        }
        for p in selected
    ]

    log_tool_audit(
        db=db,
        tool_name="analyze_and_bundle",
        input_params={"theme": theme, "max_budget": max_budget},
        output_result={"count": len(bundle_items), "items": [b["name"] for b in bundle_items]},
        status="SUCCESS",
        ai_reasoning=f"Curated high-margin bundle of {len(bundle_items)} books for theme='{theme}', max_budget={max_budget}.",
        amount_involved=round(sum(b["price"] for b in bundle_items), 2),
    )

    return bundle_items


# ---------------------------------------------------------------------------
# Checkout & Payment Link tools
# ---------------------------------------------------------------------------

def draft_checkout(
    db: Session,
    buyer_email: str,
    items: list[dict[str, Any]],
    discount_pct: float = 0.0,
    ai_reasoning: str = "",
    reasoning: str = "",
) -> dict[str, Any]:
    """
    Drafts checkout and validates constraints:
    1. Bounded Constraint: discount_pct above the configured merchant cap is blocked.
    2. Backend Math: Calculates pre_discount_total, discount_amount, final_total, amount_in_paise.
    3. Human Gate: If pre_discount_total > 100,000 -> saves order as PENDING_APPROVAL.
    4. Razorpay Call / Mock Failure: If buyer_email == 'fail@test.com' -> simulates 500 error.
    5. Creates Razorpay Payment Link and returns short_url.
    Every action is logged with explainable ai_reasoning to audit_logs table.
    """
    effective_reasoning = ai_reasoning or reasoning or ""

    # 1. Bounded Constraint Validation: configured merchant cap
    if discount_pct > MAX_DISCOUNT_PERCENT:
        err_msg = f"PolicyViolation: Max discount is {int(MAX_DISCOUNT_PERCENT)}%"
        log_tool_audit(
            db=db,
            tool_name="draft_checkout",
            input_params={"buyer_email": buyer_email, "items": items, "discount_pct": discount_pct, "ai_reasoning": effective_reasoning},
            output_result={"error": err_msg, "status": "BLOCKED"},
            status="BLOCKED",
            ai_reasoning=effective_reasoning or f"Blocked discount {discount_pct}% exceeding maximum allowed {int(MAX_DISCOUNT_PERCENT)}%",
            amount_involved=0.0
        )
        return {"error": err_msg, "status": "BLOCKED"}

    # 2. Strict Backend Math Calculation (No LLM math allowed)
    item_details = []
    pre_discount_total = 0.0

    for itm in (items or []):
        prod_id = itm.get("id") or itm.get("product_id")
        qty = int(itm.get("qty") or itm.get("quantity", 1))

        prod = None
        if prod_id:
            prod = db.query(Product).filter(Product.id == prod_id).first()
        if not prod and "name" in itm:
            prod = find_product(db, itm["name"])

        if not prod:
            return {"error": f"Product with ID/query '{prod_id or itm.get('name')}' not found in catalog.", "status": "FAILED"}

        item_subtotal = round(prod.price * qty, 2)
        pre_discount_total += item_subtotal
        item_details.append({
            "product_id": prod.id,
            "id": prod.id,
            "name": prod.name,
            "author": prod.author,
            "price": prod.price,
            "quantity": qty,
            "qty": qty,
            "subtotal": item_subtotal,
            "stock": prod.stock_quantity
        })

    if not item_details:
        return {"error": "No valid items provided for checkout.", "status": "FAILED"}

    pre_discount_total = round(pre_discount_total, 2)
    discount_pct_clamped = max(0.0, min(discount_pct, MAX_DISCOUNT_PERCENT))
    discount_amount = round(pre_discount_total * (discount_pct_clamped / 100.0), 2)
    final_total = round(pre_discount_total - discount_amount, 2)
    amount_in_paise = int(round(final_total * 100))

    # 3. Human Gate Constraint: Pre-discount total > ₹1,00,000
    if pre_discount_total > HUMAN_GATE_THRESHOLD:
        db_order = Order(
            total_amount=final_total,
            pre_discount_total=pre_discount_total,
            discount_percentage=discount_pct_clamped,
            status="PENDING_APPROVAL",
            buyer_email=buyer_email,
            product_id=item_details[0]["product_id"] if item_details else None,
        )
        db.add(db_order)
        db.commit()
        db.refresh(db_order)

        res_payload = {
            "status": "PENDING_APPROVAL",
            "order_id": db_order.id,
            "pre_discount_total": pre_discount_total,
            "final_total": final_total,
            "message": (
                f"Order total of INR {pre_discount_total:,.2f} exceeds the INR 1,00,000 human gate threshold. "
                "The order has been saved with status PENDING_APPROVAL. "
                "A human manager will review this bulk order."
            )
        }
        log_tool_audit(
            db=db,
            tool_name="draft_checkout",
            input_params={"buyer_email": buyer_email, "items": items, "discount_pct": discount_pct, "ai_reasoning": effective_reasoning},
            output_result=res_payload,
            status="PENDING_APPROVAL",
            ai_reasoning=effective_reasoning or f"HUMAN_GATE_TRIGGERED: Pre-discount total INR {pre_discount_total:,.2f} > INR 1,00,000. Queued for human manager approval.",
            amount_involved=final_total,
            order_id=db_order.id
        )
        return res_payload

    # For standard retail orders (<= ₹1,00,000), verify instant inventory stock
    for item_info in item_details:
        if item_info["stock"] < item_info["quantity"]:
            return {"error": f"Product '{item_info['name']}' has insufficient stock (available: {item_info['stock']}).", "status": "FAILED"}

    # 4. Mock Failure & Payment Link API Call
    try:
        plink_data = create_razorpay_payment_link(
            amount_in_inr=final_total,
            buyer_email=buyer_email,
            description=f"Agentic Bookstore Checkout - {len(item_details)} items",
            notes={"buyer_email": buyer_email, "ai_reasoning": effective_reasoning}
        )
    except Exception as e:
        err_str = f"Razorpay API Error: {str(e)}"
        log_tool_audit(
            db=db,
            tool_name="draft_checkout",
            input_params={"buyer_email": buyer_email, "items": items, "discount_pct": discount_pct, "ai_reasoning": effective_reasoning},
            output_result={"error": err_str, "status": "FAILED"},
            status="FAILED",
            ai_reasoning=effective_reasoning or f"Payment link creation failed: {e}. Graceful failure handled.",
            amount_involved=final_total
        )
        return {
            "error": "Payment gateway temporarily unavailable (simulated 500 error). Cart saved safely.",
            "status": "FAILED",
            "gateway_error": str(e)
        }

    # 5. Success Order Persistence & Audit Log
    db_order = Order(
        razorpay_order_id=plink_data.get("id"),
        payment_link=plink_data.get("short_url"),
        buyer_email=buyer_email,
        total_amount=final_total,
        pre_discount_total=pre_discount_total,
        discount_percentage=discount_pct_clamped,
        status="pending",
        product_id=item_details[0]["product_id"] if item_details else None,
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)

    result = {
        "status": "SUCCESS",
        "order_id": db_order.id,
        "razorpay_order_id": plink_data.get("id"),
        "payment_link": plink_data.get("short_url"),
        "short_url": plink_data.get("short_url"),
        "amount": final_total,
        "amount_in_paise": amount_in_paise,
        "pre_discount_total": pre_discount_total,
        "discount_pct": discount_pct_clamped,
        "currency": "INR",
        "items": item_details
    }

    log_tool_audit(
        db=db,
        tool_name="draft_checkout",
        input_params={"buyer_email": buyer_email, "items": items, "discount_pct": discount_pct, "ai_reasoning": effective_reasoning},
        output_result=result,
        status="SUCCESS",
        ai_reasoning=effective_reasoning or f"Created payment link for {buyer_email}, amount INR {final_total:.2f}",
        amount_involved=final_total,
        order_id=db_order.id
    )

    return result


def initiate_checkout(
    cart: list[dict[str, Any]],
    db: Session,
) -> dict[str, Any]:
    """Create a bounded Razorpay checkout from the *canonical* current cart.

    This is intentionally deterministic: payment requests are financial side
    effects and should not depend on an LLM deciding what a malformed browser
    cart means. All displayed and charged totals come from live catalog data.
    """
    cart = reconcile_cart(db, cart)
    if not cart:
        return {
            "reply": "Your cart is empty. Add a book before starting checkout.",
            "action_type": "CART_EMPTY",
            "widget": None,
            "cart": cart,
        }

    unavailable = []
    for item in cart:
        product = db.query(Product).filter(Product.id == item["product_id"]).first()
        if not product or product.stock_quantity < item["quantity"]:
            available = product.stock_quantity if product else 0
            unavailable.append(f"{item['name']} (available: {available})")

    if unavailable:
        reason = "Cannot create checkout because inventory changed: " + ", ".join(unavailable)
        log_ai_action(
            db=db,
            action_type="STOCK_CHECK_FAILED",
            ai_reasoning=reason,
            amount_involved=0.0,
            log_metadata={"status": "Blocked", "purchased_items": [i["name"] for i in cart]},
        )
        return {
            "reply": f"I couldn't start checkout because {', '.join(unavailable)} is no longer available in the requested quantity. Your cart is unchanged.",
            "action_type": "CHECKOUT_BLOCKED",
            "widget": None,
            "cart": cart,
        }

    summary = get_cart_summary(cart)
    original_total = summary["original_total"]
    final_total = summary["final_total"]
    savings = summary["savings"]
    discount_pct = round((savings / original_total * 100.0), 2) if original_total else 0.0

    if original_total > HUMAN_GATE_THRESHOLD:
        approval_id = f"approval_{uuid.uuid4().hex[:14]}"
        db_order = Order(
            razorpay_order_id=approval_id,
            total_amount=final_total,
            pre_discount_total=original_total,
            status="PENDING_APPROVAL",
            product_id=cart[0]["product_id"],
            discount_percentage=discount_pct,
        )
        db.add(db_order)
        db.commit()
        db.refresh(db_order)
        log_ai_action(
            db=db,
            order_id=db_order.id,
            action_type="PENDING_APPROVAL",
            ai_reasoning=(
                f"Human approval required before payment: pre-discount total INR {original_total:.2f} "
                f"exceeds the merchant threshold of INR {HUMAN_GATE_THRESHOLD:.2f}."
            ),
            amount_involved=final_total,
            log_metadata={"status": "Pending approval", "purchased_items": [i["name"] for i in cart]},
        )
        return {
            "reply": "Your bulk order has been saved for a manager's approval before payment. We will not charge it until that review is complete.",
            "action_type": "PENDING_APPROVAL",
            "widget": None,
            "cart": cart,
        }

    try:
        rzp_order_id = create_razorpay_order_sdk(
            amount_in_inr=final_total,
            notes={
                "items_count": str(summary["item_count"]),
                "cart_summary": ", ".join(i["name"] for i in cart[:3]),
            },
        )
    except Exception as exc:
        logger.warning("Razorpay checkout creation failed: %s", exc)
        log_ai_action(
            db=db,
            action_type="PAYMENT_FAILED",
            ai_reasoning=f"Payment provider did not create an order; the cart was retained. Error: {exc}",
            amount_involved=final_total,
        )
        return {
            "reply": "I couldn't reach the payment gateway just now. Your cart is still saved; please try checkout again shortly.",
            "action_type": "PAYMENT_FAILED",
            "widget": None,
            "cart": cart,
        }

    db_order = Order(
        razorpay_order_id=rzp_order_id,
        total_amount=final_total,
        pre_discount_total=original_total,
        status="pending",
        product_id=cart[0]["product_id"],
        discount_percentage=discount_pct,
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)

    log_ai_action(
        db=db,
        order_id=db_order.id,
        action_type="CHECKOUT_GENERATED",
        ai_reasoning=(
            f"Created Razorpay order '{rzp_order_id}' from catalog-verified cart values: "
            f"INR {original_total:.2f} before discounts, INR {final_total:.2f} payable."
        ),
        amount_involved=final_total,
        log_metadata={
            "status": "Pending payment",
            "purchased_items": [i["name"] for i in cart],
            "order_id": rzp_order_id,
        },
    )

    widget = {
        "order_id": db_order.id,
        "razorpay_order_id": rzp_order_id,
        "razorpay_key_id": RAZORPAY_KEY_ID,
        "items": cart,
        "original_total": original_total,
        "total_discount": savings,
        "discount_percentage": discount_pct,
        "final_amount": final_total,
        "currency": "INR",
    }
    reply = (
        f"Your secure checkout is ready for **{summary['item_count']} item(s)**. "
        f"The payable amount is **INR {final_total:.2f}**."
    )
    return {"reply": reply, "action_type": "SHOW_CHECKOUT", "widget": widget, "cart": cart}
