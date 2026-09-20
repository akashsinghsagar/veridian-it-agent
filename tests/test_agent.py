"""
tests/test_agent.py
-------------------
pytest test suite for the Veridian IT Service Agent.
Tests all 15 employee requests (REQ-01 to REQ-15) plus direct queries.
No external services. All local.

Run with:
    pytest -q
"""

import pytest
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import orchestrator, classifier, retriever, policy_engine, ticket_manager, audit


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture(autouse=True)
def reset_session_tickets():
    """Reset in-memory session tickets before each test."""
    ticket_manager._session_tickets.clear()
    ticket_manager._ticket_counter = 1101
    yield
    ticket_manager._session_tickets.clear()


# ===========================================================================
# Data validation tests
# ===========================================================================

def test_policies_load():
    """policies.json loads and contains at least 11 policies."""
    result = retriever.validate_policies()
    assert result["valid"] is True, result.get("error")
    assert result["count"] >= 11


def test_tickets_load():
    """tickets.json loads and contains at least 10 historical tickets."""
    result = ticket_manager.validate_tickets()
    assert result["valid"] is True, result.get("error")
    assert result["count"] >= 10


def test_requests_load():
    """requests.json loads and contains 15 employee requests."""
    validation = orchestrator.validate_data_sources()
    assert validation["requests"]["valid"] is True
    assert validation["requests"]["count"] == 15


# ===========================================================================
# Intent classifier tests
# ===========================================================================

def test_classifier_password_reset():
    r = classifier.classify_intent("I forgot my password")
    assert r["intent"] == "password_reset"
    assert r["confidence"] > 0.2


def test_classifier_vpn():
    r = classifier.classify_intent("My VPN credentials expired")
    assert r["intent"] == "vpn_access"
    assert r["confidence"] > 0.2


def test_classifier_laptop():
    r = classifier.classify_intent("My laptop is completely dead")
    assert r["intent"] == "laptop_replacement"


def test_classifier_security():
    r = classifier.classify_intent("I got a phishing email")
    assert r["intent"] == "security_incident"


def test_classifier_mailbox():
    r = classifier.classify_intent("My mailbox is full and I cannot send emails")
    assert r["intent"] == "mailbox"


def test_classifier_unknown():
    r = classifier.classify_intent("hey can you help, its not working")
    # Either unknown or very low confidence
    assert r["intent"] == "unknown" or r["confidence"] < 0.4


def test_classifier_empty():
    r = classifier.classify_intent("")
    assert r["intent"] == "unknown"
    assert r["confidence"] == 0.0


def test_classifier_guest_wifi():
    r = classifier.classify_intent("I need guest Wi-Fi for a visitor")
    assert r["intent"] == "guest_wifi"


def test_classifier_wfh():
    r = classifier.classify_intent("I work from home 4 days a week, how do I get a monitor?")
    assert r["intent"] == "wfh_equipment"


def test_classifier_admin_access():
    r = classifier.classify_intent("I need admin access to the server")
    assert r["intent"] == "admin_access"


# ===========================================================================
# Policy retriever tests
# ===========================================================================

def test_retriever_vpn():
    r = retriever.retrieve_policy("VPN credentials expired")
    assert r["policy_id"] == "KB-02"
    assert r["similarity"] > 0.1


def test_retriever_guest_wifi():
    r = retriever.retrieve_policy("guest Wi-Fi for visitor")
    assert r["policy_id"] == "KB-07"


def test_retriever_no_policy():
    r = retriever.retrieve_policy("xyzzy zork quux frobble")
    assert r["policy_id"] is None


def test_retriever_security():
    r = retriever.retrieve_policy("phishing email malware")
    assert r["policy_id"] == "KB-09"


def test_retriever_by_id():
    p = retriever.retrieve_policy_by_id("KB-01")
    assert p is not None
    assert p["title"] == "Password Reset"


def test_retriever_all_policies():
    policies = retriever.get_all_policies()
    assert len(policies) == 11
    ids = [p["policy_id"] for p in policies]
    assert "KB-01" in ids
    assert "ASSET-MGMT" in ids


# ===========================================================================
# REQ-01: Aditi Sharma — Laptop completely dead (3.5 years)
# ===========================================================================

def test_req_01_laptop_dead():
    result = orchestrator.process(
        "My laptop won't turn on at all, it's completely dead, had it about 3.5 years now.",
        employee_name="Aditi Sharma",
        employee_email="aditi.sharma@veridiancorp.example",
        request_id="REQ-01",
    )
    assert result["intent"]["intent"] == "laptop_replacement"
    assert result["decision"]["decision"] in ("ESCALATE",)
    assert result["decision"]["requires_human"] is True
    assert result["decision"]["policy_id"] == "KB-03"
    assert result["ticket"] is not None  # ticket must be created
    assert len(result["audit"]) > 0


# ===========================================================================
# REQ-02: Vikram Chawla — Guest Wi-Fi
# ===========================================================================

def test_req_02_guest_wifi():
    result = orchestrator.process(
        "Can I get Wi-Fi access for a guest visiting our office tomorrow?",
        employee_name="Vikram Chawla",
        employee_email="vikram.chawla@veridiancorp.example",
        request_id="REQ-02",
    )
    assert result["intent"]["intent"] == "guest_wifi"
    assert result["decision"]["decision"] == "RESOLVE"
    assert result["ticket"] is None  # No ticket needed for guest Wi-Fi
    assert result["decision"]["policy_id"] == "KB-07"


# ===========================================================================
# REQ-03: Karan Mehta — Locked out (6 attempts)
# ===========================================================================

def test_req_03_password_lockout():
    result = orchestrator.process(
        "I'm locked out of my account, tried my password 6 times.",
        employee_name="Karan Mehta",
        employee_email="karan.mehta@veridiancorp.example",
        request_id="REQ-03",
    )
    assert result["intent"]["intent"] == "password_reset"
    assert result["decision"]["decision"] == "ESCALATE"
    assert result["decision"]["requires_human"] is True
    assert result["ticket"] is not None


# ===========================================================================
# REQ-04: Ritu Bhatia — Non-catalog software
# ===========================================================================

def test_req_04_non_catalog_software():
    result = orchestrator.process(
        "Need approval to install a data-analysis tool that's not in the software catalog.",
        employee_name="Ritu Bhatia",
        employee_email="ritu.bhatia@veridiancorp.example",
        request_id="REQ-04",
    )
    assert result["intent"]["intent"] == "software_installation"
    assert result["decision"]["decision"] == "ESCALATE"
    assert result["decision"]["policy_id"] == "KB-04"
    assert result["ticket"] is not None


# ===========================================================================
# REQ-05: Sanjay Oberoi — VPN credentials expired
# ===========================================================================

def test_req_05_vpn_expired():
    result = orchestrator.process(
        "My VPN stopped working this morning, says credentials expired.",
        employee_name="Sanjay Oberoi",
        employee_email="sanjay.oberoi@veridiancorp.example",
        request_id="REQ-05",
    )
    assert result["intent"]["intent"] == "vpn_access"
    assert result["decision"]["decision"] == "RESOLVE"
    assert result["decision"]["policy_id"] == "KB-02"
    # No ticket for a self-service resolution
    assert result["ticket"] is None


# ===========================================================================
# REQ-06: Meera Iyer — Printer paper jam
# ===========================================================================

def test_req_06_printer_jam():
    result = orchestrator.process(
        "Printer on the 3rd floor keeps showing paper jam even though there's no jam.",
        employee_name="Meera Iyer",
        employee_email="meera.iyer@veridiancorp.example",
        request_id="REQ-06",
    )
    assert result["intent"]["intent"] == "printer"
    # Should ask for asset tag since none provided
    assert result["decision"]["decision"] == "FOLLOW_UP"
    assert result["decision"]["policy_id"] == "KB-05"
    assert result["ticket"] is None


# ===========================================================================
# REQ-07: Farhan Ali — WFH monitor (4 days/week)
# ===========================================================================

def test_req_07_wfh_equipment():
    result = orchestrator.process(
        "I've started working from home 4 days a week, how do I get a monitor?",
        employee_name="Farhan Ali",
        employee_email="farhan.ali@veridiancorp.example",
        request_id="REQ-07",
    )
    assert result["intent"]["intent"] == "wfh_equipment"
    assert result["decision"]["decision"] == "RESOLVE"
    assert result["decision"]["policy_id"] == "KB-10"
    assert result["ticket"] is not None  # Ticket needed for approval chain


# ===========================================================================
# REQ-08: Ananya Reddy — Phishing email (forwarding it — risky)
# ===========================================================================

def test_req_08_phishing_escalation():
    result = orchestrator.process(
        "I think I got a phishing email asking for my login — forwarding it to a few teammates to check.",
        employee_name="Ananya Reddy",
        employee_email="ananya.reddy@veridiancorp.example",
        request_id="REQ-08",
    )
    assert result["intent"]["intent"] == "security_incident"
    assert result["decision"]["decision"] == "ESCALATE"
    assert result["decision"]["risk_level"] == "Critical"
    assert result["decision"]["requires_human"] is True
    assert result["ticket"] is not None
    # Response must warn about not forwarding
    assert "forward" in result["response"].lower() or "not forward" in result["response"].lower()


# ===========================================================================
# REQ-09: Rohit Desai — Mailbox full
# ===========================================================================

def test_req_09_mailbox_full():
    result = orchestrator.process(
        "My mailbox is full and I can't send emails.",
        employee_name="Rohit Desai",
        employee_email="rohit.desai@veridiancorp.example",
        request_id="REQ-09",
    )
    assert result["intent"]["intent"] == "mailbox"
    assert result["decision"]["decision"] == "RESOLVE"
    assert result["decision"]["policy_id"] == "KB-06"


# ===========================================================================
# REQ-10: Kavya Pillai — Admin access (no policy)
# ===========================================================================

def test_req_10_admin_access():
    result = orchestrator.process(
        "Can someone give me admin access to the finance reporting server? Need it urgently for month-end.",
        employee_name="Kavya Pillai",
        employee_email="kavya.pillai@veridiancorp.example",
        request_id="REQ-10",
    )
    assert result["intent"]["intent"] == "admin_access"
    assert result["decision"]["decision"] == "ESCALATE"
    assert result["decision"]["requires_human"] is True
    assert result["ticket"] is not None
    # Must reference TK-1050
    assert "TK-1050" in result["response"]
    # Must NOT invent a policy
    assert result["decision"]["policy_id"] is None


# ===========================================================================
# REQ-11: Nikhil Bansal — Contractor VPN
# ===========================================================================

def test_req_11_contractor_vpn():
    result = orchestrator.process(
        "New contractor joining my team next week, they'll need VPN access.",
        employee_name="Nikhil Bansal",
        employee_email="nikhil.bansal@veridiancorp.example",
        request_id="REQ-11",
    )
    assert result["intent"]["intent"] == "vpn_access"
    # Contractor detected → ESCALATE for manager approval
    assert result["decision"]["decision"] in ("ESCALATE", "FOLLOW_UP")
    assert result["decision"]["policy_id"] == "KB-02"


# ===========================================================================
# REQ-12: Sneha Kulkarni — Expense tool login issue
# ===========================================================================

def test_req_12_expense_login():
    result = orchestrator.process(
        "I can't log into the expense tool, keeps saying invalid credentials.",
        employee_name="Sneha Kulkarni",
        employee_email="sneha.kulkarni@veridiancorp.example",
        request_id="REQ-12",
    )
    assert result["intent"]["intent"] == "expense_software"
    # Login issue → IT can help
    assert result["decision"]["decision"] in ("RESOLVE", "ROUTE")
    assert result["decision"]["policy_id"] == "KB-08"


# ===========================================================================
# REQ-13: Aman Gupta — Flickering screen (2 years old)
# ===========================================================================

def test_req_13_laptop_flickering():
    result = orchestrator.process(
        "Laptop screen is flickering on and off, had it 2 years, might just need a fix not a replacement.",
        employee_name="Aman Gupta",
        employee_email="aman.gupta@veridiancorp.example",
        request_id="REQ-13",
    )
    assert result["intent"]["intent"] == "laptop_replacement"
    # Needs diagnosis — must escalate, not blindly approve replacement
    assert result["decision"]["decision"] == "ESCALATE"
    assert result["decision"]["requires_human"] is True


# ===========================================================================
# REQ-14: Tanya Chopra — Browser extension (non-catalog)
# ===========================================================================

def test_req_14_browser_extension():
    result = orchestrator.process(
        "Requesting approval to install a browser extension for productivity tracking.",
        employee_name="Tanya Chopra",
        employee_email="tanya.chopra@veridiancorp.example",
        request_id="REQ-14",
    )
    assert result["intent"]["intent"] == "software_installation"
    assert result["decision"]["decision"] == "ESCALATE"
    assert result["decision"]["policy_id"] == "KB-04"


# ===========================================================================
# REQ-15: Rahul Menon — Unknown ("hey can you help, its not working")
# ===========================================================================

def test_req_15_unknown():
    result = orchestrator.process(
        "hey can you help, its not working",
        employee_name="Rahul Menon",
        employee_email="rahul.menon@veridiancorp.example",
        request_id="REQ-15",
    )
    # Must NOT guess — must ask a follow-up
    assert result["decision"]["decision"] == "FOLLOW_UP"
    assert result["ticket"] is None


# ===========================================================================
# Direct query tests
# ===========================================================================

def test_direct_vpn_expired():
    result = orchestrator.process("My VPN credentials expired")
    assert result["intent"]["intent"] == "vpn_access"
    assert result["decision"]["decision"] == "RESOLVE"


def test_direct_laptop_dead():
    result = orchestrator.process("My laptop is dead")
    assert result["intent"]["intent"] == "laptop_replacement"
    assert result["decision"]["requires_human"] is True


def test_direct_guest_wifi():
    result = orchestrator.process("How do I get guest Wi-Fi?")
    assert result["intent"]["intent"] == "guest_wifi"
    assert result["decision"]["decision"] == "RESOLVE"


def test_direct_phishing():
    result = orchestrator.process("I got a phishing email")
    assert result["intent"]["intent"] == "security_incident"
    assert result["decision"]["decision"] == "ESCALATE"
    assert result["decision"]["risk_level"] == "Critical"


def test_direct_mailbox_full():
    result = orchestrator.process("My mailbox is full")
    assert result["intent"]["intent"] == "mailbox"
    assert result["decision"]["policy_id"] == "KB-06"


def test_direct_wfh_monitor():
    result = orchestrator.process("I need a monitor for WFH")
    assert result["intent"]["intent"] == "wfh_equipment"


def test_direct_empty():
    result = orchestrator.process("")
    assert result["decision"]["decision"] == "FOLLOW_UP"
    assert result["ticket"] is None


# ===========================================================================
# No-hallucination tests
# ===========================================================================

def test_no_hallucinated_policy_for_admin():
    """Admin access must not invent a policy."""
    result = orchestrator.process("I need admin access")
    assert result["decision"]["policy_id"] is None


def test_audit_trail_always_populated():
    """Every request must produce an audit trail."""
    result = orchestrator.process("My printer is broken")
    assert isinstance(result["audit"], list)
    assert len(result["audit"]) >= 5


def test_ticket_created_for_escalation():
    """Security incidents must always create a ticket."""
    result = orchestrator.process("I received a suspicious phishing email")
    assert result["ticket"] is not None
    assert result["ticket"]["priority"] in ("Critical", "High")


def test_no_ticket_for_guest_wifi():
    """Guest Wi-Fi must be resolved without creating a ticket."""
    result = orchestrator.process("Need guest Wi-Fi for a visitor")
    assert result["ticket"] is None


def test_historical_tickets_not_overwritten():
    """Historical tickets from tickets.json must remain unmodified."""
    all_tickets = ticket_manager.get_all_tickets()
    historical = [t for t in all_tickets if t.get("source") == "historical"]
    ids = [t["ticket_id"] for t in historical]
    assert "TK-1050" in ids


def test_policy_source_displayed():
    """Every resolved policy must have a policy_id from the knowledge base."""
    result = orchestrator.process("My VPN credentials expired")
    pid = result["decision"].get("policy_id") or result["policy"].get("policy_id")
    assert pid is not None
    assert pid.startswith("KB-") or pid == "ASSET-MGMT"


def test_expense_access_routed_to_finance():
    """Expense access (new account) must be ROUTE to Finance, not resolved by IT."""
    result = orchestrator.process("I need access to the expense tool")
    assert result["intent"]["intent"] == "expense_software"
    assert result["decision"]["decision"] == "ROUTE"
    assert result["decision"]["route_to"] == "Finance Department"
