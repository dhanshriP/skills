# Jira Ticket Schema

## Full field mapping for crash triage tickets

```json
{
  "fields": {
    "project": {
      "key": "{YOUR_PROJECT_KEY}"
    },
    "summary": "[CRASH] {error_type} in {ClassName}.{methodName}() — v{app_version}",
    "issuetype": {
      "name": "Bug"
    },
    "priority": {
      "name": "{CRITICAL|High|Medium|Low}"
    },
    "assignee": {
      "name": "{primary_owner_username}"
    },
    "description": {
      "type": "doc",
      "version": 1,
      "content": [
        {
          "type": "heading",
          "content": [{ "type": "text", "text": "Crash Summary" }]
        },
        {
          "type": "paragraph",
          "content": [{ "type": "text", "text": "{error_type}: {error_message}" }]
        },
        {
          "type": "heading",
          "content": [{ "type": "text", "text": "Attribution" }]
        },
        {
          "type": "paragraph",
          "content": [{ "type": "text", "text": "Committed by: {primary_owner} on {commit_date}\nPR: #{pr_number} — reviewed by {secondary_owner}" }]
        },
        {
          "type": "heading",
          "content": [{ "type": "text", "text": "AI Analysis" }]
        },
        {
          "type": "paragraph",
          "content": [{ "type": "text", "text": "Root cause: {ROOT_CAUSE}\n\nHypothesis: {HYPOTHESIS}\n\nSuggested fix: {LIKELY_FIX}\n\nBlast radius: {BLAST_RADIUS}\n\nAI Confidence: {CONFIDENCE}" }]
        },
        {
          "type": "heading",
          "content": [{ "type": "text", "text": "Impact" }]
        },
        {
          "type": "paragraph",
          "content": [{ "type": "text", "text": "Occurrences: {occurrence_count}\nAffected users: {affected_users}\nFirst seen: {first_seen}\nLast seen: {last_seen}\nApp version: {app_version}" }]
        },
        {
          "type": "heading",
          "content": [{ "type": "text", "text": "Stack Trace" }]
        },
        {
          "type": "codeBlock",
          "content": [{ "type": "text", "text": "{deobfuscated_sanitized_trace}" }]
        }
      ]
    },
    "components": [
      { "name": "{derived_component}" }
    ],
    "labels": [
      "crash",
      "automated-triage",
      "{platform}",
      "v{app_version}"
    ],
    "customfield_10001": "{sprint_id}",
    "customfield_crash_hash": "{dedup_hash}",
    "customfield_ai_confidence": "{HIGH|MEDIUM|LOW}",
    "customfield_triage_source": "automated-crash-triage-agent",
    "customfield_appdynamics_url": "{appdynamics_crash_group_url}",
    "customfield_commit_sha": "{commit_sha}",
    "customfield_pr_url": "{pr_url}"
  }
}
```

---

## Severity mapping

Use AI's `SEVERITY_SUGGESTION` as the *starting point*, but apply these banking-specific overrides:

| Condition | Force severity |
|---|---|
| Crash in payment / transfer flow | CRITICAL |
| Crash on login / auth screen | CRITICAL |
| Crash affects >5% of active users | CRITICAL |
| Crash in balance/account display | High |
| Crash in notification only | Medium |
| Crash rate <0.1% and cosmetic | Low |

Human confirmer can override any suggestion in Phase 7.

---

## Component derivation

Map file path prefixes to components automatically:

```
com.yourbank.payments.*     → Payments
com.yourbank.auth.*         → Authentication
com.yourbank.accounts.*     → Accounts
com.yourbank.transfers.*    → Transfers
com.yourbank.notifications.*→ Notifications
com.yourbank.ui.*           → UI / Design System
com.yourbank.network.*      → API / Networking
```

If no match: assign component `Unknown — needs manual classification`.

---

## Watchers to add automatically

- `primary_owner` (committer) — as assignee
- `secondary_owner` (PR reviewer) — as watcher
- Team lead of the component — as watcher (lookup from CODEOWNERS)

---

## Remote links to add

```json
{
  "object": {
    "url": "{pr_url}",
    "title": "PR #{pr_number} — {pr_title}",
    "icon": { "url16x16": "https://github.com/favicon.ico" }
  }
}
```

```json
{
  "object": {
    "url": "{appdynamics_crash_group_url}",
    "title": "AppDynamics Crash Group",
    "icon": { "url16x16": "https://www.appdynamics.com/favicon.ico" }
  }
}
```

---

## Post-creation Slack notification format

```
🔴 *New crash ticket raised*
*{JIRA-KEY}* — {error_type} in {ClassName}.{methodName}()
Version: v{app_version} | Occurrences: {occurrence_count} | Users affected: {affected_users}
Assigned to: @{primary_owner_slack_handle}
Severity: {severity} | Confidence: {CONFIDENCE}
{jira_ticket_url}
```

Keep it to one message. Don't thread-spam updates unless severity is CRITICAL.
