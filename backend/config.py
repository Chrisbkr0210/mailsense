"""
MailSense V3 — Configuration
"""
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent

load_dotenv(BASE_DIR / ".env")

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL_PREVIEW    = "claude-sonnet-4-20250514"
MODEL_FULL       = "claude-haiku-4-5-20251001"

# Google OAuth
GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI  = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback")
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/gmail.modify",
    "openid",
    "email",
]

# App
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-prod")
ENV        = os.getenv("ENV", "development")
SESSION_TTL_SECONDS = 7200  # 2 heures

# Gmail
GMAIL_PAGE_SIZE   = 500
PREVIEW_COUNT     = 50
BATCH_SIZE        = 100
BATCH_PAUSE       = 0.5  # secondes
RETRY_ATTEMPTS    = 3

# Categories
CATEGORIES = [
    "ADMINISTRATIF",
    "BANQUE_FINANCE",
    "FACTURES_PAIEMENTS",
    "CONTRATS_ABONNEMENTS",
    "EMPLOI_PRO",
    "SANTE",
    "TRANSPORT_VOYAGE",
    "NEWSLETTERS_MARKETING",
    "RESEAUX_SOCIAUX",
    "PERSONNEL",
    "SPAM_PHISHING",
]

CLASSIFICATION_PROMPT = """\
Tu es un classifieur d'emails. Classe chaque email dans UNE SEULE catégorie.

Catégories : ADMINISTRATIF, BANQUE_FINANCE, FACTURES_PAIEMENTS, CONTRATS_ABONNEMENTS, EMPLOI_PRO, SANTE, TRANSPORT_VOYAGE, NEWSLETTERS_MARKETING, RESEAUX_SOCIAUX, PERSONNEL, SPAM_PHISHING

Règles :
- SPAM_PHISHING = arnaque/phishing uniquement. Newsletter normale = NEWSLETTERS_MARKETING.
- Abonnement récurrent = CONTRATS_ABONNEMENTS. Achat unique = FACTURES_PAIEMENTS.
- Sécurité sociale/arrêt maladie = SANTE.
- Livraison = TRANSPORT_VOYAGE.
- LinkedIn emploi = EMPLOI_PRO. LinkedIn notif = RESEAUX_SOCIAUX.
{corrections}

Format strict, une ligne par email : EMAIL_ID|CATEGORIE
Aucune explication. Aucune nouvelle catégorie.

Emails :
{emails}"""
