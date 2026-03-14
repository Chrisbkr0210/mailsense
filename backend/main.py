"""
MailSense V3 — FastAPI backend
Endpoints : auth, preview, processing (SSE), résultats
"""
from __future__ import annotations
import gc
import json
import asyncio
from typing import Dict, Any, Optional

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import (
    HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

import auth
import gmail_service
import classifier
import label_manager
import session_manager
from config import CATEGORIES, ENV

BASE_DIR = Path(__file__).parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="MailSense V3", docs_url=None, redoc_url=None)

# Static files (CSS, JS)
app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
app.mount("/js",  StaticFiles(directory=str(FRONTEND_DIR / "js")),  name="js")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

# Cleanup périodique des sessions expirées
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(_cleanup_loop())

async def _cleanup_loop():
    while True:
        await asyncio.sleep(300)  # toutes les 5 minutes
        session_manager.cleanup_expired()


# ── Pages HTML statiques ──────────────────────────────────────────────────────

def _html(filename: str) -> HTMLResponse:
    path = FRONTEND_DIR / filename
    return HTMLResponse(content=path.read_text(encoding="utf-8"))

@app.get("/", response_class=HTMLResponse)
async def index():
    return _html("index.html")

@app.get("/preview", response_class=HTMLResponse)
async def preview_page():
    return _html("preview.html")

@app.get("/processing", response_class=HTMLResponse)
async def processing_page():
    return _html("processing.html")

@app.get("/result", response_class=HTMLResponse)
async def result_page():
    return _html("result.html")

@app.get("/comment-ca-marche", response_class=HTMLResponse)
async def how_it_works():
    return _html("how-it-works.html")

@app.get("/privacy", response_class=HTMLResponse)
async def privacy():
    return _html("privacy.html")


# ── Auth OAuth2 ───────────────────────────────────────────────────────────────

@app.get("/auth/login")
async def auth_login():
    auth_url, state = auth.get_auth_url()
    # Stocker state dans une session temporaire
    token = session_manager.create_session()
    session_manager.update_session(token, oauth_state=state)
    # Passer le token via redirect_uri state
    return RedirectResponse(auth_url + "&session_token=" + token)


@app.get("/auth/callback")
async def auth_callback(request: Request, code: str = "", state: str = ""):
    # Récupérer session_token depuis le state ou query param
    session_token = request.query_params.get("session_token", "")

    # Chercher la session par oauth_state si pas de session_token
    if not session_token:
        for tok, sess in session_manager._sessions.items():
            if sess.get("oauth_state") == state:
                session_token = tok
                break

    if not session_token:
        raise HTTPException(status_code=400, detail="Session introuvable")

    sess = session_manager.get_session(session_token)
    if not sess:
        raise HTTPException(status_code=400, detail="Session expirée")

    try:
        creds = auth.exchange_code(code, state)
        creds_dict = auth.credentials_to_dict(creds)
        user_email = gmail_service.get_user_email(creds)
        session_manager.update_session(
            session_token,
            credentials=creds_dict,
            email=user_email,
            status="connected",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Erreur OAuth: " + str(e))

    return RedirectResponse(
        "/preview?token=" + session_token, status_code=302
    )


# ── API : Preview ─────────────────────────────────────────────────────────────

@app.get("/api/preview/{token}")
async def api_preview(token: str, background_tasks: BackgroundTasks):
    sess = session_manager.get_session(token)
    if not sess:
        raise HTTPException(status_code=404, detail="Session introuvable")

    creds_dict = sess.get("credentials")
    if not creds_dict:
        raise HTTPException(status_code=401, detail="Non authentifié")

    creds = auth.dict_to_credentials(creds_dict)
    creds = auth.refresh_credentials(creds)
    session_manager.update_session(token, status="previewing")

    try:
        # Récupérer tous les IDs (une seule fois)
        all_ids = gmail_service.get_all_message_ids(creds)
        session_manager.update_session(token, total=len(all_ids), msg_ids=all_ids)

        # Échantillon 50 emails répartis
        preview_emails = gmail_service.get_preview_sample(creds, all_ids)

        # Classifier avec Sonnet
        classified = classifier.classify_preview(preview_emails)

        session_manager.update_session(
            token,
            preview_results=classified,
            status="preview_ready",
        )
        return JSONResponse({
            "total": len(all_ids),
            "emails": classified,
        })
    except Exception as e:
        session_manager.update_session(token, status="error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/corrections/{token}")
async def api_corrections(token: str, request: Request):
    """Enregistre les corrections manuelles de l'utilisateur sur la preview."""
    sess = session_manager.get_session(token)
    if not sess:
        raise HTTPException(status_code=404, detail="Session introuvable")

    body = await request.json()
    corrections = body.get("corrections", {})
    session_manager.update_session(token, corrections=corrections)
    return {"ok": True}


# ── API : Processing (SSE temps réel) ────────────────────────────────────────

@app.get("/api/process/{token}")
async def api_process(token: str):
    """
    SSE endpoint. Envoie des événements de progression en temps réel.
    Le traitement continue en background même si le client se déconnecte.
    """
    sess = session_manager.get_session(token)
    if not sess:
        raise HTTPException(status_code=404, detail="Session introuvable")

    if sess.get("status") == "processing":
        # Déjà en cours → juste envoyer le statut courant
        return StreamingResponse(
            _sse_status_stream(token),
            media_type="text/event-stream",
        )

    return StreamingResponse(
        _sse_process_stream(token),
        media_type="text/event-stream",
    )


async def _sse_status_stream(token: str):
    """Stream SSE pour une session déjà en cours."""
    while True:
        sess = session_manager.get_session(token)
        if not sess:
            break
        data = {
            "processed": sess.get("processed", 0),
            "total": sess.get("total", 0),
            "categories": sess.get("categories", {}),
            "status": sess.get("status", ""),
        }
        yield "data: {}\n\n".format(json.dumps(data))
        if sess.get("status") in ("done", "error"):
            break
        await asyncio.sleep(1)


async def _sse_process_stream(token: str):
    """Lance le traitement complet (async 4x parallèle) et stream la progression SSE."""
    sess = session_manager.get_session(token)
    creds_dict = sess.get("credentials")
    creds = auth.dict_to_credentials(creds_dict)
    creds = auth.refresh_credentials(creds)

    all_ids = sess.get("msg_ids", [])
    if not all_ids:
        all_ids = await asyncio.get_event_loop().run_in_executor(
            None, lambda: gmail_service.get_all_message_ids(creds)
        )
        session_manager.update_session(token, total=len(all_ids), msg_ids=all_ids)

    corrections = sess.get("corrections", {})
    session_manager.update_session(
        token, status="processing", processed=0, categories={}, cost=0.0
    )

    queue: asyncio.Queue = asyncio.Queue()

    def progress_callback(processed, total, categories, cost_usd):
        session_manager.update_session(
            token, processed=processed, categories=categories, cost=cost_usd,
        )
        queue.put_nowait({
            "processed": processed, "total": total,
            "categories": categories, "cost": cost_usd,
            "status": "processing",
        })

    async def run_classification():
        try:
            emails = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: gmail_service.fetch_emails_metadata_batch(creds, all_ids),
            )

            # Classifier async, 4 batches de 300 en parallèle
            results = await classifier.classify_all_parallel(
                emails, corrections, progress_callback
            )

            emails_by_cat: Dict[str, list] = {cat: [] for cat in CATEGORIES}
            for eid, cat in results.items():
                if cat in emails_by_cat:
                    emails_by_cat[cat].append(eid)

            label_map = await asyncio.get_event_loop().run_in_executor(
                None, lambda: label_manager.ensure_labels(creds)
            )
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: label_manager.apply_labels_bulk(creds, emails_by_cat, label_map)
            )

            final_categories = {cat: len(ids) for cat, ids in emails_by_cat.items()}
            final_cost = session_manager.get_session(token).get("cost", 0.0)
            session_manager.update_session(
                token, status="done", processed=len(all_ids), categories=final_categories,
            )
            queue.put_nowait({
                "status": "done", "processed": len(all_ids), "total": len(all_ids),
                "categories": final_categories, "cost": final_cost,
            })

            del emails
            del results
            gc.collect()

        except Exception as e:
            session_manager.update_session(token, status="error", error=str(e))
            queue.put_nowait({"status": "error", "error": str(e)})

    asyncio.create_task(run_classification())

    while True:
        try:
            data = await asyncio.wait_for(queue.get(), timeout=2.0)
            yield "data: {}\n\n".format(json.dumps(data))
            if data.get("status") in ("done", "error"):
                break
        except asyncio.TimeoutError:
            sess = session_manager.get_session(token)
            if not sess:
                break
            yield ": keepalive\n\n"


# ── API : Statut ──────────────────────────────────────────────────────────────

@app.get("/api/status/{token}")
async def api_status(token: str):
    sess = session_manager.get_session(token)
    if not sess:
        raise HTTPException(status_code=404, detail="Session introuvable ou expirée")
    return {
        "status":     sess.get("status"),
        "processed":  sess.get("processed", 0),
        "total":      sess.get("total", 0),
        "categories": sess.get("categories", {}),
        "email":      sess.get("email", ""),
        "error":      sess.get("error"),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=(ENV == "development"))
