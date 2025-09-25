# synchronizer.py
from __future__ import annotations
from typing import Dict, Any, Optional, Tuple
import re


def _replace_last_component(path_str: str, new_name: str) -> str:
    """Replace only the last folder in a path string, preserving separator style.

    Works with Windows (\\) and POSIX (/) paths, without normalizing or changing
    the drive/root. If the input is empty or has a single component, returns
    `new_name`.
    """
    if not path_str:
        return new_name

    # Split by both separators without losing drive letters like "C:".
    parts = re.split(r"[\\/]", path_str)
    if not parts:
        return new_name

    parts[-1] = new_name

    # Choose the dominant original separator so we preserve style.
    sep = "\\" if ("\\" in path_str and path_str.count("\\") >= path_str.count("/")) else "/"

    # Preserve a leading separator for absolute POSIX-like paths.
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
    """Synchronize project identity across JSONs.

    Responsibilities
    ----------------
    1) Ensure `draft_meta_info["draft_name"]` matches `project_name` (unless
       `force_meta_name=False` and a name already exists).
    2) Update `draft_meta_info["draft_fold_path"]` by replacing only the LAST
       folder in the path with `project_name`. If the key is missing/empty, use
       `project_dir` if provided, otherwise just `project_name`.
    3) Return the (possibly) updated JSON dicts unchanged otherwise.

    Notes
    -----
    • We *do not* alter other identity fields unless explicitly required.
    • We avoid Path() normalization to preserve original Windows/Posix style.
    • This function keeps behavior idempotent: calling multiple times with the
      same `project_name` is safe.
    """

    dmi = draft_meta_info or {}

    # (1) Sync human-visible draft name
    if force_meta_name or not dmi.get("draft_name"):
        dmi["draft_name"] = project_name

    # (2) Rewrite only the last folder of draft_fold_path
    old_path = dmi.get("draft_fold_path")
    if old_path:
        dmi["draft_fold_path"] = _replace_last_component(old_path, project_name)
    else:
        # Fallbacks when key/value is missing
        if project_dir:
            # If a full output directory is known, use it as-is
            dmi["draft_fold_path"] = str(project_dir)
        else:
            # Otherwise store just the name (CapCut will resolve the parent)
            dmi["draft_fold_path"] = project_name

    return draft_content, dmi, draft_virtual_store
