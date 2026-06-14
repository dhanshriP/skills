"""Map a symbolicated file:line to git/PR ownership.

Chain: file:line --git blame--> commit --GitHub API--> PR --> reviewers.

Honest framing baked in:
- "last committer" is the person who last TOUCHED that line, returned as a
  SUSPECT for primary owner, not proof they caused the bug.
- PR reviewers are returned as people to LOOP IN, not "who is at fault".
  We deliberately do not label an approver as the cause of a crash.

GitHub is assumed. For GitLab/Bitbucket, swap the API calls in _commit_prs /
_pr_reviews. Everything degrades gracefully when env vars are missing.
"""
import os
import subprocess
import requests

API = "https://api.github.com"


def _gh_headers():
tok = os.environ.get("GITHUB_TOKEN", "")
h = {"Accept": "application/vnd.github+json"}
if tok:
h["Authorization"] = f"Bearer {tok}"
return h


def _find_file(repo_path: str, filename: str):
"""Resolve a bare filename (e.g. TransferReviewFragment.kt) to a repo path."""
try:
res = subprocess.run(
["git", "-C", repo_path, "ls-files", f"*{filename}"],
capture_output=True, text=True, timeout=20,
)
paths = [p for p in res.stdout.splitlines() if p.strip()]
return paths[0] if paths else None
except Exception:
return None


def _blame_line(repo_path: str, path: str, line: int):
try:
res = subprocess.run(
["git", "-C", repo_path, "blame", "-L", f"{line},{line}",
"--porcelain", "--", path],
capture_output=True, text=True, timeout=20,
)
if res.returncode != 0:
return None
out = res.stdout
sha = out.split(" ", 1)[0] if out else None
def grab(key):
for ln in out.splitlines():
if ln.startswith(key + " "):
return ln[len(key) + 1:].strip()
return None
return {
"commit": sha,
"author": grab("author"),
"author_mail": (grab("author-mail") or "").strip("<>"),
"summary": grab("summary"),
}
except Exception:
return None


def _commit_prs(sha: str):
owner, repo = os.environ.get("GITHUB_OWNER"), os.environ.get("GITHUB_REPO")
if not (owner and repo and sha):
return []
url = f"{API}/repos/{owner}/{repo}/commits/{sha}/pulls"
r = requests.get(url, headers=_gh_headers(), timeout=20)
if r.status_code != 200:
return []
return [{"number": p["number"], "url": p["html_url"], "title": p["title"],
"author": p["user"]["login"]} for p in r.json()]


def _pr_reviews(number: int):
owner, repo = os.environ.get("GITHUB_OWNER"), os.environ.get("GITHUB_REPO")
url = f"{API}/repos/{owner}/{repo}/pulls/{number}/reviews"
r = requests.get(url, headers=_gh_headers(), timeout=20)
if r.status_code != 200:
return []
approvers = []
for rv in r.json():
if rv.get("state") == "APPROVED":
login = rv["user"]["login"]
if login not in approvers:
approvers.append(login)
return approvers


def link(filename: str, line: int):
"""Return ownership info for a file:line, with per-step status."""
repo_path = os.environ.get("REPO_PATH", "")
result = {
"status": "ok",
"file": filename, "line": line,
"primary_owner_suspect": None,   # last committer of the line
"commit": None,
"pr": None,                      # {number, url, title, author}
"reviewers_to_loop_in": [],      # PR approvers
"note": "",
}
if not (repo_path and os.path.isdir(repo_path)):
result["status"] = "skipped"
result["note"] = "REPO_PATH not set or not a directory"
return result

    path = _find_file(repo_path, filename)
    if not path:
        result["status"] = "skipped"
        result["note"] = f"{filename} not found in repo"
        return result

    blame = _blame_line(repo_path, path, line)
    if not blame:
        result["status"] = "skipped"
        result["note"] = "git blame returned nothing"
        return result

    result["commit"] = blame["commit"]
    result["primary_owner_suspect"] = blame.get("author_mail") or blame.get("author")
    result["file"] = path

    try:
        prs = _commit_prs(blame["commit"])
        if prs:
            result["pr"] = prs[0]
            result["reviewers_to_loop_in"] = _pr_reviews(prs[0]["number"])
        else:
            result["note"] = "no PR associated with commit (or GitHub not configured)"
    except Exception as e:
        result["note"] = f"PR lookup error: {e}"
    return result
