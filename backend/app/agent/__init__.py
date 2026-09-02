"""
app.agent — Agentic Commerce Engine

Modules:
  catalog_data   — static lookup tables (typo corrections, vibe maps, emotional maps)
  client         — Gemini API singleton (one HTTP client for the app lifetime)
  tools          — pure Python tool implementations (catalog, cart, checkout)
  declarations   — Gemini FunctionDeclaration objects for all tools
  guardrails     — deterministic pre-checks (discount cap, stock, budget, graceful failure)
  runner         — the agentic loop: Gemini -> function_call -> tool dispatch -> reply
"""

