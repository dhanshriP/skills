"""Call the configured LLM endpoint to get a root-cause hypothesis.

OpenAI-compatible /v1/chat/completions is assumed. If your GPT-5.4 endpoint
differs, adjust the URL, body, and response parsing in `analyze`.

Guardrails are in the system prompt: never invent symbols for raw traces,
owner_hint is a TEAM/AREA not a person, flag any residual PII.
"""
import os
import json
import requests

SYSTEM = (
    "You are a mobile crash triage assistant for a banking app (Android/Kotlin, "
    "iOS/SwiftUI). Analyze ONLY the provided trace. Rules: if the trace is "
    "obfuscated/raw, set trace_status to 'raw', keep root_cause generic, drop "
    "confidence below 30, and NEVER invent class/method names. Identify the most "
    "likely responsible module: internal_module should name the app module/package "
    "(e.g. 'payments'); set is_app_code=false and name the library in internal_module "
    "if the top frames are a third-party SDK or the OS. owner_hint must be a TEAM/AREA, "
    "never a person. Flag any values that look like PANs, tokens, or emails in "
    "pii_findings. Respond with ONLY a JSON object, no markdown, keys: severity "
    "(P1|P2|P3), flow, trace_status (symbolicated|partial|raw), is_app_code (bool), "
    "internal_module, root_cause (1-2 sentences), suspected_file, suspected_line "
    "(int or null), owner_hint, pii_findings (array), confidence (0-100)."
)


def analyze(trace: str, platform: str, version: str, build: str, flow_hint: str = ""):
    base = os.environ.get("LLM_BASE_URL", "").rstrip("/")
    token = os.environ.get("LLM_TOKEN", "")
    model = os.environ.get("LLM_MODEL", "gpt-5.4")
    if not (base and token):
        raise RuntimeError("LLM_BASE_URL / LLM_TOKEN not set")

    user = (f"Platform: {platform}\nVersion: {version}  Build: {build}\n"
            f"Known flow hint: {flow_hint or '(none)'}\n\nTRACE:\n{trace}")

    # --- ADJUST to match your endpoint's contract if needed ---
    url = f"{base}/v1/chat/completions"
    body = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": user}],
        "max_tokens": 1000,
        "temperature": 0,
    }
    r = requests.post(url, headers={"Authorization": f"Bearer {token}",
                                    "Content-Type": "application/json"},
                      json=body, timeout=90)
    r.raise_for_status()
    data = r.json()
    content = data["choices"][0]["message"]["content"].strip()
    content = content.replace("```json", "").replace("```", "").strip()
    start, end = content.find("{"), content.rfind("}")
    if start >= 0 and end > start:
        content = content[start:end + 1]
    return json.loads(content)


def _chat(system: str, user: str, max_tokens: int = 1500):
    """Shared call to the OpenAI-compatible endpoint, returns parsed JSON."""
    base = os.environ.get("LLM_BASE_URL", "").rstrip("/")
    token = os.environ.get("LLM_TOKEN", "")
    model = os.environ.get("LLM_MODEL", "gpt-5.4")
    if not (base and token):
        raise RuntimeError("LLM_BASE_URL / LLM_TOKEN not set")
    r = requests.post(
        f"{base}/v1/chat/completions",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"model": model, "temperature": 0, "max_tokens": max_tokens,
              "messages": [{"role": "system", "content": system},
                           {"role": "user", "content": user}]},
        timeout=120,
    )
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"].strip()
    content = content.replace("```json", "").replace("```", "").strip()
    s, e = content.find("{"), content.rfind("}")
    if s >= 0 and e > s:
        content = content[s:e + 1]
    return json.loads(content)


def propose_solutions(root_cause: str, platform: str, internal_module: str, results: list):
    """Rank candidate solutions, grounded in web search results where possible."""
    src = "\n".join(f"[{i}] {r['title']} — {r['snippet']} ({r['link']})"
                    for i, r in enumerate(results)) or "(no web results available)"
    system = (
        "You are a senior mobile engineer triaging a banking-app crash. Given a root cause "
        "and web search results, propose 2-4 candidate solutions. Prefer solutions supported "
        "by the provided sources; if a candidate relies on general knowledge, set sources to []. "
        "For each, assess risk for a regulated banking app (low|medium|high). Pick the best. "
        "Respond ONLY with JSON: {solutions:[{title, approach (2-3 sentences), pros, cons, "
        "risk, sources:[result indices]}], recommended_index (int)}."
    )
    user = (f"Root cause: {root_cause}\nPlatform: {platform}\nModule/lib: {internal_module}\n\n"
            f"Web results:\n{src}")
    return _chat(system, user, max_tokens=1500)


def generate_patch(rel_path: str, file_content: str, solution_title: str,
                   solution_approach: str, root_cause: str, platform: str):
    """Produce a MINIMAL unified diff implementing the chosen solution.

    Writes an original implementation (do not copy external code verbatim — license).
    """
    system = (
        "You implement a minimal, original code change for a banking mobile app. "
        "Do NOT copy code verbatim from external sources (license/compliance) — write an "
        "original implementation of the approach. Make the smallest change that addresses the "
        "root cause. Return ONLY JSON: {explanation (string), diff (a valid unified diff with "
        "---/+++ headers and @@ hunks, paths relative to repo root)}. If you cannot produce a "
        "safe change, return {explanation, diff:''}."
    )
    user = (f"File: {rel_path}\nPlatform: {platform}\nRoot cause: {root_cause}\n"
            f"Chosen solution: {solution_title} — {solution_approach}\n\n"
            f"Current file content:\n{file_content}")
    return _chat(system, user, max_tokens=4000)
