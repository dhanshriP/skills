---
name: crash-triage
description: >
  Use this skill whenever a developer, lead, QA, or TPM needs to triage a mobile banking
  crash or incident. Triggers when: a crash log or stack trace is pasted or received from
  AppDynamics, someone asks "who owns this crash", an incident needs a Jira ticket raised,
  or when attribution + root-cause analysis is needed on a mobile crash. This skill handles
  the full pipeline: sanitize → deobfuscate → git blame → PR attribution → AI analysis →
  deduplication → human confirmation → Jira creation. Always use this skill for crash triage
  workflows, even if the user only pastes a partial stack trace or just asks "can you raise a
  ticket for this".
---

# Crash Triage Skill

A structured agent workflow for mobile banking crash triage. Converts a raw AppDynamics crash
log into an attributed, deduplicated, human-confirmed Jira ticket with root-cause analysis.

## Roles this serves
- **Developer**: knows who to fix it and gets a hypothesis
- **Lead**: gets severity, blast radius, and estimation
- **QA**: gets reproduction context and affected version
- **TPM**: gets incident status and impact summary

---

## Phase Overview

```
INPUT → SANITIZE → DEOBFUSCATE → ATTRIBUTE → DEDUPLICATE → ANALYSE → CONFIRM → CREATE
```

Never skip phases. Never create a Jira ticket without human confirmation.
Never send unsanitized data to any external API.

---

## Phase 1: Input Parsing

### How crashes reach this agent — three modes

**Mode A: AppDynamics Webhook (fully automatic — recommended)**
AppDynamics fires an HTTP POST to your agent's endpoint whenever a crash policy triggers.
No manual input needed. Configure in AppDynamics:
`Alert & Respond → HTTP Request Templates → point to your agent endpoint`
Set a threshold policy (e.g. "trigger if crash rate > 5 in 10 minutes") so you don't
get a ticket for every single one-off occurrence.

**Mode B: AppDynamics API Polling (scheduled, no webhook config needed)**
Agent runs on a schedule (e.g. every 15 minutes) and calls:
`GET /controller/rest/applications/{app_id}/problems`
or
`GET /controller/rest/mobileanalytics/v1/apps/{app_id}/crashes`
Fetches new crash groups since last poll. Good if webhook setup is blocked by your infra team.

**Mode C: Manual paste (zero setup — lowest automation)**
Developer sees a crash in AppDynamics, copies the stack trace, pastes it directly to the agent.
Still gets full triage: deobfuscation, attribution, analysis, confirmation, ticket creation.
Use this while Modes A/B are being set up, or for one-off investigations.

> **Which to start with:** Mode C costs nothing to set up and validates the whole pipeline end-to-end. Do Mode C first, get the workflow right, then wire up Mode A for production use.

### Extract from whichever mode triggered:

Accept crash input in any of these forms:
- Raw AppDynamics webhook payload (JSON)
- Pasted stack trace (plain text)
- AppDynamics crash group URL (fetch if accessible)

Extract and tag:
- `app_version` — e.g. `4.2.1`
- `build_number` — e.g. `1042` (critical for mapping file lookup)
- `platform` — `android` | `ios` | `react_native`
- `error_type` — e.g. `NullPointerException`, `NSInvalidArgumentException`
- `error_message` — first line of the crash
- `stack_frames` — full ordered list
- `occurrence_count` — how many times AppDynamics has seen this
- `first_seen` / `last_seen` timestamps
- `affected_users` — count if available

**If `build_number` is missing**: halt. Ask the user for it.
A deobfuscation mapping file cannot be retrieved without it.
Do not proceed with an obfuscated trace — the attribution will be wrong.

---

## Phase 2: Sanitization

**Mandatory before any external call or AI prompt.**

Strip or redact from the stack trace and error message:
- Account numbers, card numbers, PAN (16-digit sequences)
- Session tokens, JWT strings
- User IDs, customer IDs
- Device identifiers (IMEI, serial)
- IP addresses
- Any value matching banking data patterns in your PII regex list

Replace with `[REDACTED]`. Log what was redacted and where for audit.

> See `references/banking-guardrails.md` for PII regex patterns and audit log format.

---

## Phase 3: Deobfuscation

Fetch the correct mapping/symbol file from your artifact store using `app_version` + `build_number`.

| Platform | File type | Tool |
|---|---|---|
| Android | ProGuard mapping.txt | `proguard-retrace` or `retrace.jar` |
| iOS | dSYM bundle | `atos` or `symbolicatecrash` |
| React Native | source map (.map) | `source-map` CLI |

**If mapping file not found**: halt and set `resolution_status = UNRESOLVABLE`.
Create a Jira ticket flagged as `[TRIAGE BLOCKED] — mapping file missing for build {build_number}`.
Assign to the build/release engineer. Do not attempt attribution.

After deobfuscation:
1. Filter out framework frames (Android SDK, OkHttp, Retrofit, UIKit, Foundation — anything not in your org's package namespaces)
2. Take top **3–5 non-framework frames** for attribution
3. Store full deobfuscated trace for ticket body

> See `references/deobfuscation.md` for platform-specific commands and filtering rules.

---

## Phase 4: Attribution

For each of the top 3–5 deobfuscated frames, call your Git host API:

**Step 4a — git blame**
```
GET /repos/{owner}/{repo}/blame/{file_path}?ref=main
```
Identify: `committer_name`, `committer_email`, `commit_sha`, `commit_date`
for the specific line number from the stack frame.

**Step 4b — PR lookup**
```
GET /repos/{owner}/{repo}/commits/{commit_sha}/pulls
```
Extract: `pr_number`, `pr_author`, `pr_reviewer` (who approved the merge), `merged_at`

**Attribution priority:**
- Primary owner = committer of top non-framework frame
- Secondary (watcher) = PR reviewer who approved it
- If commit is >90 days old and file has had subsequent commits: flag as "ownership uncertain — multiple contributors"

Store: `primary_owner`, `secondary_owner`, `commit_sha`, `pr_number`, `pr_url`

---

## Phase 5: Deduplication

**Before any analysis or ticket creation, check for duplicates.**

Generate dedup hash:
```
hash = SHA256(top_frame_class + top_frame_method + top_frame_line)
```

Query Jira:
```
JQL: project = {project} AND cf[crash_hash] = "{hash}" AND status != Done
```

**If duplicate found:**
- Increment `occurrence_count` on the existing ticket (add a comment with new count + timestamp)
- Do NOT create a new ticket
- Notify the channel: "Existing ticket {JIRA-KEY} — occurrence count updated to {n}"
- **Stop here.**

**If no duplicate:** continue to Phase 6.

---

## Phase 6: AI Analysis

Construct the analysis prompt with sanitized data only:

```
You are a senior mobile banking engineer. Analyse this crash.

Platform: {platform}
Error: {error_type}: {error_message}
App version: {app_version}

Deobfuscated stack trace (sanitized):
{sanitized_deobfuscated_trace}

Source code context (top frame ±20 lines):
{source_code_snippet}

Respond in this exact structure:
ROOT_CAUSE: [one sentence]
HYPOTHESIS: [2–3 sentences, specific to the code shown]
LIKELY_FIX: [concrete suggestion, reference the specific line/method]
BLAST_RADIUS: [what else might be affected — other screens, flows, APIs]
SEVERITY_SUGGESTION: [CRITICAL|HIGH|MEDIUM|LOW with one-line reason]
CONFIDENCE: [HIGH|MEDIUM|LOW — how confident is this analysis]
```

**For estimation:** do NOT ask the AI to estimate effort from the stack trace alone.
Query Jira history instead:
```
JQL: project = {project} AND component = {component} AND issuetype = Bug 
     AND labels = crash AND status = Done ORDER BY resolutiondate DESC
```
Take the median close time of the last 5–10 similar bugs.
Label it in the ticket as: `Estimate: Xd (based on {n} historical similar bugs — not AI-generated)`

---

## Phase 7: Human Confirmation (MANDATORY)

**Never skip this phase. Never auto-create a Jira ticket.**

Present a pre-filled triage summary for review. Format:

---
**🔍 Crash Triage Summary — awaiting your confirmation**

| Field | Value |
|---|---|
| Error | {error_type}: {error_message} |
| App version | {app_version} |
| Occurrences | {occurrence_count} |
| Affected users | {affected_users} |
| First seen | {first_seen} |
| Top frame | {class}.{method}() line {line} |
| Committer | {primary_owner} ({commit_date}) |
| PR | #{pr_number} — reviewed by {secondary_owner} |
| Root cause | {ROOT_CAUSE} |
| Suggested fix | {LIKELY_FIX} |
| Blast radius | {BLAST_RADIUS} |
| Suggested severity | {SEVERITY_SUGGESTION} |
| Confidence | {CONFIDENCE} |
| Estimate | {estimate} ({source}) |

**Proposed Jira ticket:**
- Summary: `[CRASH] {error_type} in {class}.{method}() — v{app_version}`
- Assignee: {primary_owner}
- Severity: {SEVERITY_SUGGESTION}
- Component: {derived_component}

---

Then ask **one consolidated question** with these options:

> **Does this look right? Choose an action:**
> - ✅ Create ticket as shown
> - ✏️ Edit before creating (specify what to change)
> - 🔁 Reassign to someone else
> - ❌ Don't create — mark as known/won't fix
> - 🔗 Link to existing ticket instead

Wait for the user's response. Do not proceed until they choose.
If they choose "Edit", collect their changes, re-present the summary, confirm again.

---

## Phase 8: Jira Ticket Creation

Only after explicit confirmation in Phase 7.

Create ticket with these fields:

```json
{
  "summary": "[CRASH] {error_type} in {class}.{method}() — v{app_version}",
  "issuetype": "Bug",
  "priority": "{confirmed_severity}",
  "assignee": "{confirmed_owner}",
  "components": ["{derived_component}"],
  "labels": ["crash", "automated-triage", "{platform}"],
  "description": "See references/jira-ticket-schema.md for full field mapping",
  "customfield_crash_hash": "{dedup_hash}",
  "customfield_ai_confidence": "{CONFIDENCE}",
  "customfield_triage_source": "automated-crash-triage-agent"
}
```

After creation:
1. Add PR link as remote link on the ticket
2. Add committer and PR reviewer as watchers
3. Post deobfuscated stack trace as a collapsed attachment (not inline — keeps ticket readable)
4. Post to the team's Slack/Teams channel: ticket key, one-line summary, assignee, severity

Tag all agent-created tickets with `triage_source: automated` so humans can audit and filter them.

> See `references/jira-ticket-schema.md` for the full field schema and API call structure.

---

## Error States

| Condition | Action |
|---|---|
| Build number missing | Halt, ask user |
| Mapping file not found | Create blocked ticket, assign to release engineer |
| git blame returns no match | Flag as "attribution uncertain", assign to team lead |
| Duplicate found in Jira | Update occurrence count, do not create new ticket |
| AI confidence = LOW | Flag in ticket, add note: "Manual review of root cause recommended" |
| PII detected in trace | Redact, log redaction, continue |

---

## What this skill does NOT do

- Does not auto-merge or auto-commit fixes
- Does not push to production environments
- Does not assign tickets without human confirmation
- Does not use prod customer data in AI prompts
- Does not generate effort estimates from the stack trace alone — only from historical data

> For banking compliance context, always read `references/banking-guardrails.md` first.
