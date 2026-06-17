"""Turn a raw/obfuscated stacktrace into a symbolicated one.

Android: R8/ProGuard `retrace` against a mapping.txt (pasted by the user).
iOS:     `atos` against a dSYM path (binary, so the user gives a server-side path).

Everything degrades gracefully: if a tool or input is missing, we return the
trace unchanged and report status so the rest of the pipeline (and the UI) knows
NOT to trust downstream file/line mapping. We never fabricate symbols.
"""
import os
import re
import shutil
import subprocess
import tempfile

# Heuristics for "is this already human-readable?"
_OBFUSCATED_ANDROID = re.compile(r"\bat\s+[a-z]{1,3}(\.[a-z]{1,3}){1,}\(", re.MULTILINE)
_UNKNOWN_SOURCE = re.compile(r"\(Unknown Source\)|\(SourceFile\)")
_IOS_RAW_FRAME = re.compile(r"0x[0-9a-fA-F]{6,}\s+0x[0-9a-fA-F]{6,}\s*\+")


def detect_status(trace: str, platform: str) -> str:
    """Return 'symbolicated' | 'partial' | 'raw'."""
    if platform.lower() == "ios":
        return "raw" if _IOS_RAW_FRAME.search(trace) else "symbolicated"
    # android
    if _UNKNOWN_SOURCE.search(trace) or _OBFUSCATED_ANDROID.search(trace):
        return "raw"
    return "symbolicated"


def android_retrace(trace: str, mapping_text: str):
    """Run R8/ProGuard retrace. Returns (text, note)."""
    if not mapping_text.strip():
        return trace, "no mapping.txt provided"

    with tempfile.TemporaryDirectory() as tmp:
        map_path = os.path.join(tmp, "mapping.txt")
        trace_path = os.path.join(tmp, "trace.txt")
        with open(map_path, "w") as f:
            f.write(mapping_text)
        with open(trace_path, "w") as f:
            f.write(trace)

        jar = os.environ.get("R8_RETRACE_JAR", "").strip()
        if jar:
            cmd = ["java", "-jar", jar, map_path, trace_path]
        elif shutil.which("retrace"):
            cmd = ["retrace", map_path, trace_path]
        else:
            return trace, "retrace tool not found (set R8_RETRACE_JAR or install retrace)"

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout, "retraced with mapping.txt"
            return trace, f"retrace failed: {res.stderr.strip()[:200]}"
        except Exception as e:
            return trace, f"retrace error: {e}"


def ios_symbolicate(trace: str, dsym_path: str):
    """Best-effort iOS symbolication via atos.

    True dSYM symbolication needs the raw frame addresses + load address + arch.
    AppDynamics often returns already-symbolicated text; if so, nothing to do.
    If raw addresses are present and a dSYM path + atos exist, attempt per-frame.
    """
    if not dsym_path or not os.path.exists(dsym_path):
        return trace, "no dSYM path provided / path not found"
    if not shutil.which("atos"):
        return trace, "atos not found (run on macOS with Xcode tools)"
    if not _IOS_RAW_FRAME.search(trace):
        return trace, "no raw addresses in trace; nothing to symbolicate"
    # Per-frame atos requires arch + load address parsing that is build-specific.
    # Left as an explicit integration point rather than a fragile guess.
    return trace, "raw iOS addresses detected — wire atos with your build's arch/load address"


def symbolicate(trace: str, platform: str, android_mapping: str = "", ios_dsym_path: str = ""):
    status = detect_status(trace, platform)
    if status == "symbolicated":
        return {"trace": trace, "status": "symbolicated", "note": "already human-readable"}

    if platform.lower() == "ios":
        text, note = ios_symbolicate(trace, ios_dsym_path)
    else:
        text, note = android_retrace(trace, android_mapping)

    new_status = detect_status(text, platform)
    return {"trace": text, "status": new_status, "note": note}
