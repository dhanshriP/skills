"""Apply a unified diff to a single file's content, safely, in a temp git repo.

Returns the patched text, or None if the diff doesn't apply cleanly. We never
force a messy apply into a banking codebase — a clean apply or nothing.
"""
import os
import subprocess
import tempfile


def apply_diff(rel_path: str, original: str, diff_text: str):
    if not diff_text.strip():
        return None
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "init", "-q"], cwd=tmp, timeout=20)
        target = os.path.join(tmp, rel_path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w") as f:
            f.write(original)
        subprocess.run(["git", "add", "."], cwd=tmp, timeout=20)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "base"], cwd=tmp, timeout=20)
        diff_path = os.path.join(tmp, "change.diff")
        with open(diff_path, "w") as f:
            f.write(diff_text if diff_text.endswith("\n") else diff_text + "\n")
        res = subprocess.run(["git", "apply", "--whitespace=nowarn", diff_path],
                             cwd=tmp, capture_output=True, text=True, timeout=20)
        if res.returncode != 0:
            return None
        with open(target) as f:
            return f.read()
