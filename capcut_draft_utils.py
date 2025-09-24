"""
capcut_draft_utils.py
---------------------
Utilities to mimic CapCut's JSON mutation pattern when adding the *first image*
(and subsequent ones) into `draft_meta_info.json`.

Observed behavior (from real project snapshots):
- For the first import, CapCut may prepend a tiny placeholder item (metetype="none")
  before the real image item.
- A real photo item is then appended with fields like id, metetype="photo", file_Path,
  width, height, duration (often 5_000_000 microseconds for 5s), timestamps, etc.
- tm_draft_modified is updated to a microsecond-like integer timestamp.

This module reproduces that pattern faithfully by default.

CLI examples
------------
Add one image (with placeholder):
    python capcut_draft_utils.py --draft path/to/draft_meta_info.json --add-image C:/path/1.jpg

Add a whole folder (sequential order by filename, with placeholder before the first image only):
    python capcut_draft_utils.py --draft path/to/draft_meta_info.json --add-folder C:/path/images

Disable placeholder (still updates tm_draft_modified):
    python capcut_draft_utils.py --draft path/to/draft_meta_info.json --add-image C:/path/1.jpg --no-placeholder
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Optional, Tuple, List

# --------- Optional Pillow import for width/height detection -----------------
def _get_image_size(img_path: Path) -> Optional[Tuple[int, int]]:
    """
    Try to get image dimensions using Pillow if available.
    Returns (width, height) or None if not available/couldn't read.
    """
    try:
        from PIL import Image  # type: ignore
        with Image.open(img_path) as im:
            return im.width, im.height
    except Exception:
        return None

# --------- Core JSON helpers -------------------------------------------------
def _now_seconds() -> int:
    # Integer seconds timestamp, similar to CapCut's `create_time` / `import_time`
    return int(time.time())

def _now_micro_like() -> int:
    # Microsecond-like integer (CapCut uses long ints like 1758642046679052).
    return int(time.time() * 1_000_000)

def _ensure_materials_slot(draft: dict, mat_type: int = 0) -> list:
    """
    Find or create the materials array for a given type (0 = images/photos).
    Returns the list reference for that type's `value`.
    """
    mats = draft.get("draft_materials")
    if not isinstance(mats, list):
        mats = []
        draft["draft_materials"] = mats

    # find entry whose {"type": mat_type}
    for entry in mats:
        if isinstance(entry, dict) and entry.get("type") == mat_type:
            if not isinstance(entry.get("value"), list):
                entry["value"] = []
            return entry["value"]

    # not found -> create
    new_entry = {"type": mat_type, "value": []}
    mats.append(new_entry)
    return new_entry["value"]

def _create_placeholder_item(now_s: int, now_us: int) -> dict:
    """
    Create the tiny 'none' placeholder item CapCut sometimes prepends before the first real photo.
    """
    return {
        "ai_group_type": "",
        "create_time": now_s,
        "duration": 33333,
        "extra_info": "",
        "file_Path": "",
        "height": 0,
        "id": str(uuid.uuid4()),
        "import_time": now_s,
        "import_time_ms": now_us,
        "item_source": 1,
        "md5": "",
        "metetype": "none",
        "roughcut_time_range": {"duration": 33333, "start": 0},
        "sub_time_range": {"duration": -1, "start": -1},
        "type": 0,
        "width": 0
    }

def _create_photo_item(img_path: Path,
                       width: int,
                       height: int,
                       duration_us: int,
                       now_s: int,
                       now_us: int) -> dict:
    """
    Create a real 'photo' item mirroring CapCut's fields.
    """
    return {
        "ai_group_type": "",
        "create_time": now_s,
        "duration": int(duration_us),
        "extra_info": img_path.name,
        "file_Path": str(img_path),
        "height": int(height),
        "id": str(uuid.uuid4()),
        "import_time": now_s,
        "import_time_ms": now_us,
        "item_source": 1,
        "md5": "",
        "metetype": "photo",
        "roughcut_time_range": {"duration": -1, "start": -1},
        "sub_time_range": {"duration": -1, "start": -1},
        "type": 0,
        "width": int(width)
    }

def add_image_to_draft(draft: dict,
                       image_path: Path,
                       duration_us: int = 5_000_000,
                       include_placeholder_if_first: bool = True,
                       width: Optional[int] = None,
                       height: Optional[int] = None) -> None:
    """
    Append a single image to the draft's materials (type=0).

    - Detects width/height via Pillow if not provided; falls back to 0/0.
    - Adds the tiny placeholder if this is the very first image AND include_placeholder_if_first=True.
    - Updates tm_draft_modified (microsecond-like integer).
    """
    image_path = image_path.resolve()
    mats = _ensure_materials_slot(draft, mat_type=0)

    # Include placeholder only if there are currently no items of type=0
    if include_placeholder_if_first and len(mats) == 0:
        now_s = _now_seconds()
        now_us = _now_micro_like()
        mats.append(_create_placeholder_item(now_s, now_us))

    # Determine size
    if width is None or height is None:
        size = _get_image_size(image_path)
        if size is not None:
            width, height = size
        else:
            width = width or 0
            height = height or 0

    # Real photo item
    now_s = _now_seconds()
    now_us = _now_micro_like()
    mats.append(_create_photo_item(image_path, width, height, duration_us, now_s, now_us))

    # Update tm_draft_modified
    draft["tm_draft_modified"] = _now_micro_like()

def add_folder_to_draft(draft: dict,
                        folder: Path,
                        duration_us: int = 5_000_000,
                        include_placeholder_before_first: bool = True,
                        pattern_extensions: Tuple[str, ...] = (".jpg", ".jpeg", ".png", ".bmp", ".webp")) -> int:
    """
    Append every image in the folder (sorted by name) to the draft.
    Returns how many images were added.
    """
    folder = folder.resolve()
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in pattern_extensions]
    files.sort(key=lambda p: p.name)

    added = 0
    for idx, img in enumerate(files):
        add_image_to_draft(
            draft,
            img,
            duration_us=duration_us,
            include_placeholder_if_first=(include_placeholder_before_first and idx == 0)
        )
        added += 1
    return added

# --------- Load / Save ------------------------------------------------------
def load_draft(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_draft(draft: dict, path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(draft, f, indent=2, ensure_ascii=False)

# --------- CLI --------------------------------------------------------------
def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Mimic CapCut image import pattern on draft_meta_info.json")
    ap.add_argument("--draft", required=True, help="Path to draft_meta_info.json")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--add-image", help="Add a single image file")
    g.add_argument("--add-folder", help="Add all images from a folder (sorted by name)")
    ap.add_argument("--duration-us", type=int, default=5_000_000, help="Per-image duration in microseconds (default: 5_000_000)")
    ap.add_argument("--no-placeholder", action="store_true", help="Do not insert the tiny placeholder before the first image")
    return ap.parse_args()

def main() -> int:
    args = _parse_args()
    draft_path = Path(args.draft).resolve()
    if not draft_path.exists():
        print(f"[ERROR] Draft file not found: {draft_path}", file=sys.stderr)
        return 2

    try:
        draft = load_draft(draft_path)

        if args.add_image:
            img = Path(args.add_image)
            add_image_to_draft(
                draft,
                img,
                duration_us=args.duration_us,
                include_placeholder_if_first=not args.no_placeholder
            )
            save_draft(draft, draft_path)
            print(f"[OK] Added image: {img}")

        elif args.add_folder:
            folder = Path(args.add_folder)
            count = add_folder_to_draft(
                draft,
                folder,
                duration_us=args.duration_us,
                include_placeholder_before_first=not args.no_placeholder
            )
            save_draft(draft, draft_path)
            print(f"[OK] Added {count} image(s) from folder: {folder}")

        # Show where the draft now lives
        print(f"[OK] Updated: {draft_path}")
        return 0
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
