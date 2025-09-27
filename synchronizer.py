# synchronizer.py
from __future__ import annotations
from typing import Dict, Any, Optional, Tuple
import re


def _replace_last_component(path_str: str, new_name: str) -> str:
    """
    Replace only the last folder in a path string, preserving the original
    separator style (Windows vs POSIX) and not normalizing the drive/root.

    If the input is empty or has a single component, returns `new_name`.
    """
    if not path_str:
        return new_name

    parts = re.split(r"[\\/]", path_str)
    if not parts:
        return new_name

    parts[-1] = new_name
    # Keep the dominant original separator
    sep = "\\" if (path_str.count("\\") >= path_str.count("/")) else "/"

    # Preserve absolute-leading slash/backslash
    if path_str.startswith(("/", "\\")):
        return sep + sep.join(p for p in parts if p != "")

    return sep.join(parts)


def sync_all(
    draft_content: Dict[str, Any],
    draft_meta_info: Dict[str, Any],
    draft_virtual_store: Dict[str, Any],
    ops: Dict[str, Any],
    project_name: str,
    project_dir: Optional[str],
    force_meta_name: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """
    Synchronize identity & timing across JSONs in a template-driven way.

    - Mirror draft_content.duration  -> draft_meta_info.tm_duration (μs).
    - Ensure draft_meta_info.draft_name == project_name (when forced or empty).
    - Rewrite only the LAST folder of draft_meta_info.draft_fold_path with project_name.
      If missing, fall back to provided project_dir or project_name.
    - Best-effort reflect project name/path into draft_content minimal fields (if present).
    """
    dc = draft_content or {}
    dmi = dict(draft_meta_info or {})  # shallow copy
    dvs = draft_virtual_store or {}

    # (1) Mirror duration (μs) from content to meta
    duration_us = 0
    try:
        duration_us = int(dc.get("duration", 0) or 0)
    except Exception:
        duration_us = 0
    dmi["tm_duration"] = duration_us

    # (2) Name stamping
    if force_meta_name or not dmi.get("draft_name"):
        dmi["draft_name"] = project_name

    # (3) Folder path rewrite (only last component)
    old_path = dmi.get("draft_fold_path")
    if old_path:
        dmi["draft_fold_path"] = _replace_last_component(str(old_path), project_name)
    else:
        dmi["draft_fold_path"] = str(project_dir) if project_dir else project_name

    # (4) Best-effort reflect basic identity into draft_content (non-invasive)
    try:
        if "name" in dc:
            dc["name"] = project_name
        if "path" in dc and project_dir:
            dc["path"] = project_dir
    except Exception:
        pass

    return dc, dmi, dvs
