# MailSense — Règles absolues Claude

## Contexte du projet

Catégorisation de ~10 660+ emails Gmail (c.bouchakour35@gmail.com) via Claude Haiku.
Modèle : `claude-haiku-4-5-20251001` exclusivement.
Budget max : **$9.00** — arrêt propre si atteint.

## Ce qu'il faut TOUJOURS faire

- Sauvegarder `progress.json` après CHAQUE batch (écriture atomique via `.tmp`)
- Retry 3x sur erreur API (backoff exponentiel : 2s, 4s), puis log et continuer
- Afficher la progression après chaque batch : `X/total (XX%) $X.XX Batch #N`
- Vérifier le budget avant chaque batch — arrêter proprement si `>= $9.00`
- Traiter TOUS les emails (`in:all` — inbox, archivés, spam, corbeille)
- Utiliser le cache expéditeur (`memory/rules.json`) avant tout appel API
- Mettre à jour `memory/rules.json` après chaque batch avec les nouveaux expéditeurs classifiés
- Utiliser les labels `MailSense/CATEGORIE` (avec préfixe) dans tous les scripts

## Ce qu'il ne faut JAMAIS faire

- Dépasser le budget de $9.00
- Demander confirmation à l'utilisateur (autonomie totale)
- Utiliser Sonnet ou Opus (Haiku uniquement)
- Envoyer le body ou snippet des emails à l'API (sender + subject uniquement)
- Créer de nouvelles catégories hors des 11 définies
- Classer une newsletter normale dans POUBELLE_SPAM
- Ignorer les emails archivés, spam ou corbeille

## Règles métier

### Catégories et priorités

| Catégorie | Règle clé | Priorité |
|---|---|---|
| ADMINISTRATIF | Courriers officiels, impôts, CAF, Google account (hors santé) | Normale |
| BANQUE_FINANCE | Banque, virement, relevé, crypto, Revolut, PayPal | Normale |
| FACTURES_PAIEMENTS | Reçus de paiement reçus (ponctuel ou mensuel) | Normale |
| CONTRATS_ABONNEMENTS | Signup, renouvellement, confirmation d'abonnement | Normale |
| EMPLOI_PRO | Travail, recrutement, LinkedIn pro, RH | Normale |
| SANTE | CPAM, mutuelle, médecin, pharmacie, arrêt travail | **HAUTE** |
| TRANSPORT_VOYAGE | SNCF, vol, hôtel, Uber, Uber Eats, livraison colis | Normale |
| NEWSLETTERS_MARKETING | Newsletters, promo, soldes, pub commerciale normale | Basse |
| RESEAUX_SOCIAUX_PLATEFORMES | Facebook, Instagram, Twitter, YouTube, Discord | Basse |
| PERSONNEL | Famille, amis, contacts personnels directs | Normale |
| POUBELLE_SPAM | Arnaque / phishing UNIQUEMENT | Basse |

### Règles de distinction critiques

- **FACTURES vs CONTRATS** : FACTURES = le reçu de paiement. CONTRATS = le signup ou renouvellement.
  - "Votre facture Netflix de mars" → FACTURES_PAIEMENTS
  - "Bienvenue chez Netflix" / "Abonnement renouvelé" → CONTRATS_ABONNEMENTS
- **POUBELLE_SPAM** : arnaque / phishing UNIQUEMENT. Une newsletter normale → NEWSLETTERS_MARKETING.
- **SANTE prioritaire** : CPAM, ameli, arrêt de travail, mutuelle → SANTE (pas ADMINISTRATIF).
- **Livraisons** : Uber Eats, Amazon livraison, Deliveroo → TRANSPORT_VOYAGE.

## Architecture technique

```
main.py                  → passe principale (tous les emails)
classify_unlabeled.py    → 2ème passe (emails sans label MailSense/)
categorizer.py           → classification Claude Haiku + cache expéditeur
gmail_client.py          → OAuth2, batch fetch, labels
config.py                → configuration centrale (BATCH_SIZE=500, PAUSE=62s)
progress.json            → source de vérité pour la reprise
memory/rules.json        → cache expéditeur → catégorie (alimenté automatiquement)
memory/preferences.json  → règles métier utilisateur
```

## Paramètres de traitement

- **Modèle** : `claude-haiku-4-5-20251001`
- **Batch** : 500 emails/appel API
- **Pause** : 62 secondes entre batches (rate limit 50K tokens/min)
- **Retry** : 3 tentatives, backoff 2^n secondes
- **Format réponse API** : `EMAIL_ID|CATEGORIE` (une ligne par email)
- **Données envoyées** : expéditeur + objet UNIQUEMENT (pas de snippet, pas de body)
- **Labels Gmail** : `MailSense/CATEGORIE` (avec préfixe dans tous les scripts)
- **Couverture** : `in:all` (inbox + archivés + spam + corbeille)

## Reprise automatique

`progress.json` est sauvegardé après chaque batch via écriture atomique (`.tmp` → rename).
Relancer `py main.py` reprend exactement au dernier email traité. Jamais de doublon.

## Budget et coûts

- Tarif Haiku : $0.80/M tokens input, $4.00/M tokens output
- Budget max : $9.00 (vérifier avant chaque batch)
- Cache expéditeur : économie estimée 30-50% sur les batches suivants
- Suppression du snippet : économie ~40% de tokens input
