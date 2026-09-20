"""
agent/classifier.py
-------------------
Deterministic intent classifier for the Veridian IT Service Agent.
Uses a hybrid approach: keyword matching + TF-IDF cosine similarity.
No LLM. No external API.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np


# ---------------------------------------------------------------------------
# Intent definitions — keywords drawn from the supplied knowledge base only
# ---------------------------------------------------------------------------

INTENT_KEYWORDS: Dict[str, List[str]] = {
    "password_reset": [
        "password", "reset", "locked", "lockout", "lock out", "lock-out",
        "forgot", "forgot password", "forgot my password", "can't log in",
        "cannot log in", "failed attempts", "credentials expired", "unlock",
        "account locked",
    ],
    "vpn_access": [
        "vpn", "virtual private network", "vpn access", "vpn credentials",
        "vpn expired", "vpn stopped", "vpn not working", "remote access",
        "vpn connection", "contractor vpn",
    ],
    "laptop_replacement": [
        "laptop", "laptop replacement", "laptop dead", "laptop broken",
        "laptop won't turn on", "laptop won't start", "new laptop",
        "laptop hardware", "laptop failure", "laptop flickering",
        "screen flickering", "laptop screen", "replace laptop",
    ],
    "software_installation": [
        "install", "software", "application", "app", "install software",
        "software installation", "software request", "non-catalog",
        "not in catalog", "approved catalog", "security review",
        "browser extension", "extension", "plugin", "data analysis tool",
        "productivity tool", "software catalog",
    ],
    "printer": [
        "printer", "print", "printing", "printer queue", "print spooler",
        "printer jam", "paper jam", "printer not working", "printer error",
        "printer issue", "printer offline", "printer asset",
    ],
    "mailbox": [
        "mailbox", "email full", "mailbox full", "quota", "mailbox quota",
        "can't send email", "cannot send email", "email quota",
        "inbox full", "storage full", "mail storage", "archive",
        "increase quota", "mailbox limit",
    ],
    "guest_wifi": [
        "guest wifi", "guest wi-fi", "wifi", "wi-fi", "wireless", "guest network",
        "guest access", "visitor wifi", "visitor wi-fi", "wifi credentials",
        "internet access guest", "guest internet", "visiting",
    ],
    "expense_software": [
        "expense", "expense tool", "expense software", "expense system",
        "expense management", "concur", "expenses", "reimbursement tool",
        "expense access", "expense login", "expense account",
    ],
    "security_incident": [
        "phishing", "malware", "virus", "suspicious email", "scam email",
        "security incident", "unauthorized access", "hack", "hacked",
        "ransomware", "data breach", "suspicious link", "phishing email",
        "spam email attack", "credential theft", "security threat",
    ],
    "wfh_equipment": [
        "work from home", "wfh", "remote work", "home office", "monitor",
        "home equipment", "working remotely", "working from home",
        "home monitor", "home chair", "office equipment", "remote setup",
        "allowance", "home office allowance",
    ],
    "admin_access": [
        "admin", "admin access", "administrator", "administrator access",
        "root access", "elevated access", "server access", "privileged access",
        "admin rights", "admin privileges", "system admin",
    ],
}

# TF-IDF corpus — one document per intent, combining all keywords
INTENT_CORPUS: Dict[str, str] = {
    intent: " ".join(kws) for intent, kws in INTENT_KEYWORDS.items()
}

# Pre-fit vectorizer at module load time (deterministic, fast)
_ALL_INTENTS = list(INTENT_CORPUS.keys())
_CORPUS_DOCS = [INTENT_CORPUS[i] for i in _ALL_INTENTS]

_vectorizer = TfidfVectorizer(ngram_range=(1, 3), min_df=1, analyzer="word")
_intent_matrix = _vectorizer.fit_transform(_CORPUS_DOCS)


def _normalize(text: str) -> str:
    """Lowercase, remove punctuation, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _keyword_match(text_norm: str) -> Dict[str, float]:
    """
    Return a score per intent based on how many keywords are found in text.
    Score = matched_count / total_keywords_in_intent (normalised 0-1).
    """
    scores: Dict[str, float] = {}
    for intent, kws in INTENT_KEYWORDS.items():
        hits = sum(1 for kw in kws if kw in text_norm)
        scores[intent] = hits / max(len(kws), 1)
    return scores


def classify_intent(user_input: str) -> Dict:
    """
    Classify the intent of a user message.

    Returns a dict with:
        intent        : str   — intent label or 'unknown'
        confidence    : float — 0.0 – 1.0
        matched_terms : list  — keywords found in the input
    """
    if not user_input or not user_input.strip():
        return {"intent": "unknown", "confidence": 0.0, "matched_terms": []}

    text_norm = _normalize(user_input)

    # --- keyword scoring ---
    kw_scores = _keyword_match(text_norm)
    best_kw_intent = max(kw_scores, key=lambda k: kw_scores[k])
    best_kw_score = kw_scores[best_kw_intent]

    # Collect matched terms for best intent
    matched = [
        kw for kw in INTENT_KEYWORDS.get(best_kw_intent, [])
        if kw in text_norm
    ]

    # --- TF-IDF similarity ---
    try:
        query_vec = _vectorizer.transform([text_norm])
        sims = cosine_similarity(query_vec, _intent_matrix).flatten()
        best_tfidf_idx = int(np.argmax(sims))
        best_tfidf_intent = _ALL_INTENTS[best_tfidf_idx]
        best_tfidf_score = float(sims[best_tfidf_idx])
    except Exception:
        best_tfidf_intent = "unknown"
        best_tfidf_score = 0.0

    # --- combine: keyword takes priority if strong, else blend ---
    if best_kw_score >= 0.05:          # At least one keyword matched
        # Keyword match wins; boost confidence with TF-IDF agreement
        if best_kw_intent == best_tfidf_intent:
            confidence = min(0.5 * best_kw_score + 0.5 * best_tfidf_score + 0.3, 1.0)
        else:
            confidence = min(best_kw_score + 0.15, 0.95)
        final_intent = best_kw_intent
    else:
        # Fall back to TF-IDF only
        confidence = best_tfidf_score
        final_intent = best_tfidf_intent
        matched = []

    # Low-confidence threshold → unknown
    CONFIDENCE_THRESHOLD = 0.15
    if confidence < CONFIDENCE_THRESHOLD:
        return {"intent": "unknown", "confidence": round(confidence, 3), "matched_terms": []}

    return {
        "intent": final_intent,
        "confidence": round(min(confidence, 1.0), 3),
        "matched_terms": matched[:8],  # cap for display
    }
