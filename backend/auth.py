"""
MailSense V3 — OAuth2 Google (server-side flow).
Token stocké en mémoire via session_manager. Jamais sur disque.
"""
from __future__ import annotations
import json
from typing import Optional

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from config import (
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, GOOGLE_SCOPES,
)


def _make_client_config() -> dict:
    # "web" type required for Web Application OAuth clients (HTTPS redirect URIs).
    return {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [GOOGLE_REDIRECT_URI],
        }
    }


def get_auth_url() -> tuple:
    """Retourne (auth_url, state)."""
    flow = Flow.from_client_config(
        _make_client_config(),
        scopes=GOOGLE_SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI,
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return auth_url, state


def exchange_code(code: str, state: str) -> Credentials:
    """Échange le code OAuth2 contre un token. Retourne Credentials (RAM).
    OAUTHLIB_RELAX_TOKEN_SCOPE=1 : Google renvoie 'userinfo.email' au lieu de 'email',
    ce flag accepte les deux variantes sans lever ScopeChanged.
    """
    import os
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    flow = Flow.from_client_config(
        _make_client_config(),
        scopes=GOOGLE_SCOPES,
        state=state,
        redirect_uri=GOOGLE_REDIRECT_URI,
    )
    flow.fetch_token(code=code)
    return flow.credentials


def refresh_credentials(creds: Credentials) -> Credentials:
    """Rafraîchit le token si expiré."""
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def credentials_to_dict(creds: Credentials) -> dict:
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else [],
    }


def dict_to_credentials(d: dict) -> Credentials:
    return Credentials(
        token=d["token"],
        refresh_token=d.get("refresh_token"),
        token_uri=d["token_uri"],
        client_id=d["client_id"],
        client_secret=d["client_secret"],
        scopes=d.get("scopes"),
    )
