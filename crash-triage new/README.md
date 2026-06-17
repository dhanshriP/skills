# Crash Triage (local)

End-to-end mobile crash triage for a banking app. Paste a stacktrace (or pull
one from AppDynamics), and the server symbolicates it, redacts PII, asks your
LLM for a root-cause hypothesis, then resolves the suspect PR and owners from git.

Runs entirely on your machine. All secrets live in `.env`. The frontend never
holds a token — the browser only talks to your local server.

## Flow

```
 Browser (UI)
    │  POST /api/analyze  { platform, version, build, stacktrace, mapping, ... }
    ▼
 FastAPI server
    │  1. (optional) AppDynamics: fetch trace by crash id
    │  2. symbolicate: Android retrace(mapping.txt) / iOS atos(dSYM)
    │  3. redact PII   ── only redacted text leaves the box ──┐
    │  4. LLM root cause  ◄───────────────────────────────────┘ → your GPT-5.4 endpoint
    │  5. top app frame → git blame → commit → GitHub PR → owners
    ▼
 JSON result (AI hypotheses + git-resolved suspect leads + per-step status)
```

## Setup

### Backend (FastAPI)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in values
uvicorn server.main:app --reload --port 8000
```

### Frontend (React / Vite)

```bash
cd web
npm install
npm run dev          # http://localhost:5173  (proxies /api to :8000)
```

Run both: the backend on :8000, the React app on :5173. A zero-build fallback UI
is still served by FastAPI at http://localhost:8000 if you don't want to run node.

### Solutions → implement flow

After Analyze, click **Search the web for solutions**. The server runs a web
search (Google Programmable Search), the model ranks 2-4 candidate solutions
grounded in those results, and recommends one. Pick a solution, then answer
**"Implement … and raise a PR?"**

- **Yes** → the model writes a minimal, original patch for the suspected file,
  it's applied to a new `triage/<key>` branch (or attached as a `.patch` if it
  doesn't apply cleanly), a **draft** PR is opened with the diff, the solution's
  source links, a license/security review notice, requested reviewers, and an
  optional linked Jira ticket.
- **No** → nothing is raised.

It never merges and never copies external code verbatim. Drafts are for human
review — verify correctness, security, and license before taking out of draft.

## What each env var unlocks

| Section        | Needs                                   | If missing |
|----------------|-----------------------------------------|------------|
| LLM root cause | `LLM_BASE_URL`, `LLM_TOKEN`, `LLM_MODEL`| analysis step errors (rest still runs) |
| AppDynamics    | `APPD_*`                                | paste the trace instead |
| PR + owners    | `GITHUB_*`, `REPO_PATH`                 | git section "skipped" |
| Android symbols| `R8_RETRACE_JAR` or `retrace` on PATH   | raw trace left as-is |
| iOS symbols    | `atos` (macOS + Xcode), dSYM path       | raw trace left as-is |
| Jira ticket    | `JIRA_*`                                | "Create Jira" skipped |
| Raise draft PR | `GITHUB_*`, `GITHUB_BASE_BRANCH`        | "Raise PR" skipped |

## Jira + PR flow

After the analysis renders, the UI asks **"Raise a draft PR for this fix?"** with a
checkbox to also create a Jira ticket. On confirm:

1. (optional) a Jira issue is created with the triage summary → you get the key + link.
2. a new branch `triage/<jira-key>` is cut from the base branch.
3. a single triage note is committed (so the branch has a diff and a PR can open).
4. a **DRAFT** PR is opened with the analysis in the body, the Jira key in the title,
   reviewers requested, and the suspect owner assigned.

It never writes the code fix and never merges. A human pushes the real fix to the
branch and takes it out of draft. This is the banking constraint enforced in code:
propose, don't merge.

## Honest limitations (read before pitching)

- **AppDynamics**: uses the controller `restui` download endpoint — the same one
  the web UI calls. It works but is not an officially stable public API. Confirm
  the path against your controller version.
- **"Primary owner / which PR"**: derived from `git blame` on the crashing line.
  Blame shows the *last edit*, not the bug's origin — so it is a **suspect**, not
  proof. The UI labels it that way on purpose.
- **"Secondary owner / approver"**: returned as **reviewers to loop in**, never as
  "who is at fault." Approver-blaming is deliberately not built.
- **Raw traces**: if a trace can't be symbolicated (no mapping/dSYM archived for
  that build), git linkage is skipped — there's no reliable file:line to blame.
  This is the foundational dependency: archive `mapping.txt` and `dSYM` per build.
- **iOS atos**: stubbed as an integration point. Per-frame symbolication needs the
  build's arch + load address; wire it to your build metadata.
- The external calls (AppDynamics, GitHub, retrace/atos) were not run in the
  authoring environment — they need your real creds/tools to exercise.
```
