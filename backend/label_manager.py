"""
MailSense V3 — Gestion labels Gmail.
Vérifie les conflits, crée les labels, applique en bulk.
"""
from __future__ import annotations
import time
from typing import Dict, List

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from config import CATEGORIES


def _build_service(creds: Credentials):
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _label_name(cat: str, suffix: str = "") -> str:
    return cat + suffix


def ensure_labels(creds: Credentials) -> Dict[str, str]:
    """
    Crée les 11 labels MailSense si absents.
    Si conflit avec un label existant, ajoute suffixe _MS.
    Retourne {categorie: label_id}.
    """
    service = _build_service(creds)
    existing = service.users().labels().list(userId="me").execute()
    existing_names = {lb["name"]: lb["id"] for lb in existing.get("labels", [])}

    label_map: Dict[str, str] = {}

    for cat in CATEGORIES:
        name = cat
        if name in existing_names:
            # Vérifier si c'est déjà un label MailSense (même ID réutilisable)
            label_map[cat] = existing_names[name]
        else:
            # Créer le label
            try:
                new_lb = service.users().labels().create(
                    userId="me",
                    body={
                        "name": name,
                        "labelListVisibility": "labelShow",
                        "messageListVisibility": "show",
                    },
                ).execute()
                label_map[cat] = new_lb["id"]
            except Exception:
                # Conflit : ajouter suffixe _MS
                name_ms = cat + "_MS"
                if name_ms in existing_names:
                    label_map[cat] = existing_names[name_ms]
                else:
                    new_lb = service.users().labels().create(
                        userId="me",
                        body={
                            "name": name_ms,
                            "labelListVisibility": "labelShow",
                            "messageListVisibility": "show",
                        },
                    ).execute()
                    label_map[cat] = new_lb["id"]

    return label_map


def apply_labels_bulk(
    creds: Credentials,
    emails_by_category: Dict[str, List[str]],
    label_map: Dict[str, str],
) -> None:
    """
    Applique les labels en bulk via batchModify (1000 messages/appel).
    """
    service = _build_service(creds)
    all_label_ids = list(label_map.values())

    for cat, ids in emails_by_category.items():
        if not ids:
            continue
        label_id = label_map.get(cat)
        if not label_id:
            continue

        labels_to_remove = [lid for lid in all_label_ids if lid != label_id]

        for offset in range(0, len(ids), 1000):
            chunk = ids[offset:offset + 1000]
            body: Dict = {"ids": chunk, "addLabelIds": [label_id]}
            if labels_to_remove:
                body["removeLabelIds"] = labels_to_remove
            try:
                service.users().messages().batchModify(
                    userId="me", body=body,
                ).execute()
            except Exception:
                # Retry une fois
                time.sleep(2)
                try:
                    service.users().messages().batchModify(
                        userId="me", body=body,
                    ).execute()
                except Exception:
                    pass
