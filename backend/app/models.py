from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    author = Column(String(255), nullable=False, default="Unknown Author")
    genre = Column(String(100), nullable=False, default="General")
    format = Column(String(50), nullable=False, default="Paperback")
    price = Column(Float, nullable=False)
    stock_quantity = Column(Integer, nullable=False, default=0)
    description = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=True)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    razorpay_order_id = Column(String(255), unique=True, index=True, nullable=False)
    total_amount = Column(Float, nullable=False)
    status = Column(String(50), nullable=False, default="pending")  # pending, paid, failed
    created_at = Column(DateTime, default=datetime.utcnow)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    discount_percentage = Column(Float, default=0.0)

    # Relationships
    product = relationship("Product")
    audit_logs = relationship("AIAuditLog", back_populates="order")

class AIAuditLog(Base):
    __tablename__ = "ai_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    action_type = Column(String(100), nullable=False)
    # Action types: CHECKOUT_GENERATED, CHECKOUT_BLOCKED, STOCK_CHECK_FAILED, PAYMENT_VERIFIED, PAYMENT_FAILED
    ai_reasoning = Column(Text, nullable=False)
    amount_involved = Column(Float, nullable=False, default=0.0)
    log_metadata = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Relationship
    order = relationship("Order", back_populates="audit_logs")
