import os
import sys

# Ensure backend root path is in sys.path
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal, engine, Base
from app.models import Product
from app.api.products import generate_200_books

def seed_database():
    print("Recreating database tables...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        print("Generating 200-book catalog...")
        books = generate_200_books()
        
        inserted_count = 0
        updated_count = 0

        for book_data in books:
            existing = db.query(Product).filter(Product.name == book_data["name"]).first()
            if not existing:
                p = Product(**book_data)
                db.add(p)
                inserted_count += 1
            else:
                existing.author = book_data["author"]
                existing.genre = book_data["genre"]
                existing.format = book_data["format"]
                existing.price = book_data["price"]
                existing.stock_quantity = book_data["stock_quantity"]
                existing.description = book_data["description"]
                existing.image_url = book_data["image_url"]
                updated_count += 1

        db.commit()
        total_count = db.query(Product).count()
        print(f"Seeding Complete! Total books in database: {total_count} (Inserted: {inserted_count}, Updated: {updated_count})")
        
        machiavelli = db.query(Product).filter(Product.name.ilike("%Machiavelli%")).first()
        if machiavelli:
            print(f"Verified Out-of-Stock Item: '{machiavelli.name}' (Stock: {machiavelli.stock_quantity})")
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
