"""
MailSense V3 — Gestion des sessions en mémoire (zéro stockage disque).
"""
from __future__ import annotations
import gc
import time
import uuid
from typing import Dict, Any, Optional

from config import SESSION_TTL_SECONDS

# Stockage en RAM uniquement
_sessions: Dict[str, Dict[str, Any]] = {}


def create_session() -> str:
    token = str(uuid.uuid4())
    _sessions[token] = {
        "created_at": time.time(),
        "credentials": None,       # google.oauth2.credentials.Credentials (objet mémoire)
        "email": None,
        "total": 0,
        "processed": 0,
        "categories": {},
        "status": "idle",           # idle | previewing | processing | done | error
        "preview_results": [],
        "corrections": {},          # {email_id: categorie}
        "error": None,
        "msg_ids": [],
    }
    return token


def get_session(token: str) -> Optional[Dict[str, Any]]:
    sess = _sessions.get(token)
    if not sess:
        return None
    if time.time() - sess["created_at"] > SESSION_TTL_SECONDS:
        destroy_session(token)
        return None
    return sess


def update_session(token: str, **kwargs) -> None:
    sess = _sessions.get(token)
    if sess:
        sess.update(kwargs)


def destroy_session(token: str) -> None:
    sess = _sessions.pop(token, None)
    if sess:
        # Purge explicite
        sess["credentials"] = None
        sess["msg_ids"] = []
        sess["preview_results"] = []
        sess["corrections"] = {}
        sess.clear()
        del sess
    gc.collect()


def cleanup_expired() -> None:
    now = time.time()
    expired = [t for t, s in _sessions.items()
               if now - s["created_at"] > SESSION_TTL_SECONDS]
    for t in expired:
        destroy_session(t)
