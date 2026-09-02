# app/agent/declarations.py
# ---------------------------------------------------------------------------
# Tool definitions for Groq API (OpenAI-compatible schema).
# ---------------------------------------------------------------------------

GROQ_BOOKSTORE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_catalog",
            "description": (
                "Search the SQLite bookstore catalog by query keyword, theme, genre, vibe, author, or title. "
                "Returns a list of matching available books with base_price and max_discount. Use this for recommendation "
                "requests like 'show me sci-fi books', 'recommend 3 self-growth books', or any search/discovery intent."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query string (keyword, title, author, genre, or vibe).",
                    },
                    "theme": {
                        "type": "string",
                        "description": "Optional search theme or category.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return. Default 5.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_product",
            "description": (
                "Lookup a SINGLE specific book by name or author for cart operations "
                "(add, remove, discount). Use this — not search_catalog — when you "
                "need to identify exactly one book."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The book title or author name to look up.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_cart",
            "description": (
                "Add a specific book to the user's shopping cart. "
                "You MUST call find_product first to get the product_id, then call this. "
                "Only add to cart when the user explicitly asks to buy, add, or purchase — "
                "never add on a recommendation request."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "integer",
                        "description": "The product ID returned by find_product.",
                    },
                    "discount_pct": {
                        "type": "number",
                        "description": (
                            "Discount percentage to apply (0–15). Default 0. "
                            "The server rejects or caps values beyond the merchant policy."
                        ),
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Number of copies. Default 1.",
                    },
                    "ai_reasoning": {
                        "type": "string",
                        "description": "1-2 sentence explanation detailing why you chose to add this item, why you applied a specific discount, or how it benefits the merchant's revenue.",
                    },
                },
                "required": ["product_id", "ai_reasoning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_from_cart",
            "description": (
                "Remove a book from the user's shopping cart by name or partial title. "
                "Use when the user says 'remove', 'delete', or 'I don't want'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "identifier": {
                        "type": "string",
                        "description": "The book name or partial title to remove.",
                    },
                    "ai_reasoning": {
                        "type": "string",
                        "description": "1-2 sentence explanation detailing why this item is being removed from the cart.",
                    },
                },
                "required": ["identifier", "ai_reasoning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cart_summary",
            "description": (
                "Return the current cart contents, item count, original total, final total, "
                "and savings. Call this when the user asks about their cart total, contents, "
                "or status."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_and_bundle",
            "description": "Analyze the user's current cart and chat context to curate a high-margin, 2-to-3 book bundle. Use this immediately after a user adds an item to the cart to proactively pitch an upsell.",
            "parameters": {
                "type": "object",
                "properties": {
                    "theme": {
                        "type": "string",
                        "description": "The overarching theme or vibe of the user's current interests (e.g., 'productivity and wealth', 'sci-fi space operas').",
                    },
                    "max_budget": {
                        "type": "number",
                        "description": "An optional limit to ensure the bundle isn't too expensive for the user's perceived budget.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_book_details",
            "description": (
                "Retrieve comprehensive information, synopsis, key takeaways, pricing, format, "
                "and stock status for a specific book when a user asks for more information, "
                "details, key ideas, or a summary of a book."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The title or author of the book to get details for.",
                    },
                },
                "required": ["query"],
            },
        },
    },
]

BOOKSTORE_TOOLS = GROQ_BOOKSTORE_TOOLS
