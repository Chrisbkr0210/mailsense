"""
MailSense V3 — Classification emails via API Anthropic (async, 4 batches parallèles).
Retry avec backoff exponentiel sur 429. Parsing robuste.
"""
from __future__ import annotations
import asyncio
import re
import time
from typing import List, Dict, Optional, Callable

import anthropic

from config import (
    ANTHROPIC_API_KEY, MODEL_PREVIEW, MODEL_FULL,
    CATEGORIES, CLASSIFICATION_PROMPT, RETRY_ATTEMPTS,
)

# Taille de batch et parallélisme
BATCH_SIZE    = 300
PARALLELISM   = 4   # batches simultanés

# Coût approximatif haiku ($/MTok)
COST_INPUT    = 0.80 / 1_000_000
COST_OUTPUT   = 4.00 / 1_000_000

_async_client: Optional[anthropic.AsyncAnthropic] = None
_sync_client:  Optional[anthropic.Anthropic]      = None


def _get_sync_client() -> anthropic.Anthropic:
    global _sync_client
    if _sync_client is None:
        _sync_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _sync_client


def _get_async_client() -> anthropic.AsyncAnthropic:
    global _async_client
    if _async_client is None:
        _async_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _async_client


def _build_email_line(em: Dict) -> str:
    sender  = (em.get("sender",  "") or "")[:60]
    subject = (em.get("subject", "") or "")[:80]
    snippet = (em.get("snippet", "") or "")[:200]
    return "{id}|De:{sender}|Sujet:{subject}|Extrait:{snippet}".format(
        id=em["id"], sender=sender, subject=subject, snippet=snippet,
    )


def _parse_response(text: str, email_ids: List[str]) -> Dict[str, str]:
    """Parse EMAIL_ID|CATEGORIE. Robuste aux backticks/espaces."""
    text = re.sub(r"```[a-z]*", "", text).strip()
    valid_cats = set(CATEGORIES)
    id_set = set(email_ids)
    results: Dict[str, str] = {}

    for line in text.splitlines():
        line = line.strip()
        if "|" not in line:
            continue
        parts = line.split("|", 1)
        if len(parts) != 2:
            continue
        eid, cat = parts[0].strip(), parts[1].strip().upper()
        if eid in id_set and cat in valid_cats:
            results[eid] = cat

    for eid in email_ids:
        if eid not in results:
            results[eid] = "NEWSLETTERS_MARKETING"

    return results


def _build_prompt(emails: List[Dict], corrections: Dict[str, str]) -> str:
    corrections_text = ""
    if corrections:
        lines = ["Corrections utilisateur (priorité absolue) :"]
        for eid, cat in corrections.items():
            lines.append("  - Email {} → {}".format(eid, cat))
        corrections_text = "\n".join(lines)
    return CLASSIFICATION_PROMPT.format(
        corrections=corrections_text,
        emails="\n".join(_build_email_line(e) for e in emails),
    )


# ── Sync (preview uniquement) ─────────────────────────────────────────────────

def classify_batch_sync(emails: List[Dict], corrections: Dict[str, str], model: str) -> Dict[str, str]:
    client = _get_sync_client()
    email_ids = [e["id"] for e in emails]
    prompt = _build_prompt(emails, corrections)

    for attempt in range(RETRY_ATTEMPTS):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
                timeout=60.0,
            )
            return _parse_response(response.content[0].text, email_ids)
        except Exception:
            if attempt < RETRY_ATTEMPTS - 1:
                time.sleep(2 ** attempt)

    return {eid: "NEWSLETTERS_MARKETING" for eid in email_ids}


def classify_preview(emails: List[Dict]) -> List[Dict]:
    results = classify_batch_sync(emails, {}, MODEL_PREVIEW)
    for em in emails:
        em["category"] = results.get(em["id"], "NEWSLETTERS_MARKETING")
    return emails


# ── Async (traitement complet, 4 batches en parallèle) ────────────────────────

async def _classify_batch_async(
    sem: asyncio.Semaphore,
    emails: List[Dict],
    corrections: Dict[str, str],
    model: str,
) -> tuple:
    """Retourne (results_dict, input_tokens, output_tokens)."""
    client = _get_async_client()
    email_ids = [e["id"] for e in emails]
    prompt = _build_prompt(emails, corrections)

    async with sem:
        for attempt in range(RETRY_ATTEMPTS):
            try:
                response = await client.messages.create(
                    model=model,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}],
                    timeout=60.0,
                )
                results = _parse_response(response.content[0].text, email_ids)
                in_tok  = response.usage.input_tokens
                out_tok = response.usage.output_tokens
                return results, in_tok, out_tok
            except anthropic.RateLimitError:
                wait = 5 * (2 ** attempt)
                await asyncio.sleep(wait)
            except Exception:
                if attempt < RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(2 ** attempt)

    return {eid: "NEWSLETTERS_MARKETING" for eid in email_ids}, 0, 0


async def classify_all_parallel(
    emails: List[Dict],
    corrections: Dict[str, str],
    progress_callback: Callable,
) -> Dict[str, str]:
    """
    Classifie tous les emails par batches de BATCH_SIZE, PARALLELISM batches simultanés.
    progress_callback(processed, total, categories, cost_usd) appelé après chaque batch.
    """
    total = len(emails)
    all_results: Dict[str, str] = {}
    categories: Dict[str, int] = {cat: 0 for cat in CATEGORIES}
    processed = 0
    total_cost = 0.0

    sem = asyncio.Semaphore(PARALLELISM)

    # Découper en batches
    batches = [emails[i:i + BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]

    # Traiter par groupes de PARALLELISM
    for group_start in range(0, len(batches), PARALLELISM):
        group = batches[group_start:group_start + PARALLELISM]

        tasks = [
            _classify_batch_async(sem, batch, corrections, MODEL_FULL)
            for batch in group
        ]
        group_results = await asyncio.gather(*tasks)

        for (batch_results, in_tok, out_tok), batch in zip(group_results, group):
            all_results.update(batch_results)
            for cat in batch_results.values():
                if cat in categories:
                    categories[cat] += 1
            processed += len(batch)
            total_cost += in_tok * COST_INPUT + out_tok * COST_OUTPUT

        progress_callback(
            min(processed, total), total, dict(categories), round(total_cost, 4)
        )

    return all_results
