# app/agent/catalog_data.py
# ---------------------------------------------------------------------------
# Externalized static lookup tables — data that was previously embedded inside
# the agent logic. Keeping these separate makes them easy to update without
# touching any agent code.
# ---------------------------------------------------------------------------
import random
from typing import Any

# Fuzzy typo corrections applied before any catalog search
TYPO_CORRECTIONS: dict[str, str] = {
    "pwer": "power",
    "automic": "atomic",
    "habbit": "habit",
    "habbits": "habits",
    "macheavelli": "machiavelli",
    "machiaveli": "machiavelli",
    "steven": "stephen",
    "stefan": "stephen",
}

# Vibe / informal keyword -> canonical genre
VIBE_GENRE_MAP: dict[str, str] = {
    "scary": "Horror",
    "horror": "Horror",
    "creepy": "Horror",
    "spooky": "Horror",
    "thriller": "Horror",
    "tech": "Tech",
    "coding": "Tech",
    "programming": "Tech",
    "software": "Tech",
    "space": "Sci-Fi",
    "future": "Sci-Fi",
    "sci-fi": "Sci-Fi",
    "scifi": "Sci-Fi",
    "galaxy": "Sci-Fi",
    "habits": "Self-Growth",
    "growth": "Self-Growth",
    "money": "Self-Growth",
    "wealth": "Self-Growth",
    "focus": "Self-Growth",
    "mindset": "Self-Growth",
    "self-growth": "Self-Growth",
    "self growth": "Self-Growth",
}

# Emotional / life-situation keywords -> (genre_label, empathy_opener, book_hints)
EMOTIONAL_PROBLEM_MAP: dict[str, tuple[str, str, list[str]]] = {
    # Financial / Wealth
    "poor": (
        "wealth building & financial freedom",
        "I understand how challenging that feels, but the right knowledge and proven systems can completely transform your financial future.",
        ["Atomic Habits", "The 48 Laws of Power", "Clean Code"],
    ),
    "broke": (
        "financial growth & productivity",
        "I hear you, and investing in your mindset and skills is the most powerful first step toward building lasting stability.",
        ["Atomic Habits", "Deep Work", "Clean Code"],
    ),
    "rich": (
        "wealth accumulation & strategic discipline",
        "Ambition is powerful! Building wealth requires mastering high-value skills, habit discipline, and strategic focus.",
        ["Atomic Habits", "The 48 Laws of Power", "Designing Data-Intensive Applications"],
    ),
    "wealth": (
        "financial independence & strategic power",
        "Building true wealth starts with mastering your daily habits and understanding strategic decision-making.",
        ["Atomic Habits", "The 48 Laws of Power"],
    ),
    # Emotional / Mental
    "sad": (
        "resilience & personal growth",
        "I hear you, and taking time to nourish your mind with uplifting, empowering books is a wonderful step forward.",
        ["Atomic Habits", "Deep Work"],
    ),
    "depressed": (
        "mental clarity & small habits",
        "I understand things feel heavy right now. Small, positive daily systems can help rebuild momentum step by step.",
        ["Atomic Habits", "Deep Work"],
    ),
    "stressed": (
        "mindset & deep focus",
        "I completely understand. Managing stress starts with creating clear boundaries and focusing on what you can control.",
        ["Deep Work", "Atomic Habits"],
    ),
    "lonely": (
        "philosophy & human connection",
        "Reading is one of the most comforting companions. These inspiring books will keep you company and offer deep wisdom.",
        ["Atomic Habits", "The Shining"],
    ),
    "tired": (
        "restoration & focus systems",
        "Rest is essential. Rebuilding your focus and daily energy starts with simple, proven habits.",
        ["Atomic Habits", "Deep Work"],
    ),
    # Career / Ambition
    "succeed": (
        "high performance & career mastery",
        "I love that drive! Achieving peak success comes down to deep focus and consistent habit execution.",
        ["Deep Work", "Atomic Habits", "Clean Code"],
    ),
    "struggling": (
        "resilience & breakthrough strategies",
        "Every breakthrough begins in the middle of a struggle. These books provide clear blueprints to overcome obstacles.",
        ["Atomic Habits", "Deep Work"],
    ),
    "lazy": (
        "motivation & habit design",
        "It is rarely about laziness — it is about having the right environment and friction-free systems.",
        ["Atomic Habits", "Deep Work"],
    ),
    "focus": (
        "deep concentration & cognitive mastery",
        "Mastering deep focus is the ultimate superpower in today's distracted world.",
        ["Deep Work", "Atomic Habits"],
    ),
}

# Genres we know we don't stock — used for graceful failure pivots
UNSTOCKED_GENRES: list[str] = [
    "funny", "comedy", "romance", "romantic", "cooking", "cookbook", "manga", "poetry"
]

# Off-topic queries -> (topic_label, pivot_book_hints)
OUT_OF_CONTEXT_TOPICS: dict[str, tuple[str, list[str]]] = {
    "weather": ("science & environment", ["Dune", "Clean Code"]),
    "coding": ("tech & programming", ["Clean Code", "Designing Data-Intensive Applications"]),
    "program": ("tech & software design", ["Clean Code", "Designing Data-Intensive Applications"]),
    "python": ("tech & programming", ["Clean Code"]),
    "politics": ("history & strategy", ["The 48 Laws of Power", "The Prince"]),
    "recipe": ("lifestyle & habits", ["Atomic Habits"]),
    "football": ("sports & mindset", ["Atomic Habits", "Deep Work"]),
    "movie": ("fiction & drama", ["The Shining", "Dune"]),
}

# Out-of-stock special item for the Graceful Failure demo
OUT_OF_STOCK_ITEM_NAME = "The Prince - Machiavelli (1st Edition Signed)"
OUT_OF_STOCK_REPLY = (
    "I apologize, but another collector just purchased the last signed copy of "
    "'The Prince - Machiavelli (1st Edition Signed)'. However, we have 'Atomic Habits' by James Clear available, "
    "which is currently our #1 bestseller in strategic personal growth. "
    "Would you like me to add it to your cart with a 5% discount?"
)

# Detailed highlights, takeaways, witty pitches, and concise 30-50 word details
BOOK_HIGHLIGHTS: dict[str, dict[str, Any]] = {
    "atomic habits": {
        "tagline": "Tiny Changes, Remarkable Results",
        "pitches": [
            "Replaces unreliable willpower with tiny 1% daily systems so easy your laziest self can't find an excuse.",
            "The cure for buying a planner in January and abandoning it by January 4th. Pure behavioral wizardry.",
            "Teaches you to build unstoppable momentum without needing superhuman self-control or 5 AM ice baths.",
            "Automates good habits so smoothly your goals basically achieve themselves while you sip your morning coffee.",
        ],
        "detail_30_50_words": (
            "Atomic Habits by James Clear delivers a scientific, practical framework to build positive habits "
            "and eliminate self-destructive ones. By improving just 1% each day through identity shifts and "
            "environmental design, you unlock massive compounding personal transformation."
        ),
        "key_takeaways": [
            "The 4 Laws of Behavior Change: Make it Obvious, Attractive, Easy, and Satisfying.",
            "Identity-Based Habits: Focus on who you want to become rather than just outcomes.",
            "Micro-Compounding: 1% better every day yields a 37x improvement across a year.",
        ],
    },
    "the 48 laws of power": {
        "tagline": "The Definitive Guide to Strategy and Influence",
        "pitches": [
            "How to navigate corporate jungle warfare without getting stabbed in the back before lunch.",
            "Essential reading so you can spot the office Machiavelli three cubicles away before they steal your credit.",
            "A deliciously amoral playbook on human strategy, leverage, and keeping your poker face unshakable.",
            "Because sometimes playing too nice just gets you assigned to clean the breakroom microwave.",
        ],
        "detail_30_50_words": (
            "The 48 Laws of Power by Robert Greene is a bold, historical masterclass on strategy, "
            "influence, and self-preservation. Distilling three millennia of cunning philosophy, it teaches you to "
            "read hidden motives, avoid traps, command respect, and master ruthless competitive dynamics."
        ),
        "key_takeaways": [
            "Law 1: Never Outshine the Master — manage egos and maintain leverage.",
            "Law 4: Always Say Less than Necessary — silence creates mystery and control.",
            "Law 28: Enter Action with Boldness — hesitation breeds failure; audacity commands respect.",
        ],
    },
    "deep work": {
        "tagline": "Rules for Focused Success in a Distracted World",
        "pitches": [
            "In an era where your attention span is being rented out to TikTok, this is your cognitive superpower.",
            "Helps you lock in and produce elite work without opening 47 browser tabs every 10 minutes.",
            "A life raft for knowledge workers drowning in pointless Slack pings and Zoom fatigue.",
            "The secret weapon for getting 8 hours of real creative output done before lunch.",
        ],
        "detail_30_50_words": (
            "Deep Work by Cal Newport reveals how cultivating intense, distraction-free concentration has "
            "become the most valuable superpower in our chaotic modern economy. Packed with actionable rituals, "
            "it helps you eliminate digital noise, accelerate skill acquisition, and create high-impact work."
        ),
        "key_takeaways": [
            "The Deep Work Hypothesis: The ability to focus without distraction is becoming rare and high-value.",
            "Time-blocking and ritualized focus sessions to minimize cognitive friction.",
            "Draining the shallows: cutting out low-value busyness and constant notifications.",
        ],
    },
    "clean code": {
        "tagline": "A Handbook of Agile Software Craftsmanship",
        "pitches": [
            "Because writing code that works is cute, but writing code your future self won't want to burn down is legendary.",
            "Your coworkers will stop whispering about your pull requests behind your back after you read this.",
            "The software bible that turns spaghetti code nightmares into poetry that runs like silk.",
            "Saves you from staring blankly at your own variable names six months later wondering who wrote this.",
        ],
        "detail_30_50_words": (
            "Clean Code by Robert C. Martin is the classic craftsmanship guide for software engineers. "
            "It teaches the discipline of writing expressive, readable, and robust code through meaningful "
            "naming, small single-responsibility functions, and rigorous refactoring that keeps projects effortlessly maintainable."
        ),
        "key_takeaways": [
            "Meaningful names, small focused functions, and minimal side-effects.",
            "The Boy Scout Rule: Always leave the codebase cleaner than you found it.",
            "Effective unit testing and decoupling architectures.",
        ],
    },
    "the shining": {
        "tagline": "A Masterpiece of Psychological Suspense",
        "pitches": [
            "The ultimate reminder that maybe taking that quiet winter caretaker job in a deserted hotel is a terrible idea.",
            "Stephen King at his most delightfully terrifying — keep the lights on and double-check the bathtub.",
            "A psychological rollercoaster so intense you'll jump every time your floorboard creaks.",
            "Guaranteed to make you reconsider any snowy mountain vacations for the foreseeable future.",
        ],
        "detail_30_50_words": (
            "The Shining by Stephen King is a chilling masterpiece of psychological suspense and "
            "supernatural isolation. Following Jack Torrance's descent into madness at the snowbound Overlook Hotel, "
            "this terrifying classic explores addiction, family trauma, and relentless supernatural horror."
        ),
        "key_takeaways": [
            "Atmospheric dread and psychological tension at its peak.",
            "Iconic character study of isolation, addiction, and haunting family drama.",
            "Stephen King's master storytelling at the pinnacle of supernatural horror.",
        ],
    },
    "it": {
        "tagline": "The Ultimate Epic of Childhood, Fear, and Courage",
        "pitches": [
            "Proving once and for all that nobody should ever accept a balloon from a storm drain.",
            "An unforgettable 1,000-page emotional rollercoaster about friendship, courage, and a terrifying sewer clown.",
            "Stephen King's epic that makes you want to call your childhood best friends and avoid storm drains forever.",
        ],
        "detail_30_50_words": (
            "IT by Stephen King is a legendary epic exploring childhood trauma, loyalty, and "
            "courage against ancient terror in Derry, Maine. As seven outcasts confront the shape-shifting entity "
            "Pennywise across decades, they discover the enduring power of friendship to conquer deepest dread."
        ),
        "key_takeaways": [
            "The Losers Club bond: exploring how shared trauma and friendship conquer fear.",
            "The sinister mythology of Pennywise the Dancing Clown.",
            "Epic scale alternating between childhood nostalgia and adult reckoning.",
        ],
    },
    "the prince": {
        "tagline": "The Realist Philosophy of Leadership & Statecraft",
        "pitches": [
            "The original playbook for anyone who realized being nice didn't stop people from scheming.",
            "Renaissance leadership advice so brutally honest it makes modern management consultants sweat.",
            "Centuries old, yet reads like it was written yesterday for boardroom and political survivors.",
        ],
        "detail_30_50_words": (
            "The Prince by Niccolò Machiavelli is the foundational Renaissance guide to realism, "
            "governance, and power politics. Rejecting naive idealism, it analyzes how leaders successfully seize, "
            "exercise, and defend authority with pragmatism, strategic audacity, and calculated leverage."
        ),
        "key_takeaways": [
            "It is safer to be feared than loved, if one cannot be both.",
            "Fortune favors the bold: adapting swiftly to unpredictable circumstances.",
            "Pragmatism over idealism when securing and defending outcomes.",
        ],
    },
}


def generate_book_pitch(book_name: str, genre: str = "", author: str = "", description: str = "") -> str:
    """Returns a unique, funny/witty pitch tailored to the book without any label prefix."""
    lower_name = book_name.lower().strip()
    for key, data in BOOK_HIGHLIGHTS.items():
        if key in lower_name:
            pitches = data.get("pitches") or [data.get("pitch", "")]
            return random.choice(pitches)

    author_str = f" by {author}" if author else ""
    genre_funny_pitches = {
        "Self-Growth": [
            f"Because life doesn't come with an instruction manual, but {author or 'this author'} pretty much wrote one anyway.",
            "A cheat code for leveling up your mindset before Monday rolls around again.",
            "Guaranteed to make you feel 200% more put-together than everyone else in your morning meeting.",
        ],
        "Tech": [
            f"Because reading raw docs is torture, but mastering {genre} from {author or 'an expert'} is pure gold.",
            "Will save you from at least 40 hours of staring blankly at stack traces at 2 AM.",
            "Turn your codebase into something you can actually show off with pride.",
        ],
        "Sci-Fi": [
            "Blowing your mind with futuristic ideas so wild reality will feel boring for weeks.",
            "A one-way ticket across galaxies with worldbuilding so vivid you'll check your window for starships.",
            "Big ideas, cosmic stakes, and zero boring moments.",
        ],
        "Horror": [
            "Read with all lights blazing and maybe don't answer unusual knocks at the door.",
            "Delightfully terrifying storytelling that will keep you glued to the page past 3 AM.",
            "Heart-pounding suspense that makes ordinary coffee look like decaf.",
        ],
        "Classics": [
            "Brilliant storytelling that outlived entire empires for a very good reason.",
            "A timeless masterclass in human nature that makes modern drama look amateur.",
        ],
    }
    options = genre_funny_pitches.get(genre)
    if options:
        return random.choice(options)
    if description:
        return f"{description.rstrip('.')} — an absolute must-read that hooks you from chapter one!"
    return f"A standout pick{author_str} that readers can't stop raving about."


def get_book_30_50_word_detail(prod: Any) -> str:
    """Returns a concise 30-50 word detail of the book mentioned by the user."""
    lower_name = getattr(prod, "name", "").lower().strip()
    for key, data in BOOK_HIGHLIGHTS.items():
        if key in lower_name and "detail_30_50_words" in data:
            return data["detail_30_50_words"]

    desc = getattr(prod, "description", "") or f"An exceptional {getattr(prod, 'genre', 'fiction').lower()} work."
    text = (
        f"{prod.name} by {prod.author} is a compelling {prod.genre.lower()} book in {prod.format.lower()} format. "
        f"{desc.rstrip('.')}. "
        f"It offers rich insights and engaging storytelling that readers find both memorable and deeply impactful."
    )
    words = text.split()
    if len(words) > 50:
        text = " ".join(words[:48]) + "..."
    return text
