"""
capcut_virtual_store_utils.py
-----------------------------
Utilities to mimic CapCut's creation/update pattern for `draft_virtual_store.json`
after importing the first image (and subsequent images).

Observed from real snapshots:
- `draft_virtual_store` is a list of typed buckets.
  * type=0: contains a single metadata-like object with empty/zero fields (id "", times 0).
  * type=1: contains a list of {"child_id": <material_id>, "parent_id": ""} entries,
            one per material id present in draft_meta_info.json (including placeholder "none" and real "photo").
  * type=2: empty list.
- `draft_materials` key exists at top level and is an empty list in the snapshots.

This module can:
- Build a new `draft_virtual_store.json` given a list of material IDs.
- Sync a `draft_virtual_store.json` from a `draft_meta_info.json` by reading material ids
  from `draft_materials` where entry.type==0 (images).

CLI examples:
  # Build from draft_meta_info.json
  python capcut_virtual_store_utils.py --from-draft-meta path/to/draft_meta_info.json --out path/to/draft_virtual_store.json

  # Build from explicit ids
  python capcut_virtual_store_utils.py --material-ids UUID1 UUID2 --out path/to/draft_virtual_store.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Dict, Any

# ---------------- Core builders ----------------

def build_virtual_store(material_ids: List[str]) -> Dict[str, Any]:
    """
    Build a dict representing draft_virtual_store.json that mirrors the observed pattern.
    """
    # type=0 bucket with one empty-entry object
    type0_value = [{
        "creation_time": 0,
        "display_name": "",
        "filter_type": 0,
        "id": "",
        "import_time": 0,
        "import_time_us": 0,
        "sort_sub_type": 0,
        "sort_type": 0
    }]

    # type=1 bucket linking to material ids
    type1_value = [{"child_id": mid, "parent_id": ""} for mid in material_ids]

    # type=2 empty bucket
    type2_value: List[dict] = []

    return {
        "draft_materials": [],
        "draft_virtual_store": [
            {"type": 0, "value": type0_value},
            {"type": 1, "value": type1_value},
            {"type": 2, "value": type2_value},
        ]
    }

def extract_image_material_ids_from_meta(draft_meta: Dict[str, Any]) -> List[str]:
    """
    From draft_meta_info.json content, extract all ids for materials where entry.type==0.
    Preserves order (including placeholder first if present).
    """
    ids: List[str] = []
    materials = draft_meta.get("draft_materials", [])
    for bucket in materials:
        if isinstance(bucket, dict) and bucket.get("type") == 0:
            for item in bucket.get("value", []):
                mid = item.get("id")
                if isinstance(mid, str) and mid:
                    ids.append(mid)
    return ids

# ---------------- I/O helpers ----------------

def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_json(data: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ---------------- CLI ----------------

def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Build/Sync CapCut draft_virtual_store.json from draft_meta_info.json or explicit IDs")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--from-draft-meta", help="Path to draft_meta_info.json (will extract type=0 material ids)")
    g.add_argument("--material-ids", nargs="+", help="Explicit list of material UUIDs to link in type=1")
    ap.add_argument("--out", required=True, help="Where to write draft_virtual_store.json")
    return ap.parse_args()

def main() -> int:
    args = _parse_args()
    try:
        if args.from_draft_meta:
            draft_meta = load_json(Path(args.from_draft_meta))
            ids = extract_image_material_ids_from_meta(draft_meta)
        else:
            ids = list(args.material_ids)

        store = build_virtual_store(ids)
        save_json(store, Path(args.out))
        print(f"[OK] Wrote virtual store with {len(ids)} link(s) -> {args.out}")
        return 0
    except Exception as e:
        print(f"[ERROR] {e}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
