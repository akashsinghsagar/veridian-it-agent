"""
agent/orchestrator.py
---------------------
Central agent pipeline for the Veridian IT Service Agent.
Coordinates: normalise → classify → retrieve → search tickets → evaluate → ticket → audit → respond.
No LLM. No external API.
"""

from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Dict, List, Optional

from agent import classifier, retriever, policy_engine, ticket_manager, audit

# ---------------------------------------------------------------------------
# Data paths
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_REQUESTS_FILE = _DATA_DIR / "requests.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_requests() -> List[Dict]:
    try:
        with open(_REQUESTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _normalize_input(text: str) -> str:
    """Strip excess whitespace."""
    return re.sub(r"\s+", " ", text.strip())


def _extract_entities(user_input: str, intent: str) -> Dict:
    """
    Extract key entities from the user input.
    Deterministic — no NLP model.
    Returns a dict of relevant entities.
    """
    entities: Dict = {}
    lower = user_input.lower()

    # Printer asset tag — look for common patterns like VRD-PRN-042 or asset tag mentions
    asset_tag_match = re.search(
        r"\b([A-Z]{2,6}[-_]?[A-Z0-9]{2,10}[-_]?\d{2,6})\b",
        user_input,
        re.IGNORECASE,
    )
    if asset_tag_match and intent == "printer":
        entities["printer_asset_tag"] = asset_tag_match.group(1).upper()

    # Days per week (WFH)
    days_match = re.search(r"(\d+)\s*day", lower)
    if days_match:
        entities["days_per_week"] = int(days_match.group(1))

    # Laptop age in years
    age_match = re.search(r"(\d+(?:\.\d+)?)\s*year", lower)
    if age_match:
        entities["laptop_age_years"] = float(age_match.group(1))

    # Employee/contractor detection
    if any(kw in lower for kw in ["contractor", "contract", "freelancer", "vendor"]):
        entities["employment_type"] = "contractor"
    elif any(kw in lower for kw in ["full-time", "full time", "fulltime", "permanent"]):
        entities["employment_type"] = "full_time"

    return entities


def _find_related_tickets(user_input: str, intent: str) -> List[Dict]:
    """Search historical + session tickets for relevant context."""
    # Use intent as primary search term, plus key words from input
    search_terms = intent.replace("_", " ")
    results = ticket_manager.search_tickets(search_terms)

    # Also search by user input keywords
    words = [w for w in user_input.lower().split() if len(w) > 3]
    for word in words[:4]:  # cap to avoid noise
        extra = ticket_manager.search_tickets(word)
        for t in extra:
            if t not in results:
                results.append(t)

    return results[:5]  # cap at 5 related tickets


def _build_state(
    request_id: str,
    user_input: str,
    intent_result: Dict,
    entities: Dict,
    policy: Dict,
    decision: Dict,
    ticket: Optional[Dict],
    trail: List[Dict],
) -> Dict:
    """Assemble the complete agent state object."""
    return {
        "request_id": request_id,
        "user_input": user_input,
        "intent": intent_result.get("intent", "unknown"),
        "intent_confidence": intent_result.get("confidence", 0.0),
        "matched_terms": intent_result.get("matched_terms", []),
        "entities": entities,
        "policy_id": decision.get("policy_id") or policy.get("policy_id"),
        "policy_confidence": policy.get("similarity", 0.0),
        "decision": decision.get("decision", "NO_ACTION"),
        "ticket_id": ticket.get("ticket_id") if ticket else None,
        "requires_human": decision.get("requires_human", False),
        "audit_events": trail,
    }


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def process(
    user_input: str,
    employee_name: str = "Employee",
    employee_email: str = "employee@veridian-corp.example",
    request_id: str = "NEW",
) -> Dict:
    """
    Full agent pipeline.

    Parameters
    ----------
    user_input      : raw user message
    employee_name   : display name for ticket creation
    employee_email  : email for ticket record
    request_id      : optional REQ-XX identifier

    Returns
    -------
    {
        "user_message"   : str,
        "intent"         : dict,
        "policy"         : dict,
        "related_tickets": list,
        "decision"       : dict,
        "response"       : str,
        "ticket"         : dict | None,
        "audit"          : list,
        "state"          : dict,
    }
    """

    trail = audit.new_trail()

    # ------------------------------------------------------------------
    # Guard: empty input
    # ------------------------------------------------------------------
    if not user_input or not user_input.strip():
        audit.log(trail, audit.EV_ERROR, "Empty input received")
        return {
            "user_message": user_input,
            "intent": {"intent": "unknown", "confidence": 0.0, "matched_terms": []},
            "policy": {"policy_id": None},
            "related_tickets": [],
            "decision": {
                "decision": policy_engine.FOLLOW_UP,
                "reason": "No input provided.",
                "response": "It looks like your message was empty. Please describe your IT issue and I will be happy to help.",
                "next_action": "Await user input.",
                "policy_id": None,
                "risk_level": policy_engine.RISK_LOW,
                "requires_human": False,
                "create_ticket": False,
                "ticket_priority": "Low",
                "ticket_status": "Pending Information",
                "route_to": None,
            },
            "response": "It looks like your message was empty. Please describe your IT issue and I will be happy to help.",
            "ticket": None,
            "audit": trail,
            "state": {},
        }

    # ------------------------------------------------------------------
    # Step 1: Normalize
    # ------------------------------------------------------------------
    normalized = _normalize_input(user_input)
    audit.log(trail, audit.EV_REQUEST_RECEIVED, f"'{normalized[:80]}...' " if len(normalized) > 80 else f"'{normalized}'")
    audit.log(trail, audit.EV_INPUT_NORMALIZED)

    # ------------------------------------------------------------------
    # Step 2: Classify intent
    # ------------------------------------------------------------------
    intent_result = classifier.classify_intent(normalized)
    audit.log(
        trail,
        audit.EV_INTENT_DETECTED,
        f"{intent_result['intent']} (confidence={intent_result['confidence']})",
    )

    # ------------------------------------------------------------------
    # Step 3: Extract entities
    # ------------------------------------------------------------------
    entities = _extract_entities(normalized, intent_result["intent"])
    if entities:
        audit.log(trail, audit.EV_ENTITIES_EXTRACTED, str(entities))

    # ------------------------------------------------------------------
    # Step 4: Retrieve policy
    # ------------------------------------------------------------------
    policy = retriever.retrieve_policy(normalized)
    if policy.get("policy_id"):
        audit.log(trail, audit.EV_POLICY_RETRIEVED, f"{policy['policy_id']} — {policy.get('title', '')} (sim={policy.get('similarity', 0):.2f})")
    else:
        audit.log(trail, audit.EV_POLICY_RETRIEVED, "No policy above similarity threshold")

    # ------------------------------------------------------------------
    # Step 5: Search existing tickets
    # ------------------------------------------------------------------
    related_tickets = _find_related_tickets(normalized, intent_result["intent"])
    audit.log(trail, audit.EV_TICKETS_SEARCHED, f"{len(related_tickets)} related ticket(s) found")

    # ------------------------------------------------------------------
    # Step 6: Evaluate policy
    # ------------------------------------------------------------------
    decision = policy_engine.evaluate(
        intent=intent_result["intent"],
        intent_confidence=intent_result["confidence"],
        user_input=normalized,
        policy=policy,
        entities=entities,
        related_tickets=related_tickets,
    )
    audit.log(trail, audit.EV_POLICY_EVALUATED)
    audit.log(
        trail,
        audit.EV_DECISION_MADE,
        f"{decision['decision']} | risk={decision['risk_level']} | human={decision['requires_human']}",
    )

    # ------------------------------------------------------------------
    # Step 7: Create ticket if required
    # ------------------------------------------------------------------
    ticket: Optional[Dict] = None
    if decision.get("create_ticket"):
        # Build a clean summary from the user message
        summary = normalized[:120] if len(normalized) > 120 else normalized
        try:
            ticket = ticket_manager.create_ticket(
                employee=employee_name,
                email=employee_email,
                intent=intent_result["intent"],
                summary=summary,
                status=decision.get("ticket_status", "Open"),
                priority=decision.get("ticket_priority", "Medium"),
                policy_id=decision.get("policy_id"),
                reason=decision.get("reason", ""),
                requires_human=decision.get("requires_human", False),
            )
            audit.log(trail, audit.EV_TICKET_CREATED, f"{ticket['ticket_id']} — {ticket['status']}")
        except Exception as e:
            audit.log(trail, audit.EV_ERROR, f"Ticket creation failed: {e}")
    else:
        audit.log(trail, audit.EV_TICKET_SKIPPED, "No ticket required for this decision")

    # ------------------------------------------------------------------
    # Step 8: Finalise response
    # ------------------------------------------------------------------
    response_text = decision.get("response", "I was unable to process this request. Please contact IT directly.")
    audit.log(trail, audit.EV_RESPONSE_GENERATED)

    # ------------------------------------------------------------------
    # Assemble state
    # ------------------------------------------------------------------
    state = _build_state(
        request_id=request_id,
        user_input=normalized,
        intent_result=intent_result,
        entities=entities,
        policy=policy,
        decision=decision,
        ticket=ticket,
        trail=trail,
    )

    return {
        "user_message": normalized,
        "intent": intent_result,
        "policy": policy,
        "related_tickets": related_tickets,
        "decision": decision,
        "response": response_text,
        "ticket": ticket,
        "audit": trail,
        "state": state,
    }


# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------

def validate_data_sources() -> Dict:
    """
    Validate all required data files on startup.
    Returns a dict with status for each file.
    """
    policies_status = retriever.validate_policies()
    tickets_status = ticket_manager.validate_tickets()

    # Validate requests.json
    try:
        requests = _load_requests()
        if not isinstance(requests, list):
            requests_status = {"valid": False, "error": "requests.json is not a list."}
        else:
            requests_status = {"valid": True, "count": len(requests)}
    except FileNotFoundError:
        requests_status = {"valid": False, "error": f"requests.json not found at {_REQUESTS_FILE}"}
    except Exception as e:
        requests_status = {"valid": False, "error": str(e)}

    return {
        "policies": policies_status,
        "tickets": tickets_status,
        "requests": requests_status,
    }


def load_requests() -> List[Dict]:
    """Return all employee requests from requests.json."""
    return _load_requests()
