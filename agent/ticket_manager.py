"""
agent/ticket_manager.py
-----------------------
Ticket creation and management for the Veridian IT Service Agent.
Historical tickets (from data/tickets.json) are read-only.
New tickets are created in memory (session) and optionally persisted
to data/tickets_session.json.
No external services.
"""

from __future__ import annotations

import json
import uuid
import datetime
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_TICKETS_FILE = _DATA_DIR / "tickets.json"
_SESSION_FILE = _DATA_DIR / "tickets_session.json"

# ---------------------------------------------------------------------------
# In-memory session store (new tickets only)
# ---------------------------------------------------------------------------

_session_tickets: List[Dict] = []
_ticket_counter: int = 1101  # Start well above historical ticket numbers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_historical() -> List[Dict]:
    """Load read-only historical tickets from JSON."""
    try:
        with open(_TICKETS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_session() -> None:
    """Persist session tickets to tickets_session.json."""
    try:
        with open(_SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(_session_tickets, f, indent=2, ensure_ascii=False)
    except Exception:
        pass  # Silently fail — in-memory still works


def _generate_ticket_id() -> str:
    global _ticket_counter
    tid = f"IT-{_ticket_counter}"
    _ticket_counter += 1
    return tid


def _now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_ticket(
    employee: str,
    email: str,
    intent: str,
    summary: str,
    status: str,
    priority: str,
    policy_id: Optional[str],
    reason: str,
    requires_human: bool,
) -> Dict:
    """
    Create a new IT ticket and store it in session memory.

    Returns the created ticket dict.
    """
    ticket_id = _generate_ticket_id()
    ticket = {
        "ticket_id": ticket_id,
        "employee": employee,
        "email": email,
        "intent": intent,
        "summary": summary,
        "status": status,
        "priority": priority,
        "policy_id": policy_id,
        "reason": reason,
        "created_at": _now_iso(),
        "requires_human": requires_human,
        "source": "session",
    }
    _session_tickets.append(ticket)
    _save_session()
    return ticket


def get_ticket(ticket_id: str) -> Optional[Dict]:
    """Return a ticket by ID (searches both historical and session)."""
    for t in _session_tickets:
        if t["ticket_id"] == ticket_id:
            return t
    for t in _load_historical():
        if t.get("ticket_id") == ticket_id:
            return t
    return None


def update_ticket(ticket_id: str, updates: Dict) -> Optional[Dict]:
    """Update a session ticket's fields. Historical tickets are immutable."""
    for t in _session_tickets:
        if t["ticket_id"] == ticket_id:
            t.update(updates)
            _save_session()
            return t
    return None


def search_tickets(query: str) -> List[Dict]:
    """
    Search both historical and session tickets for relevant matches.
    Simple substring match on issue_summary / summary fields.
    Returns all matches.
    """
    if not query:
        return []

    query_lower = query.lower()
    results = []

    for t in _load_historical():
        summary = t.get("issue_summary", "").lower()
        if any(word in summary for word in query_lower.split() if len(word) > 2):
            results.append({**t, "source": "historical"})

    for t in _session_tickets:
        summary = t.get("summary", "").lower()
        if any(word in summary for word in query_lower.split() if len(word) > 2):
            results.append(t)

    return results


def get_active_tickets() -> List[Dict]:
    """Return all tickets (historical + session) that are not closed/resolved."""
    active = []
    for t in _load_historical():
        status = t.get("status", "").lower()
        if "closed" not in status and "resolved" not in status and "rejected" not in status:
            active.append({**t, "source": "historical"})
    for t in _session_tickets:
        status = t.get("status", "").lower()
        if "closed" not in status and "resolved" not in status:
            active.append(t)
    return active


def get_closed_tickets() -> List[Dict]:
    """Return all tickets that are closed or resolved."""
    closed = []
    for t in _load_historical():
        status = t.get("status", "").lower()
        if "closed" in status or "resolved" in status or "rejected" in status:
            closed.append({**t, "source": "historical"})
    for t in _session_tickets:
        status = t.get("status", "").lower()
        if "closed" in status or "resolved" in status:
            closed.append(t)
    return closed


def get_all_tickets() -> List[Dict]:
    """Return all tickets (historical + session)."""
    historical = [{**t, "source": "historical"} for t in _load_historical()]
    return historical + _session_tickets


def get_session_tickets() -> List[Dict]:
    """Return only tickets created in this session."""
    return list(_session_tickets)


def validate_tickets() -> Dict:
    """Validate that tickets.json exists and is well-formed."""
    try:
        tickets = _load_historical()
        if not isinstance(tickets, list):
            return {"valid": False, "error": "tickets.json is not a list."}
        return {"valid": True, "count": len(tickets)}
    except FileNotFoundError:
        return {"valid": False, "error": f"tickets.json not found at {_TICKETS_FILE}"}
    except json.JSONDecodeError as e:
        return {"valid": False, "error": f"tickets.json is malformed: {e}"}
