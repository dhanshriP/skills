"""Redact sensitive values from a crash payload before it reaches the model.

In a bank, crash breadcrumbs routinely carry PANs, account numbers, tokens, and
emails. This runs BEFORE the LLM call. It returns the redacted text plus a list
of finding *types* (never the raw values) so the UI can flag a leak.
"""
import re

# Order matters: most specific first.
_PATTERNS = [
    ("bearer_token", re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{12,}")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")),
    ("email", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
    # PAN: 13-19 digits, optionally space/dash grouped (e.g. 4716 1234 5678 9012)
    ("pan_or_account", re.compile(r"\b(?:\d[ \-]?){13,19}\b")),
    ("long_hex_token", re.compile(r"\b[0-9a-fA-F]{24,}\b")),
]


def redact(text: str):
    findings = []
    redacted = text
    for label, rx in _PATTERNS:
        hits = rx.findall(redacted)
        if hits:
            findings.append({"type": label, "count": len(hits)})
            redacted = rx.sub(f"[REDACTED:{label}]", redacted)
    return redacted, findings
