"""
MailSense V3 — Gmail API : récupération emails, IDs, metadata + body snippet.
"""
from __future__ import annotations
import base64
import random
from typing import List, Dict, Any, Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import GMAIL_PAGE_SIZE, PREVIEW_COUNT


def _build_service(creds: Credentials):
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def get_user_email(creds: Credentials) -> str:
    service = _build_service(creds)
    profile = service.users().getProfile(userId="me").execute()
    return profile.get("emailAddress", "")


def get_all_message_ids(creds: Credentials) -> List[str]:
    """Récupère tous les IDs (inbox + archivés + spam + trash)."""
    service = _build_service(creds)
    ids = []
    page_token = None

    while True:
        kwargs: Dict[str, Any] = {
            "userId": "me",
            "maxResults": GMAIL_PAGE_SIZE,
            "q": "in:all",
        }
        if page_token:
            kwargs["pageToken"] = page_token

        result = service.users().messages().list(**kwargs).execute()
        for msg in result.get("messages", []):
            ids.append(msg["id"])

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return ids


def _decode_body(payload: dict) -> str:
    """Extrait les 200 premiers chars du corps texte d'un email."""
    try:
        parts = payload.get("parts", [])
        if parts:
            for part in parts:
                if part.get("mimeType") == "text/plain":
                    data = part.get("body", {}).get("data", "")
                    if data:
                        text = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
                        return text[:200]
            # fallback : premier part
            data = parts[0].get("body", {}).get("data", "")
            if data:
                text = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
                return text[:200]
        else:
            data = payload.get("body", {}).get("data", "")
            if data:
                text = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
                return text[:200]
    except Exception:
        pass
    return ""


def fetch_emails_metadata_batch(creds: Credentials, msg_ids: List[str]) -> List[Dict]:
    """
    Fetch metadata + 200 chars du corps en batch Gmail (100 req/appel HTTP).
    Retourne [{id, subject, sender, snippet}]
    """
    service = _build_service(creds)
    results: Dict[str, Dict] = {}

    def _cb(request_id, response, exception):
        if exception or not response:
            results[request_id] = {
                "id": request_id, "subject": "(erreur)", "sender": "", "snippet": "",
            }
            return
        hdrs = {
            h["name"]: h["value"]
            for h in response.get("payload", {}).get("headers", [])
        }
        snippet = response.get("snippet", "")[:200]
        results[request_id] = {
            "id":      request_id,
            "subject": hdrs.get("Subject", "(Sans objet)"),
            "sender":  hdrs.get("From", ""),
            "snippet": snippet,
        }

    for i in range(0, len(msg_ids), 100):
        chunk = msg_ids[i:i + 100]
        batch = service.new_batch_http_request(callback=_cb)
        for mid in chunk:
            batch.add(
                service.users().messages().get(
                    userId="me",
                    id=mid,
                    format="metadata",
                    metadataHeaders=["Subject", "From"],
                ),
                request_id=mid,
            )
        batch.execute()

    return [
        results.get(mid, {"id": mid, "subject": "(manquant)", "sender": "", "snippet": ""})
        for mid in msg_ids
    ]


def get_preview_sample(creds: Credentials, all_ids: List[str]) -> List[Dict]:
    """
    Sélectionne PREVIEW_COUNT emails répartis sur toute la boîte (pas les 50 premiers).
    Fetch leur metadata.
    """
    if len(all_ids) <= PREVIEW_COUNT:
        sample_ids = all_ids
    else:
        step = len(all_ids) // PREVIEW_COUNT
        sample_ids = [all_ids[i * step] for i in range(PREVIEW_COUNT)]

    return fetch_emails_metadata_batch(creds, sample_ids)
