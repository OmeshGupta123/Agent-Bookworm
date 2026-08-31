import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import ChatRequest, ChatResponse
from app.services.ai_agent import process_chat_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["Chat"])

@router.post("", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest, db: Session = Depends(get_db)):
    """
    POST /api/chat
    Takes user message, conversation history, and current shopping cart.
    Evaluates intent, manages stateful cart (add/remove), enforces <=15% discount gating,
    and returns conversational reply, updated cart state, and dynamic suggested actions.
    """
    try:
        reply_text, action_type, widget_data, updated_cart, suggested_actions = process_chat_message(
            db=db,
            message=req.message,
            conversation_history=req.conversation_history,
            current_cart=req.cart or []
        )

        history = req.conversation_history or []
        updated_history = history + [
            {"role": "user", "content": req.message},
            {"role": "assistant", "content": reply_text}
        ]

        return ChatResponse(
            reply=reply_text,
            action_type=action_type,
            checkout_widget=widget_data,
            conversation_history=updated_history,
            cart=updated_cart,
            suggested_actions=suggested_actions or []
        )
    except Exception as e:
        logger.error(f"Chat processing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat processing failed: {str(e)}")
