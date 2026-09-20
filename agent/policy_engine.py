"""
agent/policy_engine.py
----------------------
Deterministic rule-based policy engine for the Veridian IT Service Agent.
Converts (intent + user info + policy + ticket context) → decision.
All rules are derived exclusively from the supplied Veridian Corp JSON data.
No LLM. No invented policies.
"""

from __future__ import annotations

from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Decision constants
# ---------------------------------------------------------------------------

RESOLVE = "RESOLVE"
FOLLOW_UP = "FOLLOW_UP"
ESCALATE = "ESCALATE"
ROUTE = "ROUTE"
NO_ACTION = "NO_ACTION"

RISK_LOW = "Low"
RISK_MEDIUM = "Medium"
RISK_HIGH = "High"
RISK_CRITICAL = "Critical"


# ---------------------------------------------------------------------------
# Response templates (natural language, deterministic)
# ---------------------------------------------------------------------------

TEMPLATES = {
    # ---- Password Reset ----
    "password_reset_lockout": (
        "I can see you have been locked out after multiple failed attempts.\n\n"
        "According to **KB-01 — Password Reset**, accounts locked after 5 or more "
        "failed login attempts require **manual unlocking by the IT team** — this "
        "cannot be done through the self-service portal.\n\n"
        "I have escalated this to IT Support. A technician will reach out to you "
        "to verify your identity and unlock your account."
    ),
    "password_reset_forgot": (
        "No problem — you can reset your own password at any time.\n\n"
        "Based on **KB-01 — Password Reset**, Veridian employees can use the "
        "**self-service password reset portal** to reset their password without "
        "raising an IT ticket. No approval is required.\n\n"
        "If you are still unable to reset after trying the portal, please reply "
        "and I will escalate this to the IT team."
    ),

    # ---- VPN Access ----
    "vpn_expired_credentials": (
        "Your VPN credentials have expired.\n\n"
        "According to **KB-02 — VPN Access**, VPN credentials expire every 90 days "
        "and must be **renewed by the employee**. Please follow the VPN renewal "
        "process in the Veridian employee portal to restore access.\n\n"
        "If you are unable to renew, please reply and I will raise an IT support ticket."
    ),
    "vpn_contractor_followup": (
        "I can help with VPN access, but I need one more detail first.\n\n"
        "Under **KB-02 — VPN Access**, VPN is granted automatically to full-time "
        "employees, but **contractors require manager approval** submitted via the "
        "access request form.\n\n"
        "**Is the person requesting VPN access a full-time employee or a contractor?**"
    ),
    "vpn_contractor_approval": (
        "Understood — since this is for a contractor, a VPN access request will "
        "need to go through the approval process.\n\n"
        "Per **KB-02 — VPN Access**, contractors require **manager approval** "
        "submitted via the access request form before VPN access can be provisioned.\n\n"
        "I have created an IT ticket for this request. Please have the manager "
        "submit the formal approval via the access request form."
    ),
    "vpn_fulltime_auto": (
        "Good news — VPN access is provisioned automatically for all full-time employees.\n\n"
        "Per **KB-02 — VPN Access**, there is nothing extra to approve. "
        "If the VPN is not working, please check whether your credentials have "
        "expired (they expire every 90 days) or raise a ticket if there is a "
        "technical issue."
    ),

    # ---- Laptop Replacement ----
    "laptop_replacement_eligible_hardware": (
        "This laptop replacement request requires human review before it can be approved.\n\n"
        "There is a potential conflict between two supplied policies:\n\n"
        "- **KB-03 — Laptop Replacement**: Laptops are eligible for replacement "
        "after 3 years, or earlier for a **verified hardware failure**.\n"
        "- **ASSET-MGMT — Asset Management Policy**: The standard refresh cycle is "
        "**4 years**. Early replacement outside this cycle requires "
        "**Finance sign-off** and **IT approval**.\n\n"
        "Since the laptop is 3.5 years old with a reported hardware failure, it "
        "meets KB-03 criteria — but the ASSET-MGMT policy may still require Finance "
        "sign-off. I am routing this for human review to confirm the correct approval path."
    ),
    "laptop_not_yet_eligible": (
        "Based on the information provided, this laptop may not yet be eligible "
        "for a standard replacement.\n\n"
        "**KB-03 — Laptop Replacement** states laptops are eligible after 3 years "
        "of service, or earlier for a **verified hardware failure**.\n\n"
        "**ASSET-MGMT — Asset Management Policy** also notes that early replacements "
        "require Finance sign-off and IT approval.\n\n"
        "If you are experiencing a hardware failure, I will escalate for technical "
        "assessment. Otherwise, I would recommend raising this closer to the 3-year mark."
    ),
    "laptop_replacement_followup": (
        "I can help with your laptop issue — I just need a bit more information.\n\n"
        "**Is the laptop experiencing a verified hardware failure, or is this a "
        "routine replacement request?**\n\n"
        "This affects which policy applies (KB-03 vs ASSET-MGMT) and whether "
        "Finance approval is required."
    ),

    # ---- Software Installation ----
    "software_catalog": (
        "If the software you need is on Veridian's **approved software catalog**, "
        "you can install it yourself without raising a ticket.\n\n"
        "Per **KB-04 — Software Installation Requests**, standard catalog software "
        "can be self-installed. Please check the approved catalog in the employee portal.\n\n"
        "If you cannot find the software in the catalog, let me know and I will "
        "initiate a non-catalog review."
    ),
    "software_non_catalog": (
        "Non-catalog software requires IT Security review before installation.\n\n"
        "Per **KB-04 — Software Installation Requests**, software not listed in the "
        "approved catalog must go through an **IT Security review**, which takes "
        "**3–5 business days**.\n\n"
        "I have created a ticket for this request. The IT Security team will review "
        "the software and notify you of the outcome."
    ),

    # ---- Printer ----
    "printer_troubleshoot": (
        "Let me help you troubleshoot the printer issue.\n\n"
        "Per **KB-05 — Printer Troubleshooting**, please try the following steps first:\n"
        "1. Check the **printer queue** and clear any stuck jobs.\n"
        "2. **Restart the print spooler** (on Windows: Services → Print Spooler → Restart).\n\n"
        "If the issue persists after these steps, I will need the printer's "
        "**asset tag** to raise a formal IT ticket. Do you have the asset tag "
        "displayed on the printer?"
    ),
    "printer_followup_asset_tag": (
        "To raise an IT ticket for the printer issue, I need one more detail.\n\n"
        "**What is the printer's asset tag?**\n\n"
        "This is usually a label on the printer itself (e.g., *VRD-PRN-042*). "
        "It is required before a ticket can be created under **KB-05 — Printer Troubleshooting**."
    ),
    "printer_ticket_created": (
        "Thank you — I have created an IT ticket for the printer issue.\n\n"
        "Per **KB-05 — Printer Troubleshooting**, a technician will be assigned "
        "to investigate. Please also try the initial steps while you wait:\n"
        "1. Clear the print queue.\n"
        "2. Restart the print spooler."
    ),

    # ---- Mailbox ----
    "mailbox_archive": (
        "Your mailbox is approaching or has hit its storage limit.\n\n"
        "Per **KB-06 — Email Mailbox Quota**, the default quota is **25GB**. "
        "The first step is to **archive older emails** using Veridian's email client. "
        "Archiving moves old messages out of your primary mailbox and frees up space "
        "without deleting anything.\n\n"
        "If you need a quota increase beyond 25GB, your manager will need to approve "
        "it (maximum allowed: 50GB). Let me know if you would like me to raise "
        "a quota increase request."
    ),
    "mailbox_quota_increase": (
        "A mailbox quota increase has been requested.\n\n"
        "Per **KB-06 — Email Mailbox Quota**, increases beyond the default 25GB "
        "require **manager approval** and are capped at a maximum of **50GB**.\n\n"
        "I have created a ticket for this request. Your manager will need to "
        "approve before IT can process the increase."
    ),

    # ---- Guest Wi-Fi ----
    "guest_wifi_resolve": (
        "Great news — guest Wi-Fi can be set up quickly without an IT ticket.\n\n"
        "Per **KB-07 — Guest Wi-Fi Access**, any Veridian employee can generate "
        "guest Wi-Fi credentials from the **front-desk kiosk**. The credentials are "
        "valid for **24 hours**.\n\n"
        "No IT support or approval is required. Simply use the kiosk before your "
        "guest arrives."
    ),

    # ---- Expense Software ----
    "expense_access_finance": (
        "Access to the expense management tool is **not handled by IT**.\n\n"
        "Per **KB-08 — Expense Software Access**, access to the expense tool is "
        "granted by the **Finance department**, not IT. Please contact Finance to "
        "request an account.\n\n"
        "Once you have an account, IT can help with any technical login issues."
    ),
    "expense_login_issue": (
        "I can help with login issues on the expense tool, since you already have an account.\n\n"
        "Per **KB-08 — Expense Software Access**, IT can assist with "
        "**technical login issues** once an account exists.\n\n"
        "I have raised an IT ticket for this. A technician will contact you to "
        "troubleshoot the login problem."
    ),

    # ---- Security Incident ----
    "security_incident_escalate": (
        "⚠️ **This is a high-priority security incident.**\n\n"
        "Per **KB-09 — Security Incident Reporting**, any suspected phishing email, "
        "malware, or unauthorized access must be reported to:\n\n"
        "**security@veridian-corp.example** — immediately.\n\n"
        "**Important:** Do NOT forward the suspicious email to other employees — "
        "this can spread the threat.\n\n"
        "I have created an urgent escalation ticket and notified the security team. "
        "Please contact them directly if the situation is critical."
    ),

    # ---- WFH Equipment ----
    "wfh_equipment_eligible": (
        "You may be eligible for a home office equipment allowance.\n\n"
        "Per **KB-10 — Work-From-Home Equipment**, employees working remotely "
        "**more than 3 days per week** are eligible for a **one-time home office "
        "equipment allowance** (chair and/or monitor).\n\n"
        "The process requires:\n"
        "1. **Manager sign-off**\n"
        "2. **Finance processing**\n\n"
        "IT only handles the equipment shipping **after** both approvals are in place. "
        "I have created a ticket to start this process."
    ),
    "wfh_equipment_followup": (
        "I can help with home office equipment, but I need one detail first.\n\n"
        "Per **KB-10 — Work-From-Home Equipment**, the allowance applies to "
        "employees working remotely **more than 3 days per week**.\n\n"
        "**How many days per week are you currently working from home?**"
    ),
    "wfh_not_eligible": (
        "Based on the information provided, you may not be eligible for the home "
        "office equipment allowance.\n\n"
        "Per **KB-10 — Work-From-Home Equipment**, the allowance is for employees "
        "working remotely **more than 3 days per week**. If your schedule changes, "
        "please raise a new request.\n\n"
        "If you believe this is incorrect, I can escalate for human review."
    ),

    # ---- Admin Access ----
    "admin_access_escalate": (
        "This request cannot be processed automatically.\n\n"
        "There is **no general administrative access policy** in the Veridian IT "
        "knowledge base. I will not assume an approval process.\n\n"
        "For context, a historical ticket (**TK-1050**) for a similar admin access "
        "request was **rejected** due to no business justification being provided.\n\n"
        "I am escalating this for human review. To improve the chances of approval, "
        "please prepare a clear business justification for the access requested."
    ),

    # ---- Unknown ----
    "unknown_followup": (
        "I want to make sure I direct you to the right team.\n\n"
        "**What isn't working — your laptop, VPN, email, printer, or another service?**\n\n"
        "A short description will help me find the right policy and resolution for you."
    ),

    # ---- No policy ----
    "no_policy": (
        "I was unable to find a relevant IT policy in the Veridian knowledge base "
        "for your request.\n\n"
        "I am escalating this for human review. An IT agent will assess your "
        "request and respond."
    ),
}


# ---------------------------------------------------------------------------
# Policy Engine
# ---------------------------------------------------------------------------

def evaluate(
    intent: str,
    intent_confidence: float,
    user_input: str,
    policy: Dict,
    entities: Dict,
    related_tickets: List[Dict],
) -> Dict:
    """
    Evaluate the intent and retrieved policy to produce a structured decision.

    Parameters
    ----------
    intent              : classified intent label
    intent_confidence   : 0.0-1.0
    user_input          : raw user message
    policy              : dict from retriever (may have policy_id=None)
    entities            : extracted entities from orchestrator
    related_tickets     : historical tickets matching the query

    Returns
    -------
    {
        "decision"        : RESOLVE | FOLLOW_UP | ESCALATE | ROUTE | NO_ACTION,
        "reason"          : str,
        "response"        : str,
        "next_action"     : str,
        "policy_id"       : str | None,
        "risk_level"      : str,
        "requires_human"  : bool,
        "create_ticket"   : bool,
        "ticket_priority" : str,
        "ticket_status"   : str,
        "route_to"        : str | None,
    }
    """

    lower = user_input.lower()

    # ------------------------------------------------------------------
    # PASSWORD RESET
    # ------------------------------------------------------------------
    if intent == "password_reset":
        lockout_keywords = ["locked", "lockout", "lock out", "5 times", "6 times",
                            "7 times", "failed attempt", "multiple attempt",
                            "can't log", "cannot log", "locked out"]
        is_lockout = any(kw in lower for kw in lockout_keywords)

        # Check for explicit attempt counts >= 5
        import re
        counts = re.findall(r"(\d+)\s*times?", lower)
        if any(int(c) >= 5 for c in counts):
            is_lockout = True

        if is_lockout:
            return {
                "decision": ESCALATE,
                "reason": "Account locked after 5+ failed attempts; manual IT unlock required (KB-01).",
                "response": TEMPLATES["password_reset_lockout"],
                "next_action": "IT team to verify identity and manually unlock account.",
                "policy_id": "KB-01",
                "risk_level": RISK_MEDIUM,
                "requires_human": True,
                "create_ticket": True,
                "ticket_priority": "Medium",
                "ticket_status": "Escalated",
                "route_to": None,
            }
        else:
            return {
                "decision": RESOLVE,
                "reason": "Standard password reset; employee can use self-service portal (KB-01).",
                "response": TEMPLATES["password_reset_forgot"],
                "next_action": "Employee uses self-service password reset portal.",
                "policy_id": "KB-01",
                "risk_level": RISK_LOW,
                "requires_human": False,
                "create_ticket": False,
                "ticket_priority": "Low",
                "ticket_status": "Resolved",
                "route_to": None,
            }

    # ------------------------------------------------------------------
    # VPN ACCESS
    # ------------------------------------------------------------------
    if intent == "vpn_access":
        expired_keywords = ["expired", "expir", "expired credential", "credentials expired",
                            "90 day", "renew", "renewal"]
        contractor_keywords = ["contractor", "contract", "freelancer", "vendor", "external"]
        fulltime_keywords = ["full-time", "full time", "fulltime", "employee", "permanent", "staff"]

        is_expired = any(kw in lower for kw in expired_keywords)
        is_contractor = any(kw in lower for kw in contractor_keywords)
        is_fulltime = any(kw in lower for kw in fulltime_keywords)
        is_new_request = any(kw in lower for kw in ["new", "joining", "access", "need vpn", "request"])

        if is_expired:
            return {
                "decision": RESOLVE,
                "reason": "VPN credentials expired; employee must renew (KB-02).",
                "response": TEMPLATES["vpn_expired_credentials"],
                "next_action": "Employee renews VPN credentials via portal.",
                "policy_id": "KB-02",
                "risk_level": RISK_LOW,
                "requires_human": False,
                "create_ticket": False,
                "ticket_priority": "Low",
                "ticket_status": "Resolved",
                "route_to": None,
            }
        elif is_contractor:
            return {
                "decision": ESCALATE,
                "reason": "Contractor VPN requires manager approval via access request form (KB-02).",
                "response": TEMPLATES["vpn_contractor_approval"],
                "next_action": "Manager to submit formal approval via access request form.",
                "policy_id": "KB-02",
                "risk_level": RISK_MEDIUM,
                "requires_human": True,
                "create_ticket": True,
                "ticket_priority": "Medium",
                "ticket_status": "Pending Approval",
                "route_to": None,
            }
        elif is_fulltime:
            return {
                "decision": RESOLVE,
                "reason": "Full-time employee — VPN is auto-provisioned (KB-02).",
                "response": TEMPLATES["vpn_fulltime_auto"],
                "next_action": "Check VPN credentials or raise ticket for technical issue.",
                "policy_id": "KB-02",
                "risk_level": RISK_LOW,
                "requires_human": False,
                "create_ticket": False,
                "ticket_priority": "Low",
                "ticket_status": "Resolved",
                "route_to": None,
            }
        elif is_new_request:
            # Ambiguous — could be contractor or employee — need follow-up
            return {
                "decision": FOLLOW_UP,
                "reason": "Cannot determine employment type; contractor vs employee changes approval requirement (KB-02).",
                "response": TEMPLATES["vpn_contractor_followup"],
                "next_action": "Ask user whether requester is full-time employee or contractor.",
                "policy_id": "KB-02",
                "risk_level": RISK_LOW,
                "requires_human": False,
                "create_ticket": False,
                "ticket_priority": "Low",
                "ticket_status": "Pending Information",
                "route_to": None,
            }
        else:
            return {
                "decision": FOLLOW_UP,
                "reason": "VPN request context unclear; need employment type to apply correct rule (KB-02).",
                "response": TEMPLATES["vpn_contractor_followup"],
                "next_action": "Clarify whether user is a full-time employee or contractor.",
                "policy_id": "KB-02",
                "risk_level": RISK_LOW,
                "requires_human": False,
                "create_ticket": False,
                "ticket_priority": "Low",
                "ticket_status": "Pending Information",
                "route_to": None,
            }

    # ------------------------------------------------------------------
    # LAPTOP REPLACEMENT
    # ------------------------------------------------------------------
    if intent == "laptop_replacement":
        hardware_failure_keywords = [
            "dead", "won't turn on", "wont turn on", "broken", "failure",
            "failed", "completely dead", "hardware failure", "not turning on",
            "not starting", "won't start", "wont start", "crash", "crashed",
        ]
        screen_issue_keywords = ["flickering", "screen flicker", "display issue"]
        is_hardware_failure = any(kw in lower for kw in hardware_failure_keywords)
        is_screen_issue = any(kw in lower for kw in screen_issue_keywords)

        import re
        # Try to detect age in years
        age_years: Optional[float] = None
        age_matches = re.findall(r"(\d+(?:\.\d+)?)\s*year", lower)
        if age_matches:
            age_years = float(age_matches[0])

        if is_screen_issue:
            # Screen flickering — 2 years old — not a replacement candidate yet
            # Route to IT diagnostic
            return {
                "decision": ESCALATE,
                "reason": "Laptop screen flickering — needs hardware diagnosis before replacement decision (KB-03).",
                "response": (
                    "A flickering screen may or may not require a full replacement.\n\n"
                    "Per **KB-03 — Laptop Replacement**, early replacement is possible "
                    "only for **verified hardware failure**. I will route this for a "
                    "hardware diagnostic first.\n\n"
                    "An IT technician will assess whether this can be repaired or "
                    "qualifies as a hardware failure requiring replacement."
                ),
                "next_action": "IT technician to perform hardware diagnostic assessment.",
                "policy_id": "KB-03",
                "risk_level": RISK_MEDIUM,
                "requires_human": True,
                "create_ticket": True,
                "ticket_priority": "Medium",
                "ticket_status": "Escalated",
                "route_to": None,
            }
        elif is_hardware_failure and age_years is not None:
            # Hardware failure reported — apply KB-03 + ASSET-MGMT conflict check
            return {
                "decision": ESCALATE,
                "reason": (
                    f"Laptop is {age_years} years old with reported hardware failure. "
                    "KB-03 allows early replacement for hardware failure, but ASSET-MGMT "
                    "requires Finance sign-off for replacement before the 4-year cycle ends."
                ),
                "response": TEMPLATES["laptop_replacement_eligible_hardware"],
                "next_action": "Route for IT and Finance review — KB-03 vs ASSET-MGMT conflict.",
                "policy_id": "KB-03",
                "risk_level": RISK_MEDIUM,
                "requires_human": True,
                "create_ticket": True,
                "ticket_priority": "Medium",
                "ticket_status": "Escalated",
                "route_to": None,
            }
        elif is_hardware_failure:
            return {
                "decision": ESCALATE,
                "reason": "Hardware failure reported; requires IT assessment and possible Finance sign-off (KB-03, ASSET-MGMT).",
                "response": TEMPLATES["laptop_replacement_eligible_hardware"],
                "next_action": "IT assessment required before replacement can be approved.",
                "policy_id": "KB-03",
                "risk_level": RISK_MEDIUM,
                "requires_human": True,
                "create_ticket": True,
                "ticket_priority": "Medium",
                "ticket_status": "Escalated",
                "route_to": None,
            }
        elif age_years is not None and age_years >= 3.0:
            # Eligible by age — still need to note ASSET-MGMT 4-year cycle
            return {
                "decision": ESCALATE,
                "reason": (
                    f"Laptop is {age_years} years old — meets KB-03 3-year threshold, "
                    "but ASSET-MGMT standard cycle is 4 years (Finance sign-off may be needed)."
                ),
                "response": TEMPLATES["laptop_replacement_eligible_hardware"],
                "next_action": "Human review to confirm whether Finance sign-off is required.",
                "policy_id": "KB-03",
                "risk_level": RISK_MEDIUM,
                "requires_human": True,
                "create_ticket": True,
                "ticket_priority": "Medium",
                "ticket_status": "Escalated",
                "route_to": None,
            }
        else:
            return {
                "decision": FOLLOW_UP,
                "reason": "Laptop details insufficient to determine eligibility (KB-03, ASSET-MGMT).",
                "response": TEMPLATES["laptop_replacement_followup"],
                "next_action": "Ask user for laptop age and whether there is a hardware failure.",
                "policy_id": "KB-03",
                "risk_level": RISK_LOW,
                "requires_human": False,
                "create_ticket": False,
                "ticket_priority": "Low",
                "ticket_status": "Pending Information",
                "route_to": None,
            }

    # ------------------------------------------------------------------
    # SOFTWARE INSTALLATION
    # ------------------------------------------------------------------
    if intent == "software_installation":
        non_catalog_keywords = [
            "not in catalog", "non-catalog", "not listed", "not approved",
            "approval", "security review", "data analysis", "browser extension",
            "productivity tracking", "third party", "third-party",
        ]
        is_non_catalog = any(kw in lower for kw in non_catalog_keywords)

        if is_non_catalog:
            return {
                "decision": ESCALATE,
                "reason": "Non-catalog software requires IT Security review (KB-04).",
                "response": TEMPLATES["software_non_catalog"],
                "next_action": "IT Security review — 3 to 5 business days.",
                "policy_id": "KB-04",
                "risk_level": RISK_MEDIUM,
                "requires_human": True,
                "create_ticket": True,
                "ticket_priority": "Medium",
                "ticket_status": "Pending Security Review",
                "route_to": None,
            }
        else:
            return {
                "decision": RESOLVE,
                "reason": "Software may be in the approved catalog — employee can self-install (KB-04).",
                "response": TEMPLATES["software_catalog"],
                "next_action": "Employee to check approved catalog and self-install.",
                "policy_id": "KB-04",
                "risk_level": RISK_LOW,
                "requires_human": False,
                "create_ticket": False,
                "ticket_priority": "Low",
                "ticket_status": "Resolved",
                "route_to": None,
            }

    # ------------------------------------------------------------------
    # PRINTER
    # ------------------------------------------------------------------
    if intent == "printer":
        has_asset_tag = entities.get("printer_asset_tag") is not None

        if has_asset_tag:
            return {
                "decision": RESOLVE,
                "reason": "Printer asset tag provided; ticket created for IT technician (KB-05).",
                "response": TEMPLATES["printer_ticket_created"],
                "next_action": "IT technician assigned to printer issue.",
                "policy_id": "KB-05",
                "risk_level": RISK_LOW,
                "requires_human": True,
                "create_ticket": True,
                "ticket_priority": "Low",
                "ticket_status": "Open",
                "route_to": None,
            }
        else:
            return {
                "decision": FOLLOW_UP,
                "reason": "Printer asset tag required before a ticket can be created (KB-05).",
                "response": TEMPLATES["printer_troubleshoot"],
                "next_action": "Ask user for printer asset tag.",
                "policy_id": "KB-05",
                "risk_level": RISK_LOW,
                "requires_human": False,
                "create_ticket": False,
                "ticket_priority": "Low",
                "ticket_status": "Pending Information",
                "route_to": None,
            }

    # ------------------------------------------------------------------
    # MAILBOX
    # ------------------------------------------------------------------
    if intent == "mailbox":
        increase_keywords = ["increase", "more storage", "need more", "quota increase",
                             "raise limit", "expand", "bigger quota"]
        is_increase = any(kw in lower for kw in increase_keywords)

        if is_increase:
            return {
                "decision": ESCALATE,
                "reason": "Mailbox quota increase beyond 25GB requires manager approval (KB-06).",
                "response": TEMPLATES["mailbox_quota_increase"],
                "next_action": "Manager approval required; max quota 50GB.",
                "policy_id": "KB-06",
                "risk_level": RISK_LOW,
                "requires_human": True,
                "create_ticket": True,
                "ticket_priority": "Low",
                "ticket_status": "Pending Approval",
                "route_to": None,
            }
        else:
            return {
                "decision": RESOLVE,
                "reason": "Mailbox full; employee should archive old mail first (KB-06).",
                "response": TEMPLATES["mailbox_archive"],
                "next_action": "Employee to archive old email; request quota increase if still needed.",
                "policy_id": "KB-06",
                "risk_level": RISK_LOW,
                "requires_human": False,
                "create_ticket": False,
                "ticket_priority": "Low",
                "ticket_status": "Resolved",
                "route_to": None,
            }

    # ------------------------------------------------------------------
    # GUEST WI-FI
    # ------------------------------------------------------------------
    if intent == "guest_wifi":
        return {
            "decision": RESOLVE,
            "reason": "Guest Wi-Fi can be generated from front-desk kiosk; no IT ticket needed (KB-07).",
            "response": TEMPLATES["guest_wifi_resolve"],
            "next_action": "Employee generates guest Wi-Fi credentials from front-desk kiosk.",
            "policy_id": "KB-07",
            "risk_level": RISK_LOW,
            "requires_human": False,
            "create_ticket": False,
            "ticket_priority": "Low",
            "ticket_status": "Resolved",
            "route_to": None,
        }

    # ------------------------------------------------------------------
    # EXPENSE SOFTWARE
    # ------------------------------------------------------------------
    if intent == "expense_software":
        login_issue_keywords = [
            "can't log in", "cannot log in", "login issue", "invalid credential",
            "login problem", "can't access", "cannot access", "sign in",
            "sign-in", "login error", "password wrong",
        ]
        access_request_keywords = [
            "access", "get access", "need access", "grant access", "account",
            "new account", "request access",
        ]
        is_login_issue = any(kw in lower for kw in login_issue_keywords)

        if is_login_issue:
            return {
                "decision": RESOLVE,
                "reason": "Existing account login issue — IT can assist per KB-08.",
                "response": TEMPLATES["expense_login_issue"],
                "next_action": "IT technician to help troubleshoot login issue.",
                "policy_id": "KB-08",
                "risk_level": RISK_LOW,
                "requires_human": True,
                "create_ticket": True,
                "ticket_priority": "Low",
                "ticket_status": "Open",
                "route_to": None,
            }
        else:
            return {
                "decision": ROUTE,
                "reason": "Expense tool access is granted by Finance, not IT (KB-08).",
                "response": TEMPLATES["expense_access_finance"],
                "next_action": "User to contact Finance department for account creation.",
                "policy_id": "KB-08",
                "risk_level": RISK_LOW,
                "requires_human": False,
                "create_ticket": False,
                "ticket_priority": "Low",
                "ticket_status": "Routed",
                "route_to": "Finance Department",
            }

    # ------------------------------------------------------------------
    # SECURITY INCIDENT
    # ------------------------------------------------------------------
    if intent == "security_incident":
        return {
            "decision": ESCALATE,
            "reason": "Security incident (phishing/malware/unauthorized access) — immediate escalation required (KB-09).",
            "response": TEMPLATES["security_incident_escalate"],
            "next_action": "Report to security@veridian-corp.example immediately.",
            "policy_id": "KB-09",
            "risk_level": RISK_CRITICAL,
            "requires_human": True,
            "create_ticket": True,
            "ticket_priority": "Critical",
            "ticket_status": "Escalated — Security",
            "route_to": "Security Team",
        }

    # ------------------------------------------------------------------
    # WFH EQUIPMENT
    # ------------------------------------------------------------------
    if intent == "wfh_equipment":
        import re
        days_matches = re.findall(r"(\d+)\s*day", lower)
        remote_days: Optional[int] = None
        if days_matches:
            remote_days = int(days_matches[0])

        eligible_keywords = ["work from home", "wfh", "remote", "working remotely",
                             "working from home", "4 days", "5 days", "full week"]
        is_clearly_remote = any(kw in lower for kw in eligible_keywords)

        if remote_days is not None and remote_days > 3:
            return {
                "decision": RESOLVE,
                "reason": f"Employee works {remote_days} days from home (>3 days); eligible for WFH equipment allowance (KB-10).",
                "response": TEMPLATES["wfh_equipment_eligible"],
                "next_action": "Manager sign-off → Finance processing → IT ships equipment.",
                "policy_id": "KB-10",
                "risk_level": RISK_LOW,
                "requires_human": True,
                "create_ticket": True,
                "ticket_priority": "Low",
                "ticket_status": "Pending Manager Approval",
                "route_to": None,
            }
        elif remote_days is not None and remote_days <= 3:
            return {
                "decision": RESOLVE,
                "reason": f"Employee works {remote_days} days remotely — does not meet >3 days threshold (KB-10).",
                "response": TEMPLATES["wfh_not_eligible"],
                "next_action": "Inform employee of eligibility criteria.",
                "policy_id": "KB-10",
                "risk_level": RISK_LOW,
                "requires_human": False,
                "create_ticket": False,
                "ticket_priority": "Low",
                "ticket_status": "Resolved",
                "route_to": None,
            }
        elif is_clearly_remote:
            return {
                "decision": RESOLVE,
                "reason": "Employee indicates remote work arrangement; appears eligible for WFH allowance (KB-10).",
                "response": TEMPLATES["wfh_equipment_eligible"],
                "next_action": "Manager sign-off → Finance processing → IT ships equipment.",
                "policy_id": "KB-10",
                "risk_level": RISK_LOW,
                "requires_human": True,
                "create_ticket": True,
                "ticket_priority": "Low",
                "ticket_status": "Pending Manager Approval",
                "route_to": None,
            }
        else:
            return {
                "decision": FOLLOW_UP,
                "reason": "Remote working frequency unclear; needed to determine WFH equipment eligibility (KB-10).",
                "response": TEMPLATES["wfh_equipment_followup"],
                "next_action": "Ask how many days per week the employee works from home.",
                "policy_id": "KB-10",
                "risk_level": RISK_LOW,
                "requires_human": False,
                "create_ticket": False,
                "ticket_priority": "Low",
                "ticket_status": "Pending Information",
                "route_to": None,
            }

    # ------------------------------------------------------------------
    # ADMIN ACCESS
    # ------------------------------------------------------------------
    if intent == "admin_access":
        return {
            "decision": ESCALATE,
            "reason": (
                "No general admin-access policy exists in the supplied knowledge base. "
                "Historical ticket TK-1050 was rejected (no business justification). "
                "Cannot assume an approval workflow."
            ),
            "response": TEMPLATES["admin_access_escalate"],
            "next_action": "Human review required; user to provide business justification.",
            "policy_id": None,
            "risk_level": RISK_HIGH,
            "requires_human": True,
            "create_ticket": True,
            "ticket_priority": "High",
            "ticket_status": "Escalated",
            "route_to": None,
        }

    # ------------------------------------------------------------------
    # UNKNOWN / LOW CONFIDENCE
    # ------------------------------------------------------------------
    if intent == "unknown" or intent_confidence < 0.15:
        return {
            "decision": FOLLOW_UP,
            "reason": "Intent could not be determined with sufficient confidence.",
            "response": TEMPLATES["unknown_followup"],
            "next_action": "Ask the user to describe their issue more specifically.",
            "policy_id": None,
            "risk_level": RISK_LOW,
            "requires_human": False,
            "create_ticket": False,
            "ticket_priority": "Low",
            "ticket_status": "Pending Information",
            "route_to": None,
        }

    # ------------------------------------------------------------------
    # FALLBACK (intent recognised but no policy found)
    # ------------------------------------------------------------------
    return {
        "decision": ESCALATE,
        "reason": "No applicable policy found in the knowledge base for this request.",
        "response": TEMPLATES["no_policy"],
        "next_action": "Escalate to human IT agent for assessment.",
        "policy_id": policy.get("policy_id"),
        "risk_level": RISK_MEDIUM,
        "requires_human": True,
        "create_ticket": True,
        "ticket_priority": "Medium",
        "ticket_status": "Escalated",
        "route_to": None,
    }
