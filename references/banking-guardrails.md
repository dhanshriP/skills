# Banking Guardrails

These are non-negotiable constraints for this agent in a regulated banking environment.
Every phase of the triage workflow must comply with these.

---

## Data handling rules

### Never send to external APIs (including AI)
- Customer names, account numbers, card numbers (PAN)
- Session tokens, auth tokens, API keys
- Device fingerprints, IMEI, serial numbers
- IP addresses from production
- User IDs, customer IDs
- Transaction IDs or amounts linked to real customers

### PII detection patterns (regex, apply before any external call)

```python
PII_PATTERNS = [
    # Card numbers (Visa, Mastercard, Amex, etc.)
    r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b',
    # UK account numbers
    r'\b[0-9]{8}\b',
    # Sort codes
    r'\b[0-9]{2}-[0-9]{2}-[0-9]{2}\b',
    # IBAN
    r'\b[A-Z]{2}[0-9]{2}[A-Z0-9]{4}[0-9]{7}(?:[A-Z0-9]?){0,16}\b',
    # JWT tokens
    r'eyJ[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.?[A-Za-z0-9\-_.+/=]*',
    # Bearer tokens
    r'Bearer\s+[A-Za-z0-9\-_=.]+',
    # IPv4 addresses
    r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b',
    # UUIDs (session/customer IDs)
    r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b',
]
```

Replace all matches with `[REDACTED:{type}]` e.g. `[REDACTED:PAN]`, `[REDACTED:JWT]`.

---

## Audit log format

Every agent action must be logged. Log entry structure:

```json
{
  "timestamp": "ISO8601",
  "action": "SANITIZE | DEOBFUSCATE | ATTRIBUTE | DEDUPLICATE | ANALYSE | CONFIRM | CREATE",
  "actor": "automated-crash-triage-agent",
  "crash_id": "{appdynamics_crash_id}",
  "app_version": "{app_version}",
  "build_number": "{build_number}",
  "redactions_applied": ["PAN:1", "JWT:2"],
  "outcome": "SUCCESS | HALTED | SKIPPED",
  "reason": "{free text if halted}",
  "jira_ticket": "{KEY if created}",
  "human_confirmed_by": "{username if confirmation step}",
  "duration_ms": 0
}
```

Logs must go to your internal SIEM / audit log system, not to a third-party log aggregator.

---

## Network and API constraints

- All API calls (Git, Jira, AppDynamics, AI) must route through your corporate egress proxy
- AI API call (Claude) must go through your VPC endpoint — not direct internet
- Mapping files and source code must never leave your network boundary
- Git API calls must use a service account token with read-only scope
- Jira API calls must use a service account token with create/edit scope on your project only

---

## Agent permission model

| Action | Permission | Requires human approval |
|---|---|---|
| Read AppDynamics crash data | ✅ Auto | No |
| Read Git blame / PR info | ✅ Auto | No |
| Read mapping files from artifact store | ✅ Auto | No |
| Fetch source code snippets | ✅ Auto | No |
| Query Jira for duplicates | ✅ Auto | No |
| Call AI API for analysis | ✅ Auto (sanitized only) | No |
| Create Jira ticket | ⛔ Blocked | **Yes — Phase 7 confirmation** |
| Post Slack notification | ⛔ Blocked | **Yes — after ticket confirmed** |
| Update existing Jira ticket | ⛔ Blocked | **Yes — for anything beyond count increment** |
| Assign or reassign tickets | ⛔ Blocked | **Yes** |
| Any production system write | ⛔ Never | Not applicable |

---

## What the agent must never do

- Commit or push code
- Trigger deployments or rollbacks
- Access production databases
- Modify CI/CD pipelines
- Access customer accounts or transaction history
- Store crash data outside your approved data stores
- Create tickets for security vulnerabilities in a public Jira project (use private security project)

---

## Security vulnerability handling

If the crash analysis reveals a potential security vulnerability (e.g., crash in auth, 
cryptography, or payment validation code), do NOT create a standard Jira ticket.

Instead:
1. Halt normal triage flow
2. Notify via a private, encrypted channel (not Slack)
3. Create ticket in the designated **security/private Jira project** only
4. Restrict visibility to security team + assigned engineer
5. Label as: `security-sensitive` — do not add to normal sprint board

---

## Change management

In banking, any automated agent action that results in a Jira ticket in a regulated 
project may need to be traceable to a change request. Ensure:

- All agent-created tickets are tagged `triage_source: automated`
- The audit log entry is retained for minimum 7 years (align with your retention policy)
- Human confirmer's identity is recorded in the audit log
- Tickets created for payment-critical components are flagged for change board review
