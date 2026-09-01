import pytest
import json
from fastapi.testclient import TestClient
from app.main import app
from app.config import MAX_DISCOUNT_PERCENT
from app.models import Product
from app.services.ai_agent import add_to_cart, remove_from_cart

client = TestClient(app)

def make_mock_product(id=1, name="Atomic Habits", author="James Clear", price=20.0, stock=10):
    """Helper factory to create mock Product instances for testing."""
    p = Product()
    p.id = id
    p.name = name
    p.author = author
    p.format = "Paperback"
    p.price = price
    p.stock_quantity = stock
    p.genre = "Self-Growth"
    p.description = "An Easy & Proven Way to Build Good Habits & Break Bad Ones."
    p.image_url = "https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c"
    return p

# 1. Financial Guardrails Test
def test_financial_discount_cap_guardrail():
    """Verify that attempting to apply a 50% discount is intercepted and capped at 15%."""
    cart = []
    prod = make_mock_product(price=100.0)  # Base price ₹100.00
    
    # Attempt to apply an illegal 50% discount
    updated_cart = add_to_cart(cart, prod, discount_pct=50.0)
    
    assert len(updated_cart) == 1
    added_item = updated_cart[0]
    
    # Discount percentage must be capped at 15.0%
    assert added_item["discount_percentage"] == MAX_DISCOUNT_PERCENT
    assert added_item["discount_percentage"] == 15.0
    # Final price must be ₹100 - ₹15 = ₹85.00
    assert added_item["final_price"] == 85.0

# 2. Pre-LLM Guardrail Test
def test_pre_llm_word_count_guardrail():
    """Verify that user messages longer than 150 words are rejected before calling the LLM."""
    # Message with 151 words
    long_msg = "word " * 151
    response_long = client.post("/api/chat", json={"message": long_msg.strip(), "conversation_history": [], "cart": []})
    assert response_long.status_code == 200
    data_long = response_long.json()
    assert data_long["action_type"] == "MESSAGE_TOO_LONG"
    assert "under 150 words" in data_long["reply"]

    # Message with 149 words
    short_msg = "word " * 149
    response_short = client.post("/api/chat", json={"message": short_msg.strip(), "conversation_history": [], "cart": []})
    assert response_short.status_code == 200
    data_short = response_short.json()
    assert data_short["action_type"] != "MESSAGE_TOO_LONG"

# 3. Cart State Mutation Test
def test_cart_state_mutation():
    """Verify add_to_cart and remove_from_cart helper functions mutate the cart array correctly."""
    cart = []
    prod1 = make_mock_product(id=1, name="Atomic Habits")
    prod2 = make_mock_product(id=2, name="Deep Work")

    # Add items to cart
    cart = add_to_cart(cart, prod1, discount_pct=0.0)
    assert len(cart) == 1
    assert cart[0]["name"] == "Atomic Habits"

    cart = add_to_cart(cart, prod2, discount_pct=0.0)
    assert len(cart) == 2

    # Remove item from cart by name keyword
    cart, removed_names = remove_from_cart(cart, "Atomic Habits")
    assert len(cart) == 1
    assert removed_names == ["Atomic Habits"]
    assert cart[0]["name"] == "Deep Work"

    # Remove item by ID
    cart, removed_names = remove_from_cart(cart, "2")
    assert len(cart) == 0
    assert removed_names == ["Deep Work"]

# 4. Agent-Readable Catalog Endpoint Test
def test_agent_readable_catalog_schema():
    """Verify GET /api/agent-catalog.json returns 200 OK and valid AI-commerce schema keys."""
    response = client.get("/api/agent-catalog.json")
    assert response.status_code == 200
    
    data = response.json()
    assert data["store_name"] == "Agent Bookworm Bookstore"
    assert data["checkout_capability"] is True
    assert "catalog" in data
    assert len(data["catalog"]) > 0

    first_item = data["catalog"][0]
    required_keys = ["id", "title", "author", "price", "currency", "checkout_capability"]
    for key in required_keys:
        assert key in first_item, f"Missing required key '{key}' in catalog schema"
    assert first_item["checkout_capability"] is True

# 5. Conversational Memory & Affirmations Test
def test_conversational_memory_affirmations():
    """Verify that replying 'yes' or 'sure' to a recommendation adds the pitched books to cart."""
    from app.database import SessionLocal
    from app.services.ai_agent import process_chat_message

    db = SessionLocal()
    try:
        history = [
            {"role": "user", "content": "I have a budget of 200"},
            {
                "role": "assistant",
                "content": "As your **Budget Curator**, I have selected a custom bundle that fits right under your **₹200.00** budget:\n\n• **Atomic Habits** by James Clear (Paperback) - ₹16.99\n• **Deep Work** by Cal Newport (Paperback) - ₹15.99\n\nWould you like me to add these books to your cart?"
            }
        ]
        
        reply, action_type, widget, updated_cart, actions = process_chat_message(
            db=db,
            message="sure",
            conversation_history=history,
            current_cart=[]
        )

        assert action_type == "CART_UPDATED"
        assert len(updated_cart) >= 2
        assert "Atomic Habits" in [item["name"] for item in updated_cart]
        assert "Deep Work" in [item["name"] for item in updated_cart]
        assert "Awesome!" in reply or "added" in reply
    finally:
        db.close()

# 6. Audit Log Metadata & Payment Status Tests (Verified & Failed)
def test_payment_verified_audit_metadata():
    """Verify POST /api/orders/verify logs PAYMENT_VERIFIED with order_id, payment_id, status, and purchased_items array."""
    # Create order
    create_res = client.post("/api/orders/create", json={"product_id": 1, "discount_percentage": 0.0})
    assert create_res.status_code == 200
    rzp_order_id = create_res.json()["razorpay_order_id"]
    rzp_payment_id = "pay_test_verified_123"

    # Verify payment
    verify_res = client.post("/api/orders/verify", json={
        "razorpay_order_id": rzp_order_id,
        "razorpay_payment_id": rzp_payment_id,
        "razorpay_signature": "simulated_success_sig",
        "items": ["Atomic Habits", "Deep Work"]
    })
    assert verify_res.status_code == 200

    # Query audit logs
    audit_res = client.get("/api/audit-logs")
    assert audit_res.status_code == 200
    logs = audit_res.json()

    verified_log = next((l for l in logs if l.get("action_type") == "PAYMENT_VERIFIED" and l.get("log_metadata")), None)
    assert verified_log is not None, "Expected PAYMENT_VERIFIED audit log"

    meta = json.loads(verified_log["log_metadata"])
    assert meta["status"] == "Verified"
    assert meta["order_id"] == rzp_order_id
    assert meta["payment_id"] == rzp_payment_id
    assert isinstance(meta["purchased_items"], list)
    assert len(meta["purchased_items"]) == 2
    assert "Atomic Habits" in meta["purchased_items"]
    assert "Deep Work" in meta["purchased_items"]

def test_payment_failed_audit_metadata():
    """Verify POST /api/orders/fail logs PAYMENT_FAILED with order_id, failure_reason, status, and purchased_items."""
    # Create order
    create_res = client.post("/api/orders/create", json={"product_id": 1, "discount_percentage": 0.0})
    assert create_res.status_code == 200
    rzp_order_id = create_res.json()["razorpay_order_id"]

    # Trigger failure endpoint
    fail_res = client.post("/api/orders/fail", json={
        "razorpay_order_id": rzp_order_id,
        "reason": "User cancelled checkout modal",
        "items": ["Atomic Habits"]
    })
    assert fail_res.status_code == 200

    # Query audit logs
    audit_res = client.get("/api/audit-logs")
    assert audit_res.status_code == 200
    logs = audit_res.json()

    failed_log = next((l for l in logs if l.get("action_type") == "PAYMENT_FAILED" and l.get("log_metadata")), None)
    assert failed_log is not None, "Expected PAYMENT_FAILED audit log"

    meta = json.loads(failed_log["log_metadata"])
    assert meta["status"] == "Failed"
    assert meta["order_id"] == rzp_order_id
    assert meta["failure_reason"] == "User cancelled checkout modal"
    assert meta["purchased_items"] == ["Atomic Habits"]

# 7. Strict Cross-Sell Duplicate Prevention Test
def test_no_duplicate_cross_sell_companion():
    """Verify that find_cross_sell_companion never returns the added product or a book already in cart."""
    from app.database import SessionLocal
    from app.services.ai_agent import find_cross_sell_companion

    db = SessionLocal()
    try:
        prod_deep = make_mock_product(id=2, name="Deep Work")
        cart = [{"product_id": 2, "name": "Deep Work"}]

        companion = find_cross_sell_companion(db, prod_deep, cart)
        if companion:
            assert companion.id != prod_deep.id
            assert companion.name.lower() != "deep work"
            assert companion.name not in [item["name"] for item in cart]
    finally:
        db.close()
