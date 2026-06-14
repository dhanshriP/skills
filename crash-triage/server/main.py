"""Crash Triage — local server.

Pipeline for POST /api/analyze:
  1. (optional) pull trace from AppDynamics by crash id
  2. symbolicate (Android retrace / iOS atos) if raw + mapping provided
  3. redact PII  -> only the redacted trace ever reaches the LLM
  4. LLM root-cause hypothesis (your GPT-5.4 endpoint)
  5. pick the top "our code" frame -> git blame -> PR -> owners
  6. return everything with a per-section status so the UI can be honest

Run:
  pip install -r requirements.txt
  cp .env.example .env   # fill in values
  uvicorn server.main:app --reload --port 8000
"""
import os
import re
import traceback
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from . import symbolication, redact, llm, gitlink, appdynamics, jira, github_pr

load_dotenv()
app = FastAPI(title="Crash Triage")

STATIC = Path(__file__).parent / "static"

# Matches frames like  (TransferReviewFragment.kt:214)  or  (LoginView.swift:88)
_FRAME = re.compile(r"([A-Za-z0-9_$]+\.(?:kt|java|swift|m|mm)):(\d+)")


class AnalyzeRequest(BaseModel):
    platform: str = "Android"
    version: str = ""
    build: str = ""
    stacktrace: str = ""
    android_mapping: str = ""
    ios_dsym_path: str = ""
    flow_hint: str = ""
    appd_crash_id: str = ""


def _pick_suspect_frame(trace: str):
    """First frame that looks like our code, else the first frame at all."""
    prefix = os.environ.get("APP_PACKAGE_PREFIX", "")
    candidates = []
    for line in trace.splitlines():
        m = _FRAME.search(line)
        if m:
            candidates.append((line, m.group(1), int(m.group(2))))
    if not candidates:
        return None
    if prefix:
        for line, fname, ln in candidates:
            if prefix in line:
                return {"file": fname, "line": ln}
    return {"file": candidates[0][1], "line": candidates[0][2]}


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC / "index.html").read_text()


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    result = {"sections": {}}
    trace = req.stacktrace

    # 1. AppDynamics (optional)
    if req.appd_crash_id and appdynamics.is_configured():
        try:
            trace = appdynamics.fetch_crash_trace(req.appd_crash_id)
            result["sections"]["appdynamics"] = {"status": "ok", "note": "fetched by crash id"}
        except Exception as e:
            result["sections"]["appdynamics"] = {"status": "error", "note": str(e)}
    elif req.appd_crash_id:
        result["sections"]["appdynamics"] = {"status": "skipped", "note": "AppDynamics not configured"}

    if not trace.strip():
        return JSONResponse({"error": "No stacktrace provided"}, status_code=400)

    # 2. Symbolication
    sym = symbolication.symbolicate(trace, req.platform, req.android_mapping, req.ios_dsym_path)
    trace = sym["trace"]
    result["sections"]["symbolication"] = {"status": sym["status"], "note": sym["note"]}

    # 3. Redaction (always, before the LLM)
    redacted, findings = redact.redact(trace)
    result["sections"]["redaction"] = {"status": "ok", "findings": findings}

    # 4. LLM root-cause
    try:
        ai = llm.analyze(redacted, req.platform, req.version, req.build, req.flow_hint)
        result["ai"] = ai
        result["sections"]["llm"] = {"status": "ok"}
    except Exception as e:
        result["ai"] = {}
        result["sections"]["llm"] = {"status": "error", "note": str(e)}

    # 5. Git linkage (only if we have a usable symbolicated frame)
    if sym["status"] == "raw":
        result["git"] = {"status": "skipped", "note": "trace is raw — no reliable file:line to blame"}
    else:
        frame = _pick_suspect_frame(trace)
        if not frame:
            result["git"] = {"status": "skipped", "note": "no source frame found in trace"}
        else:
            try:
                result["git"] = gitlink.link(frame["file"], frame["line"])
            except Exception as e:
                result["git"] = {"status": "error", "note": str(e), "trace": traceback.format_exc()[:300]}

    return result


# ---- Jira + PR flow (post-analysis, human-triggered) ----

class JiraRequest(BaseModel):
    severity: str = ""
    flow: str = ""
    root_cause: str = ""
    internal_module: str = ""
    suspected_file: str = ""
    platform: str = ""
    version: str = ""
    build: str = ""
    pr_link: str = ""


def _summary(d: "JiraRequest"):
    return f"[{d.severity or 'P?'}] Crash in {d.flow or d.internal_module or 'app'} ({d.platform} v{d.version})"


def _description(d: "JiraRequest"):
    return (
        f"Auto-generated crash triage (for human review).\n\n"
        f"Platform: {d.platform}  Version: {d.version}  Build: {d.build}\n"
        f"Flow: {d.flow}\n"
        f"Module/lib: {d.internal_module}\n"
        f"Suspected file: {d.suspected_file}\n\n"
        f"Root-cause hypothesis:\n{d.root_cause}\n\n"
        f"Suspect PR (last-touch lead): {d.pr_link or 'n/a'}\n\n"
        f"NOTE: hypotheses and suspect leads. Not a confirmed cause. No code merged."
    )


@app.post("/api/jira")
def create_jira(req: JiraRequest):
    if not jira.is_configured():
        return JSONResponse({"status": "skipped", "note": "Jira not configured"}, status_code=200)
    try:
        issue = jira.create_issue(_summary(req), _description(req), labels=["crash-triage", "auto"])
        return {"status": "ok", **issue}
    except Exception as e:
        return JSONResponse({"status": "error", "note": str(e)}, status_code=200)


class RaisePRRequest(JiraRequest):
    primary_owner_suspect: str = ""   # github login to assign (if resolvable)
    reviewers: list[str] = []
    jira_key: str = ""
    create_jira: bool = False


@app.post("/api/raise-pr")
def raise_pr(req: RaisePRRequest):
    out = {"status": "ok"}

    # Optionally create the Jira ticket first and link it.
    jira_key = req.jira_key
    if req.create_jira and jira.is_configured() and not jira_key:
        try:
            issue = jira.create_issue(_summary(req), _description(req), labels=["crash-triage", "auto"])
            jira_key = issue["key"]
            out["jira"] = {"status": "ok", **issue}
        except Exception as e:
            out["jira"] = {"status": "error", "note": str(e)}

    if not github_pr.is_configured():
        out["status"] = "skipped"
        out["note"] = "GitHub not configured"
        return out

    title = (f"[{jira_key}] " if jira_key else "") + _summary(req)
    note = "# Crash triage\n\n" + _description(req)
    body = (note + ("\n\nLinked Jira: " + jira_key if jira_key else "") +
            "\n\n---\nDRAFT. Push the actual fix to this branch, then take it out of draft. "
            "Reviewers are requested, not approvers of blame.")
    # Strip an email form of the owner to a bare handle if it slipped through.
    assignee = (req.primary_owner_suspect or "").split("@")[0] or None
    try:
        pr = github_pr.raise_draft_pr(title, body, note,
                                      reviewers=req.reviewers or None,
                                      assignee=assignee, jira_key=jira_key)
        out["pr"] = {"status": "ok", **pr}
    except Exception as e:
        out["pr"] = {"status": "error", "note": str(e)}
        out["status"] = "error"
    return out
