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
