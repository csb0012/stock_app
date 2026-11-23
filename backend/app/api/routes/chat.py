from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.routes.auth import get_current_user
from app.core.config import settings
from app.models.user import User
from app.services import chatbot

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=60)


@router.get("/status")
async def chat_status(current_user: User = Depends(get_current_user)):
    """챗봇 사용 가능 여부 (키는 보여주지 않음)"""
    return {"enabled": bool(settings.anthropic_api_key), "model": settings.chat_model, "effort": settings.chat_effort}


@router.post("")
async def chat(req: ChatRequest, current_user: User = Depends(get_current_user)):
    """AI 챗봇 — Claude 가 앱 데이터(추천·종목 분석·투자종목·관심종목·시장·적중률·이벤트)를 조회해 답변"""
    try:
        return await chatbot.chat(current_user, [m.model_dump() for m in req.messages])
    except chatbot.ChatError as e:
        raise HTTPException(status_code=e.status, detail=str(e))
