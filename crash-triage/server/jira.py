"""Jira integration (Jira Cloud REST API v3).

Creates a triage issue from the analysis. Auth is basic (email + API token).
Env: JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY.

Description uses Atlassian Document Format (ADF), which v3 requires.
Degrades gracefully: is_configured() lets callers skip cleanly.
"""
import os
import requests


def is_configured() -> bool:
    return all(os.environ.get(k) for k in
               ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY"))


def _adf(text: str):
    """Wrap plain text in a minimal ADF document."""
    lines = [ln for ln in text.split("\n")]
    content = [{"type": "paragraph",
                "content": [{"type": "text", "text": ln or " "}]} for ln in lines]
    return {"type": "doc", "version": 1, "content": content}


def create_issue(summary: str, description: str, labels=None, issue_type="Bug"):
    base = os.environ["JIRA_BASE_URL"].rstrip("/")
    auth = (os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"])
    project = os.environ["JIRA_PROJECT_KEY"]

    fields = {
        "project": {"key": project},
        "summary": summary[:240],
        "description": _adf(description),
        "issuetype": {"name": issue_type},
    }
    if labels:
        fields["labels"] = labels

    r = requests.post(f"{base}/rest/api/3/issue",
                      json={"fields": fields}, auth=auth, timeout=30)
    r.raise_for_status()
    key = r.json()["key"]
    return {"key": key, "url": f"{base}/browse/{key}"}
