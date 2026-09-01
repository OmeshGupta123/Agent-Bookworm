from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class ProductBase(BaseModel):
    name: str
    author: str
    genre: str
    format: str
    price: float
    stock_quantity: int
    description: Optional[str] = None
    image_url: Optional[str] = None

class ProductResponse(ProductBase):
    id: int

    class Config:
        from_attributes = True

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

class ChatRequest(BaseModel):
    message: str
    conversation_history: Optional[List[Dict[str, str]]] = Field(default_factory=list)
    cart: Optional[List[Dict[str, Any]]] = Field(default_factory=list)

class CheckoutWidgetData(BaseModel):
    order_id: int
    razorpay_order_id: str
    razorpay_key_id: str
    items: List[Dict[str, Any]] = Field(default_factory=list)
    original_total: float
    total_discount: float
    discount_percentage: float
    final_amount: float
    currency: str = "INR"

class ChatResponse(BaseModel):
    reply: str
    action_type: Optional[str] = None
    checkout_widget: Optional[CheckoutWidgetData] = None
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    cart: List[Dict[str, Any]] = Field(default_factory=list)
    suggested_actions: List[str] = Field(default_factory=list)

class OrderCreateRequest(BaseModel):
    product_id: int
    discount_percentage: float = Field(default=0.0, ge=0.0, le=100.0)
    cross_sell_product_id: Optional[int] = None

class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    items: Optional[List[str]] = Field(default_factory=list)

class VerifyPaymentResponse(BaseModel):
    status: str
    message: str
    order_id: int

class FailPaymentRequest(BaseModel):
    razorpay_order_id: str
    reason: Optional[str] = "User cancelled payment or payment transaction failed."
    items: Optional[List[str]] = Field(default_factory=list)

class AIAuditLogResponse(BaseModel):
    id: int
    order_id: Optional[int] = None
    action_type: str
    ai_reasoning: str
    amount_involved: float
    log_metadata: Optional[str] = None
    timestamp: datetime

    class Config:
        from_attributes = True
