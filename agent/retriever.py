"""
agent/retriever.py
------------------
Policy retriever for the Veridian IT Service Agent.
Loads policies.json and uses TF-IDF + cosine similarity to find relevant policies.
No LLM. No external API.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_POLICIES_FILE = _DATA_DIR / "policies.json"

# ---------------------------------------------------------------------------
# Module-level cache
# ---------------------------------------------------------------------------

_policies: Optional[List[Dict]] = None
_vectorizer: Optional[TfidfVectorizer] = None
_policy_matrix = None


def _load_policies() -> List[Dict]:
    """Load and cache policies from JSON."""
    global _policies
    if _policies is None:
        with open(_POLICIES_FILE, "r", encoding="utf-8") as f:
            _policies = json.load(f)
    return _policies


def _build_index():
    """Build the TF-IDF index from policy text."""
    global _vectorizer, _policy_matrix
    if _vectorizer is not None:
        return
    policies = _load_policies()
    docs = [
        f"{p['policy_id']} {p['title']} {p['policy']}"
        for p in policies
    ]
    _vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, analyzer="word")
    _policy_matrix = _vectorizer.fit_transform(docs)


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def retrieve_policy(query: str, top_k: int = 1) -> Dict:
    """
    Retrieve the most relevant policy for the query.

    Returns:
        {
            "policy_id": "KB-02",
            "title": "VPN Access",
            "policy": "...",
            "source": "...",
            "similarity": 0.87
        }
        or {"policy_id": None, "similarity": 0.0, "source": None}
    """
    if not query or not query.strip():
        return {"policy_id": None, "similarity": 0.0, "source": None}

    _build_index()
    policies = _load_policies()

    query_norm = _normalize(query)
    try:
        query_vec = _vectorizer.transform([query_norm])
        sims = cosine_similarity(query_vec, _policy_matrix).flatten()
    except Exception:
        return {"policy_id": None, "similarity": 0.0, "source": None}

    best_idx = int(np.argmax(sims))
    best_sim = float(sims[best_idx])

    SIMILARITY_THRESHOLD = 0.08
    if best_sim < SIMILARITY_THRESHOLD:
        return {"policy_id": None, "similarity": round(best_sim, 3), "source": None}

    best_policy = policies[best_idx]
    return {
        "policy_id": best_policy["policy_id"],
        "title": best_policy["title"],
        "policy": best_policy["policy"],
        "source": best_policy["source"],
        "similarity": round(best_sim, 3),
    }


def retrieve_policy_by_id(policy_id: str) -> Optional[Dict]:
    """Return a specific policy by its ID."""
    policies = _load_policies()
    for p in policies:
        if p["policy_id"] == policy_id:
            return p
    return None


def retrieve_top_policies(query: str, top_k: int = 3) -> List[Dict]:
    """Return top-k relevant policies with similarity scores."""
    if not query or not query.strip():
        return []

    _build_index()
    policies = _load_policies()

    query_norm = _normalize(query)
    try:
        query_vec = _vectorizer.transform([query_norm])
        sims = cosine_similarity(query_vec, _policy_matrix).flatten()
    except Exception:
        return []

    SIMILARITY_THRESHOLD = 0.05
    indexed = sorted(enumerate(sims), key=lambda x: x[1], reverse=True)
    results = []
    for idx, sim in indexed[:top_k]:
        if sim < SIMILARITY_THRESHOLD:
            continue
        p = policies[idx]
        results.append({
            "policy_id": p["policy_id"],
            "title": p["title"],
            "policy": p["policy"],
            "source": p["source"],
            "similarity": round(float(sim), 3),
        })
    return results


def get_all_policies() -> List[Dict]:
    """Return the full policy list."""
    return _load_policies()


def validate_policies() -> Dict:
    """Validate that the policies file exists and is well-formed."""
    try:
        policies = _load_policies()
        if not isinstance(policies, list) or len(policies) == 0:
            return {"valid": False, "error": "policies.json is empty or not a list."}
        for p in policies:
            for field in ["policy_id", "title", "policy", "source"]:
                if field not in p:
                    return {"valid": False, "error": f"Policy missing field '{field}'."}
        return {"valid": True, "count": len(policies)}
    except FileNotFoundError:
        return {"valid": False, "error": f"policies.json not found at {_POLICIES_FILE}"}
    except json.JSONDecodeError as e:
        return {"valid": False, "error": f"policies.json is malformed: {e}"}
