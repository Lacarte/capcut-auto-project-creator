# doctor.py
from __future__ import annotations
from typing import Dict, Any, List

def inspect_and_fix(
    draft_content: Dict[str, Any],
    draft_meta_info: Dict[str, Any],
    draft_virtual_store: Dict[str, Any],
    strict: bool = True,
    autofix: bool = True,
) -> Dict[str, Any]:
    """
    Minimal validator:
    - Checks duration presence, meta name/path presence, and that JSONs are dicts.
    - Returns a report; does not mutate inputs (your real autofix can).
    """
    issues: List[str] = []

    if not isinstance(draft_content, dict):
        issues.append("draft_content is not an object")
    if not isinstance(draft_meta_info, dict):
        issues.append("draft_meta_info is not an object")
    if not isinstance(draft_virtual_store, dict):
        issues.append("draft_virtual_store is not an object")

    dur = draft_content.get("duration", 0)
    if not isinstance(dur, int):
        issues.append("draft_content.duration missing or not int (microseconds expected)")

    for k in ("draft_fold_path", "draft_name"):
        if k not in draft_meta_info:
            issues.append(f"draft_meta_info missing {k}")

    return {"strict": strict, "autofix": autofix, "issues": issues}
