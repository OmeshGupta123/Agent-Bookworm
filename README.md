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
RAZORPAY_KEY_ID=rzp_test_TV4evSxVgchq96
RAZORPAY_KEY_SECRET=U7A0FYCOv59mycrB6IE4KCOn
DATABASE_URL=sqlite:///./agenticpay.db
GEMINI_API_KEY=your_gemini_api_key_here
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
3. Initializes database tables & populates the **200-Book Catalog** (`/api/seed`).
4. Launches **FastAPI Server** (`http://127.0.0.1:8000`) and **Vite React App** (`http://localhost:5173`) concurrently!

---

## 🧪 Verification & Demo Scenarios

Once running, navigate to **`http://localhost:5173`** and click the demo prompt chips:

1. **Test 15% Cap Gating**: Click *"Can you give me a 20% discount on Atomic Habits?"*  
   *Result:* AI rejects 20%, caps discount at 15.0%, logs `CHECKOUT_BLOCKED` to the audit trail, and renders a 15% checkout card.
2. **Test Graceful Failure**: Click *"I want to buy The Prince 1st Edition Signed"*  
   *Result:* Backend catches stock count = 0, logs `STOCK_CHECK_FAILED`, and AI offers Atomic Habits at a 5% discount.
3. **Test Payment Verification**: Click *"Pay with Razorpay"* on any generated checkout card  
   *Result:* Launches Razorpay Test Mode modal. On success, `/api/orders/verify` validates the HMAC signature and logs `PAYMENT_VERIFIED`.
4. **Merchant Audit Inspector**: Switch to **Merchant Audit Dashboard** tab  
   *Result:* View live KPI counters and expand any row to read the exact Ai reasoning trace.

---

## 📄 License
Built for the **Razorpay Buildathon 2026** — *AI Growth & Agentic Commerce Track*.
