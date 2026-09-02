import os
import unittest
import uuid
from unittest.mock import patch

# Keep offline agent tests isolated from the database configured for the app.
os.environ["DATABASE_URL"] = "sqlite:///./agenticpay_test.db"
os.environ["AUDIT_CLEAR_TOKEN"] = "test-audit-clear-token"

from app.database import SessionLocal, engine
from app.agent.runner import run_agent


def tearDownModule():
    engine.dispose()

class OfflineAgentDeterministicTests(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def test_recommend_books(self):
        reply, action, widget, cart, actions = run_agent(self.db, "Recommend 3 good Self-Growth books.", [], [])
        self.assertIn("Atomic Habits", reply)
        self.assertGreater(len(actions), 0)

    def test_author_discovery(self):
        reply, action, widget, cart, actions = run_agent(self.db, "I like Stephen King. What else has he written?", [], [])
        self.assertIn("The Shining", reply)
        self.assertIn("IT", reply)

    def test_discount_capping(self):
        reply, action, widget, cart, actions = run_agent(self.db, "Can I get a 20% discount on Atomic Habits?", [], [])
        self.assertEqual(action, "CART_UPDATED")
        self.assertEqual(cart[0]["discount_percentage"], 15.0)

    def test_out_of_stock_item(self):
        reply, action, widget, cart, actions = run_agent(self.db, "I want to buy The Prince 1st Edition Signed", [], [])
        self.assertEqual(action, "GRACEFUL_FAILURE")
        self.assertIn("the prince", reply.lower())
        self.assertIn("atomic habits", reply.lower())

    def test_budget_curation(self):
        reply, action, widget, cart, actions = run_agent(self.db, "books under 500", [], [])
        self.assertIn("budget", reply.lower())
        self.assertIn("inr", reply.lower())

    def test_emotional_context(self):
        reply, action, widget, cart, actions = run_agent(self.db, "feeling stressed and overwhelmed", [], [])
        self.assertIn("stress", reply.lower())

    def test_off_topic_pivot(self):
        reply, action, widget, cart, actions = run_agent(self.db, "tell me about the weather", [], [])
        self.assertIn("catalog", reply.lower())

    def test_checkout_generation(self):
        cart_item = [{
            "product_id": 1,
            "name": "Atomic Habits",
            "price": 16.99,
            "final_price": 14.44,
            "quantity": 1,
            "discount_percentage": 15.0
        }]
        order_id = f"order_test_checkout_{uuid.uuid4().hex}"
        with patch("app.agent.tools.create_razorpay_order_sdk", return_value=order_id):
            reply, action, widget, cart, actions = run_agent(self.db, "checkout now", [], cart_item)
        self.assertEqual(action, "SHOW_CHECKOUT")
        self.assertIsNotNone(widget)
        self.assertTrue(widget["razorpay_order_id"].startswith("order_"))
