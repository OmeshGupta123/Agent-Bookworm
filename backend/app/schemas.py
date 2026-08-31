from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field

class ProductBase(BaseModel):
    name: str
    author: Optional[str] = "Unknown Author"
    genre: Optional[str] = "General"
    format: Optional[str] = "Paperback"
    price: float
    stock_quantity: int
    description: Optional[str] = None
    image_url: Optional[str] = None

class ProductResponse(ProductBase):
    id: int

    class Config:
        from_attributes = True

class OrderCreateRequest(BaseModel):
    product_id: int
    discount_percentage: float = 0.0
    cross_sell_product_id: Optional[int] = None

class OrderResponse(BaseModel):
    id: int
    razorpay_order_id: str
    total_amount: float
    status: str
    created_at: datetime
    product_id: Optional[int] = None
    discount_percentage: float = 0.0

    class Config:
        from_attributes = True

class CartItem(BaseModel):
    product_id: int
    name: str
    author: Optional[str] = None
    format: Optional[str] = None
    price: float
    discount_percentage: float = 0.0
    final_price: float
    image_url: Optional[str] = None

class CheckoutWidgetData(BaseModel):
    order_id: int
    razorpay_order_id: str
    razorpay_key_id: str
    items: List[Dict[str, Any]]
    original_total: float
    total_discount: float
    discount_percentage: float
    final_amount: float
    currency: str = "INR"

class ChatRequest(BaseModel):
    message: str
    conversation_history: Optional[List[Dict[str, str]]] = Field(default_factory=list)
    cart: Optional[List[Dict[str, Any]]] = Field(default_factory=list)

class ChatResponse(BaseModel):
    reply: str
    action_type: Optional[str] = None
    checkout_widget: Optional[CheckoutWidgetData] = None
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    cart: List[Dict[str, Any]] = Field(default_factory=list)
    suggested_actions: List[str] = Field(default_factory=list)

class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str

class VerifyPaymentResponse(BaseModel):
    status: str
    message: str
    order_id: int

class AIAuditLogResponse(BaseModel):
    id: int
    order_id: Optional[int] = None
    action_type: str
    ai_reasoning: str
    amount_involved: float
    timestamp: datetime

    class Config:
        from_attributes = True
