"""
FastAPI router for the AI chat assistant.

Unlike investigations, sending a message is a plain synchronous request —
the analyst is waiting for a reply, not polling a background job — so the
handler blocks until the LLM (and any tool calls it makes) finish. That can
take a while under a rate-limited provider; the retry/backoff caps already
built into the LLM layer keep it bounded rather than hanging forever.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import get_chatbot

router = APIRouter(prefix="/chat", tags=["chat"])


class SessionCreate(BaseModel):
    title: Optional[str] = None


class SessionUpdate(BaseModel):
    title: str


class MessageCreate(BaseModel):
    content: str


def _get_chatbot_or_503():
    chatbot = get_chatbot()
    if chatbot is None:
        raise HTTPException(status_code=503, detail="AI chat assistant is not configured")
    return chatbot


def _ensure_session(chatbot, session_id: str) -> dict:
    session = chatbot.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session


@router.get("/sessions")
def list_sessions(chatbot=Depends(_get_chatbot_or_503)):
    return chatbot.list_sessions()


@router.post("/sessions", status_code=201)
def create_session(body: SessionCreate, chatbot=Depends(_get_chatbot_or_503)):
    return chatbot.create_session(title=body.title)


@router.get("/sessions/{session_id}")
def get_session(session_id: str, chatbot=Depends(_get_chatbot_or_503)):
    return _ensure_session(chatbot, session_id)


@router.patch("/sessions/{session_id}")
def rename_session(session_id: str, body: SessionUpdate, chatbot=Depends(_get_chatbot_or_503)):
    _ensure_session(chatbot, session_id)
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    chatbot.rename_session(session_id, title)
    return chatbot.get_session(session_id)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str, chatbot=Depends(_get_chatbot_or_503)):
    _ensure_session(chatbot, session_id)
    chatbot.delete_session(session_id)
    return None


@router.get("/sessions/{session_id}/messages")
def list_messages(session_id: str, chatbot=Depends(_get_chatbot_or_503)):
    _ensure_session(chatbot, session_id)
    return chatbot.list_messages(session_id)


@router.post("/sessions/{session_id}/messages", status_code=201)
def send_message(session_id: str, body: MessageCreate, chatbot=Depends(_get_chatbot_or_503)):
    _ensure_session(chatbot, session_id)
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message content cannot be empty")
    return chatbot.send_message(session_id, content)
