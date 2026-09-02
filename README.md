# 📚 Agent Bookworm — Autonomous AI Bookstore & Agentic Commerce

> **Razorpay Buildathon Submission**  
> **Track:** AI Growth & Agentic Commerce  
> **Repository:** [AgentBookworm](https://github.com/your-org/AgentBookworm)

---

## 🚀 Overview

**Agent Bookworm** is an end-to-end AI Agentic Commerce platform built for conversational bookstore retail. It enables AI agents to negotiate prices, cross-sell complementary books, manage shopping carts, and generate instant, in-chat Razorpay checkouts—all while operating under strict, un-bypassable financial and operational guardrails.

---

## 🎯 The Problem

Traditional e-commerce checkouts are passive forms. Conversational AI promises active selling, but merchants face significant risks when giving AI money-handling powers:
1. **Unbounded Financial Risk**: AI agents hallucinating 90% discounts or zero-dollar carts.
2. **Black-Box Opacity**: Lack of auditability into why an AI granted a discount or recommended a specific upsell.
3. **Fragile Exception Handling**: AI crashing or giving broken responses when items go out of stock mid-conversation.

**Agent Bookworm solves this by combining Gemini-powered conversational intelligence with a hard-gated FastAPI financial backend and an explainable PostgreSQL audit trail.**

---

## 🏆 Meeting "The Bar" (Core Judging Criteria)

Agent Bookworm was architected ground-up around the mandatory judging pillars of the Agentic Commerce track:

### 1. 🛡️ Bounded & Hard-Gated Financial API
The AI model **never** calls payment APIs directly with unvalidated numbers. All money actions are funneled through our FastAPI backend (`POST /api/orders/create`), which enforces immutable backend rules:
- **15% Hard Discount Cap**: Any discount request > 15% is immediately rejected by the backend logic, triggering a `CHECKOUT_BLOCKED` audit record. The AI gracefully caps the discount at 15.0% and explains the rule to the buyer.
- **Cart Total Floor**: Orders with `total_amount <= 0` are automatically blocked.

### 2. 🔍 Explainable Audit Trail (Merchant Dashboard)
Every single money or pricing decision made by the AI is logged persistently in PostgreSQL (`ai_audit_logs`) with full human-readable reasoning:
- **Audit Fields**: `id`, `order_id`, `action_type` (`ITEM_ADDED_TO_CART`, `ITEM_REMOVED_FROM_CART`, `CHECKOUT_GENERATED`, `CHECKOUT_BLOCKED`, `STOCK_CHECK_FAILED`, `PAYMENT_VERIFIED`), `ai_reasoning`, `amount_involved`, and `timestamp`.
- **Merchant Dashboard View**: Merchants can view an interactive timeline of AI actions and click any row to expand the exact text explaining **why** the AI made that pricing or product decision.

### 3. ⚠️ Graceful Inventory Failure Handling
Demonstrated via a specific mock scenario:
- **The Out-Of-Stock Test Item**: Asking for *"The Prince - Machiavelli (1st Edition Signed)"* (Stock: 0).
- **Backend Exception**: When the AI or buyer attempts to check out this item, the backend detects zero stock and logs `STOCK_CHECK_FAILED` to `ai_audit_logs`.
- **Graceful AI Pivot**: The AI catches the exception and responds smoothly:
  > *"I apologize, but another collector just purchased the last signed copy of 'The Prince - Machiavelli (1st Edition Signed)'. However, we have 'Atomic Habits' by James Clear available, which is currently our #1 bestseller in strategic personal growth. Would you like me to add it to your cart with a 5% discount?"*

---

## 🛠️ Tech Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Frontend** | React (Vite), Tailwind CSS, Lucide Icons, React-Markdown | Dual-view UI (Buyer Chat & Merchant Audit Dashboard) |
| **Payment SDK** | Razorpay JS SDK (`checkout.js`) | Embedded in-chat modal checkout & HMAC SHA256 signature verification |
| **Backend API** | FastAPI (Python), Pydantic, Uvicorn | High-performance REST backend with gating logic |
| **AI Engine** | Gemini API (`google-genai`), Python SDK | Conversational intent evaluation & discount negotiation |
| **Database** | PostgreSQL / SQLite (SQLAlchemy ORM) | Persistent catalog, orders, and explainable audit logs |

---

## 💻 Dual-View Interface

1. **Buyer Chat Interface (`View 1`)**: A sleek conversational feed with interactive prompt chips (*"Recommend 3 good Self-Growth books"*, *"Can you give me a 20% discount?"*, *"I want to buy The Prince 1st Edition Signed"*). Generates embedded **Razorpay Checkout Cards** with product details, discount tags, cross-sell add-ons, and a working **"Pay with Razorpay"** button.
2. **Merchant Audit Dashboard (`View 2`)**: Real-time KPI summary cards (Total Checkouts, Cart Volume in ₹, Gated Blocks, Stock Exception Triggers) alongside an expandable audit timeline revealing exact AI decision traces.

---

## ⚡ Quick Start & Local Setup

### Prerequisites
- **Python 3.10+**
- **Node.js 18+** & `npm`

### 1. Clone & Environment Setup
Ensure your `.env` file is present in the root directory:
```env
# Use your own Razorpay *test-mode* credentials. Never commit real keys.
RAZORPAY_KEY_ID=rzp_test_your_key_id
RAZORPAY_KEY_SECRET=your_test_key_secret
DATABASE_URL=sqlite:///./agenticpay.db
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-120b
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.6-flash
MAX_DISCOUNT_PERCENT=15
# Optional maintenance credential. Do not expose this value to the browser.
AUDIT_CLEAR_TOKEN=replace-with-a-long-random-value
```

### 2. Automated One-Command Setup

#### On Windows:
```cmd
setup.bat
```

#### On Linux / macOS:
```bash
chmod +x setup.sh
./setup.sh
```

What the setup script performs:
1. Installs Python dependencies (`pip install -r backend/requirements.txt`).
2. Installs React frontend packages (`cd frontend && npm install`).
3. Initializes database tables & populates the **200-Book Catalog** (`/api/products/seed`).
4. Launches **FastAPI Server** (`http://127.0.0.1:8000`) and **Vite React App** (`http://localhost:5173`) concurrently!

### 3. Verify before demoing

```powershell
cd backend
..\.venv\Scripts\python.exe -m unittest discover -s tests -v

cd ..\frontend
.\node_modules\.bin\vite.cmd build
```

Razorpay orders are never faked: if the test-mode credentials or payment gateway are unavailable, checkout remains blocked, the cart stays intact, and the failure is recorded in the audit trail.

Audit history is intentionally persistent. The destructive maintenance endpoint requires `AUDIT_CLEAR_TOKEN` in the `X-Audit-Clear-Token` request header; the buyer and merchant browser UI cannot clear it.

---

## 🧪 Verification & Demo Scenarios

Once running, navigate to **`http://localhost:5173`** and click the demo prompt chips:

1. **Test 15% Cap Gating**: Click *"Can you give me a 20% discount on Atomic Habits?"*  
   *Result:* AI rejects 20%, applies the bounded 15.0% offer to the cart, and logs the cap decision in the audit trail. A Razorpay order is created only when the buyer explicitly proceeds to checkout.
2. **Test Graceful Failure**: Click *"I want to buy The Prince 1st Edition Signed"*  
   *Result:* Backend catches stock count = 0, logs `STOCK_CHECK_FAILED`, and AI offers an in-stock alternative without changing the cart until the buyer confirms.
3. **Test Payment Verification**: Click *"Pay with Razorpay"* on any generated checkout card  
   *Result:* Launches Razorpay Test Mode modal. On success, `/api/orders/verify` validates the HMAC signature and logs `PAYMENT_VERIFIED`.
4. **Merchant Audit Inspector**: Switch to **Merchant Audit Dashboard** tab  
   *Result:* View live KPI counters and expand any row to read the exact Ai reasoning trace.

If Gemini is rate-limited or temporarily unavailable, common shopping actions—catalog discovery, author lookup, budget curation, cart changes, discount caps and stock checks—continue against the live catalog. The assistant never fabricates a payment order or successful payment.

---

## 📄 License
Built for the **Razorpay Buildathon 2026** — *AI Growth & Agentic Commerce Track*.
