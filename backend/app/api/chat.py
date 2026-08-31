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
    Enforces Pre-LLM >150 word count token-saver guardrail before invoking AI agent.
    Evaluates intent, manages stateful cart (add/remove), enforces <=15% discount gating,
    and returns conversational reply, updated cart state, and dynamic suggested actions.
    """
    # 1. Pre-LLM Token Saver Guardrail: Check message word count
    words = (req.message or "").split()
    if len(words) > 150:
        logger.info(f"Pre-LLM Guardrail triggered: Message length {len(words)} > 150 words.")
        return ChatResponse(
            reply="Your message is a bit too long! To help me assist you quickly, please keep your requests under 150 words.",
            action_type="MESSAGE_TOO_LONG",
            checkout_widget=None,
            conversation_history=req.conversation_history or [],
            cart=req.cart or [],
            suggested_actions=[]
        )

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
