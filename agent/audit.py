"""
agent/audit.py
--------------
Structured audit trail for the Veridian IT Service Agent.
Every processing step is recorded with a timestamp.
No external services.
"""

from __future__ import annotations

import datetime
from typing import List, Dict


def _now() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


def new_trail() -> List[Dict]:
    """Create a new empty audit trail list."""
    return []


def log(trail: List[Dict], event: str, detail: str = "") -> None:
    """
    Append an event to the audit trail.

    Parameters
    ----------
    trail  : the list to append to (modified in place)
    event  : short event label (e.g. 'INTENT_DETECTED')
    detail : optional additional detail string
    """
    entry = {
        "timestamp": _now(),
        "event": event,
        "detail": detail,
    }
    trail.append(entry)


def format_trail(trail: List[Dict]) -> str:
    """
    Format the audit trail as a human-readable string for display.

    Example output:
        12:30:01  REQUEST_RECEIVED
        12:30:01  INTENT_DETECTED: vpn_access (confidence=0.91)
        12:30:01  POLICY_RETRIEVED: KB-02
        ...
    """
    lines = []
    for entry in trail:
        ts = entry.get("timestamp", "")
        event = entry.get("event", "")
        detail = entry.get("detail", "")
        if detail:
            lines.append(f"{ts}  {event}: {detail}")
        else:
            lines.append(f"{ts}  {event}")
    return "\n".join(lines)


# Convenience event labels
EV_REQUEST_RECEIVED = "REQUEST_RECEIVED"
EV_INPUT_NORMALIZED = "INPUT_NORMALIZED"
EV_INTENT_DETECTED = "INTENT_DETECTED"
EV_ENTITIES_EXTRACTED = "ENTITIES_EXTRACTED"
EV_POLICY_RETRIEVED = "POLICY_RETRIEVED"
EV_TICKETS_SEARCHED = "TICKETS_SEARCHED"
EV_POLICY_EVALUATED = "POLICY_EVALUATED"
EV_DECISION_MADE = "DECISION_MADE"
EV_TICKET_CREATED = "TICKET_CREATED"
EV_TICKET_SKIPPED = "TICKET_SKIPPED"
EV_RESPONSE_GENERATED = "RESPONSE_GENERATED"
EV_ERROR = "ERROR"
