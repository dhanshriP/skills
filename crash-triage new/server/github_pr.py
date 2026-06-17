"""Open a DRAFT pull request for a triaged crash.

Banking constraint, enforced here: this never merges and never writes a code
fix. It creates a new branch off the base, commits a single triage note, opens
a DRAFT PR with the analysis in the body, requests reviewers, and assigns the
suspect owner. A human pushes the actual fix to that branch and takes it out of
draft. Propose, don't merge.

Env: GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO, GITHUB_BASE_BRANCH (default 'main').
"""
import os
import time
import base64
import requests

API = "https://api.github.com"


def is_configured() -> bool:
    return all(os.environ.get(k) for k in ("GITHUB_TOKEN", "GITHUB_OWNER", "GITHUB_REPO"))


def _h():
    return {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json"}


def raise_draft_pr(title: str, body: str, note_markdown: str,
                   reviewers=None, assignee=None, jira_key=None):
    owner = os.environ["GITHUB_OWNER"]
    repo = os.environ["GITHUB_REPO"]
    base = os.environ.get("GITHUB_BASE_BRANCH", "main")
    slug = jira_key or f"triage-{int(time.time())}"
    branch = f"triage/{slug}"

    # 1. base SHA
    r = requests.get(f"{API}/repos/{owner}/{repo}/git/ref/heads/{base}", headers=_h(), timeout=30)
    r.raise_for_status()
    base_sha = r.json()["object"]["sha"]

    # 2. new branch
    r = requests.post(f"{API}/repos/{owner}/{repo}/git/refs", headers=_h(), timeout=30,
                      json={"ref": f"refs/heads/{branch}", "sha": base_sha})
    if r.status_code not in (200, 201):
        raise RuntimeError(f"create branch failed: {r.status_code} {r.text[:200]}")

    # 3. commit a triage note so the branch differs from base (lets us open a PR)
    content = base64.b64encode(note_markdown.encode()).decode()
    r = requests.put(f"{API}/repos/{owner}/{repo}/contents/triage/{slug}.md", headers=_h(), timeout=30,
                     json={"message": f"triage: {title}", "content": content, "branch": branch})
    if r.status_code not in (200, 201):
        raise RuntimeError(f"create note failed: {r.status_code} {r.text[:200]}")

    # 4. draft PR
    r = requests.post(f"{API}/repos/{owner}/{repo}/pulls", headers=_h(), timeout=30,
                      json={"title": title, "head": branch, "base": base, "body": body, "draft": True})
    if r.status_code not in (200, 201):
        raise RuntimeError(f"create PR failed: {r.status_code} {r.text[:200]}")
    pr = r.json()
    number = pr["number"]

    # 5. request reviewers (best-effort)
    if reviewers:
        requests.post(f"{API}/repos/{owner}/{repo}/pulls/{number}/requested_reviewers",
                      headers=_h(), timeout=30, json={"reviewers": reviewers})
    # 6. assign suspect owner (best-effort)
    if assignee:
        requests.post(f"{API}/repos/{owner}/{repo}/issues/{number}/assignees",
                      headers=_h(), timeout=30, json={"assignees": [assignee]})

    return {"url": pr["html_url"], "number": number, "branch": branch, "draft": True}


# ---- granular helpers for committing a real file change ----

def get_file(path: str, ref: str = None):
    owner, repo = os.environ["GITHUB_OWNER"], os.environ["GITHUB_REPO"]
    params = {"ref": ref} if ref else {}
    r = requests.get(f"{API}/repos/{owner}/{repo}/contents/{path}",
                     headers=_h(), params=params, timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    j = r.json()
    return {"sha": j["sha"], "content": base64.b64decode(j["content"]).decode("utf-8", "replace")}


def create_branch(slug: str):
    owner, repo = os.environ["GITHUB_OWNER"], os.environ["GITHUB_REPO"]
    base = os.environ.get("GITHUB_BASE_BRANCH", "main")
    r = requests.get(f"{API}/repos/{owner}/{repo}/git/ref/heads/{base}", headers=_h(), timeout=30)
    r.raise_for_status()
    base_sha = r.json()["object"]["sha"]
    branch = f"triage/{slug}"
    r = requests.post(f"{API}/repos/{owner}/{repo}/git/refs", headers=_h(), timeout=30,
                      json={"ref": f"refs/heads/{branch}", "sha": base_sha})
    if r.status_code not in (200, 201):
        raise RuntimeError(f"create branch failed: {r.status_code} {r.text[:200]}")
    return branch, base


def put_file(branch: str, path: str, text: str, message: str, sha: str = None):
    owner, repo = os.environ["GITHUB_OWNER"], os.environ["GITHUB_REPO"]
    body = {"message": message, "content": base64.b64encode(text.encode()).decode(), "branch": branch}
    if sha:
        body["sha"] = sha
    r = requests.put(f"{API}/repos/{owner}/{repo}/contents/{path}", headers=_h(), timeout=30, json=body)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"put file failed: {r.status_code} {r.text[:200]}")


def open_draft_pr(title: str, branch: str, base: str, body: str, reviewers=None, assignee=None):
    owner, repo = os.environ["GITHUB_OWNER"], os.environ["GITHUB_REPO"]
    r = requests.post(f"{API}/repos/{owner}/{repo}/pulls", headers=_h(), timeout=30,
                      json={"title": title, "head": branch, "base": base, "body": body, "draft": True})
    if r.status_code not in (200, 201):
        raise RuntimeError(f"create PR failed: {r.status_code} {r.text[:200]}")
    pr = r.json()
    if reviewers:
        requests.post(f"{API}/repos/{owner}/{repo}/pulls/{pr['number']}/requested_reviewers",
                      headers=_h(), timeout=30, json={"reviewers": reviewers})
    if assignee:
        requests.post(f"{API}/repos/{owner}/{repo}/issues/{pr['number']}/assignees",
                      headers=_h(), timeout=30, json={"assignees": [assignee]})
    return {"url": pr["html_url"], "number": pr["number"], "branch": branch, "draft": True}
