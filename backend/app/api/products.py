import random
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Product
from app.schemas import ProductResponse

router = APIRouter(prefix="/api/products", tags=["Products"])

# Hardcoded Recognition Bestsellers (~15)
HARDCODED_BOOKS = [
    {
        "name": "Atomic Habits",
        "author": "James Clear",
        "genre": "Self-Growth",
        "format": "Paperback",
        "price": 16.99,
        "stock_quantity": 40,
        "description": "An Easy & Proven Way to Build Good Habits & Break Bad Ones.",
        "image_url": "https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?w=500&auto=format&fit=crop&q=80"
    },
    {
        "name": "The 48 Laws of Power",
        "author": "Robert Greene",
        "genre": "Self-Growth",
        "format": "Hardcover",
        "price": 22.00,
        "stock_quantity": 30,
        "description": "Amoral, cunning, ruthless, and instructive book on power strategy.",
        "image_url": "https://images.unsplash.com/photo-1512820790803-83ca734da794?w=500&auto=format&fit=crop&q=80"
    },
    {
        "name": "The Prince - Machiavelli (1st Edition Signed)",
        "author": "Niccolò Machiavelli",
        "genre": "Classics",
        "format": "Hardcover",
        "price": 199.99,
        "stock_quantity": 0,  # INTENTIONAL OUT OF STOCK FOR GRACEFUL FAILURE TEST
        "description": "Rare 1st edition signed collector copy of political philosophy. Out of stock test item.",
        "image_url": "https://images.unsplash.com/photo-1543002588-bfa74002ed7e?w=500&auto=format&fit=crop&q=80"
    },
    {
        "name": "The Shining",
        "author": "Stephen King",
        "genre": "Horror",
        "format": "Paperback",
        "price": 14.99,
        "stock_quantity": 25,
        "description": "Classic horror novel set at the isolated Overlook Hotel.",
        "image_url": "https://images.unsplash.com/photo-1509021436468-d5103e3196d7?w=500&auto=format&fit=crop&q=80"
    },
    {
        "name": "IT",
        "author": "Stephen King",
        "genre": "Horror",
        "format": "Hardcover",
        "price": 19.99,
        "stock_quantity": 20,
        "description": "Seven adults return to Derry, Maine to confront a shape-shifting monster.",
        "image_url": "https://images.unsplash.com/photo-1516979187457-637abb4f9353?w=500&auto=format&fit=crop&q=80"
    },
    {
        "name": "Dune",
        "author": "Frank Herbert",
        "genre": "Sci-Fi",
        "format": "Paperback",
        "price": 18.50,
        "stock_quantity": 35,
        "description": "Epic science fiction masterpiece set on the desert planet Arrakis.",
        "image_url": "https://images.unsplash.com/photo-1532012197267-da84d127e765?w=500&auto=format&fit=crop&q=80"
    },
    {
        "name": "Project Hail Mary",
        "author": "Andy Weir",
        "genre": "Sci-Fi",
        "format": "Audio",
        "price": 24.99,
        "stock_quantity": 50,
        "description": "A lone astronaut must save Earth from an extinction-level catastrophe.",
        "image_url": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=500&auto=format&fit=crop&q=80"
    },
    {
        "name": "Clean Code",
        "author": "Robert C. Martin",
        "genre": "Tech",
        "format": "Paperback",
        "price": 42.99,
        "stock_quantity": 15,
        "description": "A Handbook of Agile Software Craftsmanship for software engineers.",
        "image_url": "https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=500&auto=format&fit=crop&q=80"
    },
    {
        "name": "Designing Data-Intensive Applications",
        "author": "Martin Kleppmann",
        "genre": "Tech",
        "format": "Paperback",
        "price": 49.99,
        "stock_quantity": 18,
        "description": "The Big Ideas Behind Reliable, Scalable, and Maintainable Systems.",
        "image_url": "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=500&auto=format&fit=crop&q=80"
    },
    {
        "name": "Deep Work",
        "author": "Cal Newport",
        "genre": "Self-Growth",
        "format": "Paperback",
        "price": 15.99,
        "stock_quantity": 28,
        "description": "Rules for Focused Success in a Distracted World.",
        "image_url": "https://images.unsplash.com/photo-1499750310107-5fef28a66643?w=500&auto=format&fit=crop&q=80"
    },
    {
        "name": "The Pragmatic Programmer",
        "author": "Andrew Hunt & David Thomas",
        "genre": "Tech",
        "format": "Hardcover",
        "price": 45.00,
        "stock_quantity": 22,
        "description": "Your Journey To Mastery, 20th Anniversary Edition.",
        "image_url": "https://images.unsplash.com/photo-1517694712202-14dd9538aa97?w=500&auto=format&fit=crop&q=80"
    },
    {
        "name": "Neuromancer",
        "author": "William Gibson",
        "genre": "Sci-Fi",
        "format": "Paperback",
        "price": 13.99,
        "stock_quantity": 30,
        "description": "Groundbreaking cyberpunk novel that introduced the Matrix.",
        "image_url": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=500&auto=format&fit=crop&q=80"
    },
    {
        "name": "Misery",
        "author": "Stephen King",
        "genre": "Horror",
        "format": "Paperback",
        "price": 12.99,
        "stock_quantity": 18,
        "description": "A famous novelist is held captive by his unhinged fan Annie Wilkes.",
        "image_url": "https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?w=500&auto=format&fit=crop&q=80"
    },
    {
        "name": "Psychology of Money",
        "author": "Morgan Housel",
        "genre": "Self-Growth",
        "format": "Audio",
        "price": 17.50,
        "stock_quantity": 45,
        "description": "Timeless lessons on wealth, greed, and happiness.",
        "image_url": "https://images.unsplash.com/photo-1559526324-4b87b5e36e44?w=500&auto=format&fit=crop&q=80"
    },
    {
        "name": "Zero to One",
        "author": "Peter Thiel",
        "genre": "Tech",
        "format": "Hardcover",
        "price": 21.00,
        "stock_quantity": 25,
        "description": "Notes on Startups, or How to Build the Future.",
        "image_url": "https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=500&auto=format&fit=crop&q=80"
    }
]

def generate_200_books():
    """Generates exactly 200 books (15 hardcoded + 185 programmatic)."""
    books = list(HARDCODED_BOOKS)

    genres = ["Horror", "Self-Growth", "Sci-Fi", "Tech"]
    formats = ["Paperback", "Hardcover", "Audio"]

    authors = {
        "Horror": ["Stephen King", "Clive Barker", "Shirley Jackson", "Bram Stoker", "H.P. Lovecraft", "Anne Rice", "Peter Straub", "Joe Hill"],
        "Self-Growth": ["James Clear", "Cal Newport", "Mark Manson", "Ryan Holiday", "Dale Carnegie", "Stephen Covey", "Brené Brown", "Viktor Frankl"],
        "Sci-Fi": ["Isaac Asimov", "Philip K. Dick", "Arthur C. Clarke", "Ursula K. Le Guin", "Cixin Liu", "Neal Stephenson", "Frank Herbert", "Alastair Reynolds"],
        "Tech": ["Robert C. Martin", "Martin Kleppmann", "Kent Beck", "Erich Gamma", "Guido van Rossum", "Linus Torvalds", "Donald Knuth", "Gene Kim"]
    }

    title_words = {
        "Horror": ["Shadows", "Whispers", "Midnight", "Curse", "Haunting", "Blood", "Silence", "Darkness", "Nightmare", "Sanctuary", "Echoes", "Graveyard"],
        "Self-Growth": ["Mindset", "Focus", "Habits", "Mastery", "Discipline", "Purpose", "Growth", "Clarity", "Resilience", "Influence", "Energy", "Potential"],
        "Sci-Fi": ["Chronicles", "Horizon", "Starlight", "Singularity", "Galaxy", "Protocol", "Orbit", "Quantum", "Nexus", "Cyber", "Void", "Eternity"],
        "Tech": ["Architecture", "System", "Algorithms", "Engine", "Data", "Microservices", "Compiler", "Security", "Cloud", "Distributed", "Patterns", "DevOps"]
    }

    image_pool = [
        "https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?w=500&auto=format&fit=crop&q=80",
        "https://images.unsplash.com/photo-1512820790803-83ca734da794?w=500&auto=format&fit=crop&q=80",
        "https://images.unsplash.com/photo-1532012197267-da84d127e765?w=500&auto=format&fit=crop&q=80",
        "https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=500&auto=format&fit=crop&q=80",
        "https://images.unsplash.com/photo-1499750310107-5fef28a66643?w=500&auto=format&fit=crop&q=80",
        "https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?w=500&auto=format&fit=crop&q=80"
    ]

    random.seed(42)  # Deterministic seed for reproducible 200 catalog

    remaining_needed = 200 - len(books)
    for i in range(1, remaining_needed + 1):
        genre = genres[i % len(genres)]
        author = random.choice(authors[genre])
        w1 = random.choice(title_words[genre])
        w2 = random.choice(title_words[genre])
        if w1 == w2:
            w2 = "Essence"

        title = f"The {w1} of {w2} Vol. {i}"
        fmt = formats[i % len(formats)]
        price = round(random.uniform(11.99, 49.99), 2)
        stock = random.randint(10, 60)
        desc = f"An essential {genre.lower()} work in {fmt} format by {author}. Volume #{i} in the master collection."

        books.append({
            "name": title,
            "author": author,
            "genre": genre,
            "format": fmt,
            "price": price,
            "stock_quantity": stock,
            "description": desc,
            "image_url": image_pool[i % len(image_pool)]
        })

    return books

@router.get("", response_model=List[ProductResponse])
def get_products(db: Session = Depends(get_db)):
    products = db.query(Product).all()
    if not products:
        seed_products(db)
        products = db.query(Product).all()
    return products

@router.get("/{product_id}", response_model=ProductResponse)
def get_product_by_id(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@router.post("/seed", response_model=List[ProductResponse])
def seed_products(db: Session = Depends(get_db)):
    all_books = generate_200_books()
    for item in all_books:
        existing = db.query(Product).filter(Product.name == item["name"]).first()
        if not existing:
            p = Product(**item)
            db.add(p)
        else:
            existing.author = item["author"]
            existing.genre = item["genre"]
            existing.format = item["format"]
            existing.stock_quantity = item["stock_quantity"]
            existing.price = item["price"]
            existing.description = item["description"]
            existing.image_url = item["image_url"]
    db.commit()
    return db.query(Product).all()
