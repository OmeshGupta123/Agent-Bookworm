import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Product, Order
from app.config import MAX_DISCOUNT_PERCENT, RAZORPAY_KEY_ID
from app.schemas import (
    OrderCreateRequest, CheckoutWidgetData,
    VerifyPaymentRequest, VerifyPaymentResponse
)
from app.services.audit_service import log_ai_action
from app.services.razorpay_service import create_razorpay_order_sdk, verify_razorpay_signature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orders", tags=["Orders"])

@router.post("/create", response_model=CheckoutWidgetData)
def create_order(req: OrderCreateRequest, db: Session = Depends(get_db)):
    """
    POST /api/orders/create
    Creates a Razorpay checkout order with strict backend gating enforcement:
    1. Maximum discount allowed: 15%
    2. Cart total cannot be <= 0
    """
    product = db.query(Product).filter(Product.id == req.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    if product.stock_quantity <= 0:
        log_ai_action(
            db=db,
            action_type="STOCK_CHECK_FAILED",
            ai_reasoning=f"STOCK FAILURE DETECTED: Order creation for '{product.name}' blocked (Stock = {product.stock_quantity}).",
            amount_involved=product.price
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Item Out of Stock: {product.name} is currently unavailable."
        )

    if req.discount_percentage > MAX_DISCOUNT_PERCENT:
        log_ai_action(
            db=db,
            action_type="CHECKOUT_BLOCKED",
            ai_reasoning=f"HARD GATING ENFORCEMENT: Order rejected. Discount {req.discount_percentage}% exceeds cap of {MAX_DISCOUNT_PERCENT}%.",
            amount_involved=product.price
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Discount cannot exceed maximum cap of {MAX_DISCOUNT_PERCENT}%."
        )

    cross_sell_name = None
    cross_sell_price = 0.0
    if req.cross_sell_product_id:
        cross_item = db.query(Product).filter(Product.id == req.cross_sell_product_id).first()
        if cross_item and cross_item.stock_quantity > 0:
            cross_sell_name = cross_item.name
            cross_sell_price = cross_item.price

    discount_amount = round(product.price * (req.discount_percentage / 100.0), 2)
    final_amount = round((product.price - discount_amount) + cross_sell_price, 2)

    if final_amount <= 0:
        log_ai_action(
            db=db,
            action_type="CHECKOUT_BLOCKED",
            ai_reasoning=f"HARD GATING ENFORCEMENT: Order rejected. Total amount is {final_amount} (must be > 0).",
            amount_involved=final_amount
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cart total amount must be greater than 0."
        )

    rzp_order_id = create_razorpay_order_sdk(
        amount_in_inr=final_amount,
        notes={
            "product_name": product.name,
            "discount_percentage": str(req.discount_percentage)
        }
    )

    db_order = Order(
        razorpay_order_id=rzp_order_id,
        total_amount=final_amount,
        status="pending",
        product_id=product.id,
        discount_percentage=req.discount_percentage
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)

    log_ai_action(
        db=db,
        order_id=db_order.id,
        action_type="CHECKOUT_GENERATED",
        ai_reasoning=f"CHECKOUT CREATED: Generated Razorpay order '{rzp_order_id}' for '{product.name}'. Payable: ${final_amount}.",
        amount_involved=final_amount
    )

    items = [
        {
            "product_id": product.id,
            "name": product.name,
            "author": product.author,
            "format": product.format,
            "price": product.price,
            "discount_percentage": req.discount_percentage,
            "discount_amount": discount_amount,
            "final_price": product.price - discount_amount,
            "image_url": product.image_url
        }
    ]
    if cross_sell_name:
        items.append({
            "product_id": req.cross_sell_product_id,
            "name": cross_sell_name,
            "price": cross_sell_price,
            "discount_percentage": 0.0,
            "discount_amount": 0.0,
            "final_price": cross_sell_price,
            "image_url": None
        })

    return CheckoutWidgetData(
        order_id=db_order.id,
        razorpay_order_id=rzp_order_id,
        razorpay_key_id=RAZORPAY_KEY_ID,
        items=items,
        original_total=product.price + cross_sell_price,
        total_discount=discount_amount,
        discount_percentage=req.discount_percentage,
        final_amount=final_amount,
        currency="INR"
    )

@router.post("/verify", response_model=VerifyPaymentResponse)
def verify_payment(req: VerifyPaymentRequest, db: Session = Depends(get_db)):
    """
    POST /api/orders/verify
    Verifies Razorpay HMAC payment signature, updates order status to 'paid',
    and logs PAYMENT_VERIFIED to ai_audit_logs table.
    """
    order = db.query(Order).filter(Order.razorpay_order_id == req.razorpay_order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found in database.")

    is_valid = verify_razorpay_signature(
        razorpay_order_id=req.razorpay_order_id,
        razorpay_payment_id=req.razorpay_payment_id,
        razorpay_signature=req.razorpay_signature
    )

    if is_valid:
        order.status = "paid"
        db.commit()

        log_ai_action(
            db=db,
            order_id=order.id,
            action_type="PAYMENT_VERIFIED",
            ai_reasoning=(
                f"PAYMENT VERIFIED SUCCESSFULLY: Razorpay HMAC payment signature validated for Order ID '{order.razorpay_order_id}' "
                f"with Payment ID '{req.razorpay_payment_id}'. Database order status updated to PAID."
            ),
            amount_involved=order.total_amount
        )
        return VerifyPaymentResponse(
            status="success",
            message="Razorpay payment verified successfully!",
            order_id=order.id
        )
    else:
        order.status = "failed"
        db.commit()

        log_ai_action(
            db=db,
            order_id=order.id,
            action_type="PAYMENT_FAILED",
            ai_reasoning=(
                f"PAYMENT VERIFICATION FAILED: Invalid Razorpay signature for Order ID '{order.razorpay_order_id}'. "
                "Order status updated to FAILED."
            ),
            amount_involved=order.total_amount
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payment signature."
        )
