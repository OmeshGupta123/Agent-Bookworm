import os
import unittest
from unittest.mock import patch, MagicMock

# The suite must never point at a developer's or merchant's configured
# database. Set this before importing any application module.
os.environ["DATABASE_URL"] = "sqlite:///./agenticpay_test.db"
os.environ["AUDIT_CLEAR_TOKEN"] = "test-audit-clear-token"

from fastapi.testclient import TestClient
from google.genai import types

from app.config import MAX_DISCOUNT_PERCENT
from app.database import SessionLocal, engine
from app.main import app
from app.agent.runner import run_agent


def tearDownModule():
    engine.dispose()


def chat(client: TestClient, message: str, cart=None, history=None) -> dict:
    response = client.post(
        "/api/chat",
        json={
            "message": message,
            "conversation_history": history or [],
            "cart": cart or [],
        },
    )
    assert response.status_code == 200
    return response.json()


class AgentGuardrailTests(unittest.TestCase):
    def test_discount_is_hard_capped_before_gemini(self):
        with TestClient(app) as client:
            data = chat(client, "Can I get a 90% discount on Atomic Habits?")

        self.assertEqual(data["action_type"], "CART_UPDATED")
        self.assertEqual(data["cart"][0]["name"], "Atomic Habits")
        self.assertEqual(data["cart"][0]["discount_percentage"], MAX_DISCOUNT_PERCENT)
        self.assertIn("caps maximum discounts", data["reply"])


    def test_browser_cart_prices_are_rehydrated_from_catalog(self):
        tampered_cart = [
            {
                "product_id": 1,
                "name": "Definitely not Atomic Habits",
                "price": 0.01,
                "final_price": 0.01,
                "quantity": 1,
                "discount_percentage": 999,
            }
        ]
        with TestClient(app) as client:
            data = chat(client, "show cart", cart=tampered_cart)

        self.assertEqual(data["action_type"], "CART_SUMMARY")
        item = data["cart"][0]
        self.assertEqual(item["name"], "Atomic Habits")
        self.assertEqual(item["price"], 16.99)
        self.assertEqual(item["discount_percentage"], MAX_DISCOUNT_PERCENT)
        self.assertGreater(item["final_price"], 0)


    def test_discovery_and_author_results_do_not_need_gemini(self):
        with TestClient(app) as client:
            data = chat(client, "I like Stephen King. What else has he written?")

        self.assertIsNone(data["action_type"])
        self.assertIn("The Shining", data["reply"])
        self.assertIn("IT", data["reply"])
        self.assertTrue(data["suggested_actions"])


    def test_ambiguous_yes_does_not_add_multiple_books(self):
        history = [
            {
                "role": "assistant",
                "content": "**Atomic Habits** and **Deep Work** are in stock. Would you like me to add one to your cart?",
            }
        ]
        with TestClient(app) as client:
            data = chat(client, "yes", history=history)

        self.assertEqual(data["cart"], [])
        self.assertIn("Which title", data["reply"])


    def test_empty_cart_never_creates_a_default_order(self):
        with TestClient(app) as client:
            data = chat(client, "checkout now")

        self.assertEqual(data["action_type"], "CART_EMPTY")
        self.assertIsNone(data["checkout_widget"])
        self.assertEqual(data["cart"], [])

    def test_tool_call_response_keeps_the_groq_call_id(self):
        """Protect the Groq multi-step tool protocol from regressions."""
        from types import SimpleNamespace
        tool_call = SimpleNamespace(
            id="call-search-1",
            type="function",
            function=SimpleNamespace(name="search_catalog", arguments='{"query": "sci-fi", "limit": 2}')
        )
        msg1 = MagicMock(content=None, tool_calls=[tool_call])
        choice1 = MagicMock(message=msg1)
        resp1 = MagicMock(choices=[choice1])

        msg2 = MagicMock(content="I found two sci-fi books.", tool_calls=None)
        choice2 = MagicMock(message=msg2)
        resp2 = MagicMock(choices=[choice2])

        class FakeCompletions:
            def __init__(self):
                self.calls = []

            def create(self, **kwargs):
                self.calls.append(kwargs)
                return resp1 if len(self.calls) == 1 else resp2

        fake_completions = FakeCompletions()
        fake_chat = MagicMock(completions=fake_completions)
        fake_client = MagicMock(chat=fake_chat)
        db = SessionLocal()
        try:
            with patch("app.agent.runner.get_groq_client", return_value=fake_client):
                reply, _, _, _, _ = run_agent(db, "Share a surprising science-fiction idea.", [], [])
        finally:
            db.close()

        self.assertEqual(reply, "I found two sci-fi books.")
        self.assertEqual(len(fake_completions.calls), 2)
        tool_msg = fake_completions.calls[1]["messages"][-1]
        self.assertEqual(tool_msg["role"], "tool")
        self.assertEqual(tool_msg["tool_call_id"], "call-search-1")

    def test_model_prose_cannot_create_checkout(self):
        """A hallucinated Razorpay claim must never become a payment action."""
        msg = MagicMock(content="Your Razorpay checkout order has been generated.", tool_calls=None)
        resp = MagicMock(choices=[MagicMock(message=msg)])

        class FakeCompletions:
            def create(self, **kwargs):
                return resp

        fake_client = MagicMock(chat=MagicMock(completions=FakeCompletions()))
        raw_cart = [{"product_id": 1, "name": "Atomic Habits", "quantity": 1}]
        db = SessionLocal()
        try:
            with patch("app.agent.runner.get_groq_client", return_value=fake_client):
                reply, action, widget, cart, _ = run_agent(db, "Tell me about your store.", [], raw_cart)
        finally:
            db.close()

        self.assertIsNone(action)
        self.assertIsNone(widget)
        self.assertEqual(cart[0]["name"], "Atomic Habits")
        self.assertIn("have not created a checkout", reply)

    def test_model_tool_call_cannot_add_without_buyer_authorization(self):
        """Prompt or model mistakes cannot turn a browsing request into a sale."""
        from types import SimpleNamespace
        tool_call = SimpleNamespace(
            id="call-unauthorized-add",
            type="function",
            function=SimpleNamespace(name="add_to_cart", arguments='{"product_id": 1, "ai_reasoning": "Attempted upsell."}')
        )
        msg1 = MagicMock(content=None, tool_calls=[tool_call])
        resp1 = MagicMock(choices=[MagicMock(message=msg1)])

        msg2 = MagicMock(content="Here is our store.", tool_calls=None)
        resp2 = MagicMock(choices=[MagicMock(message=msg2)])

        class FakeCompletions:
            def __init__(self):
                self.calls = []

            def create(self, **kwargs):
                self.calls.append(kwargs)
                return resp1 if len(self.calls) == 1 else resp2

        fake_completions = FakeCompletions()
        fake_client = MagicMock(chat=MagicMock(completions=fake_completions))
        db = SessionLocal()
        try:
            with patch("app.agent.runner.get_groq_client", return_value=fake_client):
                reply, action, _, cart, _ = run_agent(db, "Tell me about your store.", [], [])
        finally:
            db.close()

        self.assertEqual(reply, "Here is our store.")
        self.assertIsNone(action)
        self.assertEqual(cart, [])
        import json
        tool_result = json.loads(fake_completions.calls[1]["messages"][-1]["content"])
        self.assertIn("explicit buyer request", tool_result["result"]["error"])

    def test_missing_groq_client_uses_local_catalog(self):
        db = SessionLocal()
        try:
            with patch("app.agent.runner.get_groq_client", return_value=None):
                reply, action, _, cart, actions = run_agent(
                    db, "Can you help me?", [], []
                )
        finally:
            db.close()

        self.assertIsNone(action)
        self.assertEqual(cart, [])
        self.assertIn("matching books from our catalog", reply)
        self.assertTrue(actions)
