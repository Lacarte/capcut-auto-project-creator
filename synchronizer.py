# synchronizer.py
from __future__ import annotations
from typing import Dict, Any, Optional
from pathlib import Path

def sync_all(
    draft_content: Dict[str, Any],
    draft_meta_info: Dict[str, Any],
    draft_virtual_store: Dict[str, Any],
    ops: Dict[str, Any],
    project_name: str,
    project_dir: Optional[str],
    force_meta_name: bool = True,
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """
    - Mirrors total duration from draft_content into meta (tm_duration).
    - Updates draft_fold_path and draft_name so that only the last folder
      of draft_fold_path is replaced with project_name.
    """

    dmi = dict(draft_meta_info)

    # sync duration
    duration_us = int(draft_content.get("duration", 0))
    dmi.setdefault("tm_duration", duration_us)
    dmi["tm_duration"] = duration_us

    if force_meta_name:
        # --- draft_name ---
        dmi["draft_name"] = project_name

        # --- draft_fold_path ---
        old_path = dmi.get("draft_fold_path")
        if old_path:
            p = Path(old_path)
            # replace only the last folder with project_name
            parent = p.parent
            new_path = str(parent / project_name)
            dmi["draft_fold_path"] = new_path
        else:
            # fallback: if missing, just set to project_dir or project_name
            if project_dir:
                dmi["draft_fold_path"] = str(Path(project_dir))
            else:
                dmi["draft_fold_path"] = project_name

    return draft_content, dmi, draft_virtual_store
