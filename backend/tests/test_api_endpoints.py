import os
import unittest
import hmac
import hashlib
import uuid
from unittest.mock import patch

# Keep endpoint tests isolated from the database configured for the app.
os.environ["DATABASE_URL"] = "sqlite:///./agenticpay_test.db"
os.environ["AUDIT_CLEAR_TOKEN"] = "test-audit-clear-token"

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal, engine
from app.models import Product, Order, AIAuditLog
from app.config import MAX_DISCOUNT_PERCENT, RAZORPAY_KEY_SECRET


def tearDownModule():
    engine.dispose()

class FullBackendSuiteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    def test_root_endpoint(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "online")
        self.assertIn("Agent Bookworm API", data["app"])

    def test_agent_catalog_endpoint(self):
        response = self.client.get("/api/agent-catalog.json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["checkout_capability"])
        self.assertIn("catalog", data)
        self.assertGreater(data["total_products"], 0)

    def test_products_list_and_filter(self):
        response = self.client.get("/api/products")
        self.assertEqual(response.status_code, 200)
        products = response.json()
        self.assertGreater(len(products), 0)

        # Test single product retrieval
        first_product_id = products[0]["id"]
        res_single = self.client.get(f"/api/products/{first_product_id}")
        self.assertEqual(res_single.status_code, 200)
        self.assertEqual(res_single.json()["id"], first_product_id)

    def test_order_creation_gating_discount_cap(self):
        db = SessionLocal()
        in_stock_product = db.query(Product).filter(Product.stock_quantity > 0).first()
        db.close()
        self.assertIsNotNone(in_stock_product)

        # 1. Reject discount > MAX_DISCOUNT_PERCENT (e.g. 20%)
        res_bad = self.client.post("/api/orders/create", json={
            "product_id": in_stock_product.id,
            "discount_percentage": 25.0
        })
        self.assertEqual(res_bad.status_code, 400)
        self.assertIn(f"maximum cap of {MAX_DISCOUNT_PERCENT}%", res_bad.json()["detail"])

        # 2. Accept valid discount <= MAX_DISCOUNT_PERCENT (e.g. 10%)
        order_id = f"order_test_discount_cap_{uuid.uuid4().hex}"
        with patch("app.api.orders.create_razorpay_order_sdk", return_value=order_id):
            res_good = self.client.post("/api/orders/create", json={
                "product_id": in_stock_product.id,
                "discount_percentage": 10.0
            })
        self.assertEqual(res_good.status_code, 200)
        order_data = res_good.json()
        self.assertEqual(order_data["discount_percentage"], 10.0)
        self.assertTrue(order_data["razorpay_order_id"].startswith("order_"))

    def test_order_creation_out_of_stock_item(self):
        db = SessionLocal()
        out_of_stock = db.query(Product).filter(Product.stock_quantity <= 0).first()
        db.close()
        if out_of_stock:
            res = self.client.post("/api/orders/create", json={
                "product_id": out_of_stock.id,
                "discount_percentage": 0.0
            })
            self.assertEqual(res.status_code, 409)
            self.assertIn("Out of Stock", res.json()["detail"])

    def test_payment_verification_valid_and_invalid_signature(self):
        db = SessionLocal()
        in_stock_product = db.query(Product).filter(Product.stock_quantity > 0).first()
        db.close()

        # Create order
        order_id = f"order_test_signature_{uuid.uuid4().hex}"
        with patch("app.api.orders.create_razorpay_order_sdk", return_value=order_id):
            create_res = self.client.post("/api/orders/create", json={
                "product_id": in_stock_product.id,
                "discount_percentage": 5.0
            })
        self.assertEqual(create_res.status_code, 200)
        order_info = create_res.json()
        rzp_order_id = order_info["razorpay_order_id"]

        # 1. Invalid signature
        verify_bad = self.client.post("/api/orders/verify", json={
            "razorpay_order_id": rzp_order_id,
            "razorpay_payment_id": "pay_test123",
            "razorpay_signature": "invalid_signature_hash",
            "items": [in_stock_product.name]
        })
        self.assertEqual(verify_bad.status_code, 400)

        # 2. Valid signature computation
        msg = f"{rzp_order_id}|pay_testValid123"
        valid_sig = hmac.new(
            RAZORPAY_KEY_SECRET.encode("utf-8"),
            msg.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        verify_good = self.client.post("/api/orders/verify", json={
            "razorpay_order_id": rzp_order_id,
            "razorpay_payment_id": "pay_testValid123",
            "razorpay_signature": valid_sig,
            "items": [in_stock_product.name]
        })
        self.assertEqual(verify_good.status_code, 200)
        self.assertEqual(verify_good.json()["status"], "success")

        # A client-side failure report is not financial evidence and cannot
        # downgrade a paid order.
        failure_after_paid = self.client.post("/api/orders/fail", json={
            "razorpay_order_id": rzp_order_id,
            "reason": "Late checkout modal event",
        })
        self.assertEqual(failure_after_paid.status_code, 200)
        self.assertEqual(failure_after_paid.json()["status"], "acknowledged")
        db = SessionLocal()
        try:
            self.assertEqual(
                db.query(Order).filter(Order.razorpay_order_id == rzp_order_id).one().status,
                "paid",
            )
        finally:
            db.close()

    def test_client_payment_failure_logs_to_audit_trail(self):
        res = self.client.post("/api/orders/fail", json={
            "razorpay_order_id": "order_mock_cancelled",
            "reason": "User closed Razorpay modal without completing payment",
            "items": ["Atomic Habits"]
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "recorded")
        db = SessionLocal()
        try:
            log = db.query(AIAuditLog).filter(AIAuditLog.action_type == "PAYMENT_FAILED").first()
            self.assertIsNotNone(log)
            self.assertIn("User closed Razorpay modal", log.ai_reasoning)
        finally:
            db.close()

    def test_audit_logs_retrieval(self):
        # 1. Record a server-side audit event. Browser reports are excluded
        # because they are not authoritative payment evidence.
        db = SessionLocal()
        try:
            db.add(AIAuditLog(
                action_type="PAYMENT_FAILED",
                ai_reasoning="Provider checkout creation failed safely.",
                amount_involved=16.99,
            ))
            db.commit()
        finally:
            db.close()
        # 2. Retrieve logs
        res = self.client.get("/api/audit-logs")
        self.assertEqual(res.status_code, 200)
        logs = res.json()
        self.assertIsInstance(logs, list)
        self.assertGreater(len(logs), 0)

        # 3. The destructive endpoint rejects an uncredentialed browser request.
        res_clear = self.client.post("/api/audit-logs/clear")
        self.assertEqual(res_clear.status_code, 403)

        # 4. A controlled maintenance call can clear the trail.
        res_clear = self.client.post(
            "/api/audit-logs/clear",
            headers={"X-Audit-Clear-Token": "test-audit-clear-token"},
        )
        self.assertEqual(res_clear.status_code, 200)
        res_after = self.client.get("/api/audit-logs")
        self.assertEqual(len(res_after.json()), 0)

    def test_chat_word_limit_guardrail(self):
        long_message = "word " * 160
        res = self.client.post("/api/chat", json={
            "message": long_message,
            "conversation_history": [],
            "cart": []
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["action_type"], "MESSAGE_TOO_LONG")
        self.assertIn("under 150 words", data["reply"])
