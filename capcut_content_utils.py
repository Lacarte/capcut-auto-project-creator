"""
capcut_content_utils.py
-----------------------
Utilities to mimic CapCut's *timeline* mutations inside `draft_content.json`
when adding still images (1.jpg, 2.jpg, ...), as observed in your diffs.

Goals
-----
- Append a new *video* material representing the image on the timeline.
- Append a new *segment* in tracks[0] that references that video material.
- For each new segment, create a dedicated set of "aux" materials
  (speed, placeholder_info, canvas, sound_channel_mapping, material_color,
   vocal_separation) and wire them via `extra_material_refs`.
- Leave unrelated parts of the JSON untouched.

Notes
-----
- This module doesn't touch `draft_meta_info.json`. Use your meta utilities to
  update `tm_duration` and `tm_draft_modified` there.
- The exact internal schema can vary across CapCut versions; this utility preserves
  existing structure if present and fills in minimal, self-consistent defaults when absent.
- Width/height can be provided. If omitted, we try Pillow; else default to 0/0.

CLI Examples
------------
# Add a single image for 5s, automatically placed after existing segments
python capcut_content_utils.py --content path/to/draft_content.json --add-image "C:/path/1.jpg"

# Add a specific start and duration (in microseconds)
python capcut_content_utils.py --content path/to/draft_content.json --add-image "C:/path/2.jpg" --start-us 5000000 --duration-us 5000000

# Add a whole folder (sorted by name), each 5s, appended one after another
python capcut_content_utils.py --content path/to/draft_content.json --add-folder "C:/path/images" --duration-us 5000000
"""

from __future__ import annotations

import argparse
import json
import uuid
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# ---------- Helpers: time and dimensions ------------------------------------

def _now_ms_like() -> int:
    # CapCut uses long micro/milli style stamps elsewhere; here we just need a stable "now"
    return int(time.time() * 1_000_000)

def _get_image_size(img_path: Path) -> Optional[Tuple[int, int]]:
    try:
        from PIL import Image  # type: ignore
        with Image.open(img_path) as im:
            return im.width, im.height
    except Exception:
        return None

# ---------- Ensure structure -------------------------------------------------

def _ensure_materials(content: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    mats = content.setdefault("materials", {})
    def _ensure_list(key: str) -> List[Dict[str, Any]]:
        v = mats.get(key)
        if not isinstance(v, list):
            v = []
            mats[key] = v
        return v

    videos = _ensure_list("videos")
    canvases = _ensure_list("canvases")
    placeholder_infos = _ensure_list("placeholder_infos")
    sound_maps = _ensure_list("sound_channel_mappings")
    speeds = _ensure_list("speeds")
    material_colors = _ensure_list("material_colors")
    vocal_separations = _ensure_list("vocal_separations")

    return {
        "videos": videos,
        "canvases": canvases,
        "placeholder_infos": placeholder_infos,
        "sound_channel_mappings": sound_maps,
        "speeds": speeds,
        "material_colors": material_colors,
        "vocal_separations": vocal_separations,
        "transitions": _ensure_list("transitions"),
    }

def _ensure_tracks(content: Dict[str, Any]) -> List[Dict[str, Any]]:
    tracks = content.get("tracks")
    if not isinstance(tracks, list):
        tracks = []
        content["tracks"] = tracks
    # Ensure at least one main video track
    if not tracks:
        tracks.append({
            "id": str(uuid.uuid4()),
            "type": "video",
            "segments": []
        })
    # Ensure first track has segments list
    if "segments" not in tracks[0] or not isinstance(tracks[0]["segments"], list):
        tracks[0]["segments"] = []
    return tracks

# ---------- Builders ---------------------------------------------------------

def _build_video_material(path: Path, width: int, height: int) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "material_name": path.name,
        "path": str(path),
        "duration": 10_800_000_000,  # CapCut often stores a large internal duration; segment trims it
        "width": int(width),
        "height": int(height),
        "type": "video",          # CapCut treats stills as "video material" on the timeline
        "source_platform": "local"
    }

def _build_canvas() -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "type": "canvas_color",
        "color": "#000000",
    }

def _build_placeholder_info() -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "type": "placeholder_info",
        "text": ""
    }

def _build_sound_channel_mapping() -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "type": "sound_channel_mapping",
        "mapping": []
    }

def _build_speed() -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "type": "speed",
        "multiplier": 1.0
    }

def _build_material_color() -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "type": "material_color",
        "value": "#FFFFFF"
    }


def _build_transition(name: str = "Pull in", duration_us: int = 466_666, is_overlap: bool = False) -> Dict[str, Any]:
    """
    Build a minimal transition material entry.
    Note: CapCut stores many extra fields; we keep a compact structure that matches references.
    """
    return {
        "id": str(uuid.uuid4()),
        "type": "transition",
        "name": name,
        "duration": int(duration_us),
        "is_overlap": bool(is_overlap),
        # Optional descriptive fields (non-critical to structure)
        "category_name": "remen",
        "platform": "all"
    }
def _build_vocal_separation() -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "type": "vocal_separation",
        "enabled": False
    }

def _build_extra_refs(canvas_id: str,
                      placeholder_id: str,
                      sound_map_id: str,
                      speed_id: str,
                      color_id: str,
                      vocal_sep_id: str) -> Dict[str, Any]:
    return {
        "canvas": canvas_id,
        "placeholder_info": placeholder_id,
        "sound_channel_mapping": sound_map_id,
        "speed": speed_id,
        "material_color": color_id,
        "vocal_separation": vocal_sep_id
    }


def _ensure_transition_hook_on_previous_segment(segments: List[Dict[str, Any]], transition_id: str) -> None:
    """
    Attach the transition to the previous segment's extra_material_refs.
    In observed files, the transition id appears after [speed, placeholder_info] as the 3rd element.
    We will insert it at index 2 if not present; otherwise append.
    """
    if len(segments) < 2:
        return
    prev = segments[-2]
    refs = prev.get("extra_material_refs")
    if isinstance(refs, list):
        if transition_id not in refs:
            # try to insert as 3rd item for fidelity; else append
            if len(refs) >= 2:
                refs.insert(2, transition_id)
            else:
                refs.append(transition_id)
    elif isinstance(refs, dict):
        # If future schema changes to dict, store under a 'transition' key
        if "transition" not in refs:
            refs["transition"] = transition_id
def _build_segment(video_material_id: str,
                   start_us: int,
                   duration_us: int,
                   extra_refs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "material_id": video_material_id,
        "type": "video",
        "source_timerange": {"start": 0, "duration": int(duration_us)},
        "target_timerange": {"start": int(start_us), "duration": int(duration_us)},
        "extra_material_refs": extra_refs
    }

# ---------- Public API -------------------------------------------------------

def add_image_to_timeline(content: Dict[str, Any],
                          image_path: Path,
                          duration_us: int = 5_000_000,
                          start_us: Optional[int] = None,
                          width: Optional[int] = None,
                          height: Optional[int] = None,
                          add_transition_after_previous: bool = True,
                          transition_name: str = "Pull in",
                          transition_duration_us: int = 466_666,
                          transition_is_overlap: bool = False) -> None:
    """
    Add a still image to the timeline:
      - create video material (one per image)
      - create dedicated aux materials and refs
      - append a segment to tracks[0] at `start_us` (or auto-append if None)

    Mutates `content` in place.
    """
    mats = _ensure_materials(content)
    tracks = _ensure_tracks(content)
    segments = tracks[0]["segments"]

    # Determine start position (append after last segment if unspecified)
    if start_us is None:
        start_us = 0
        if segments:
            last = segments[-1]
            start_us = int(last["target_timerange"]["start"]) + int(last["target_timerange"]["duration"])

    # Determine dimensions
    image_path = image_path.resolve()
    if width is None or height is None:
        size = _get_image_size(image_path)
        if size:
            width, height = size
        else:
            width = width or 0
            height = height or 0

    # Build and register materials
    vid = _build_video_material(image_path, width, height)
    mats["videos"].append(vid)

    canvas = _build_canvas(); mats["canvases"].append(canvas)
    ph = _build_placeholder_info(); mats["placeholder_infos"].append(ph)
    sm = _build_sound_channel_mapping(); mats["sound_channel_mappings"].append(sm)
    sp = _build_speed(); mats["speeds"].append(sp)
    mc = _build_material_color(); mats["material_colors"].append(mc)
    vs = _build_vocal_separation(); mats["vocal_separations"].append(vs)

    extra_refs = _build_extra_refs(canvas["id"], ph["id"], sm["id"], sp["id"], mc["id"], vs["id"])

    # Build and append segment
    seg = _build_segment(vid["id"], start_us=start_us, duration_us=duration_us, extra_refs=extra_refs)
    segments.append(seg)

    # If requested and there is a previous segment, create a transition and attach it to the previous segment
    if add_transition_after_previous and len(segments) >= 2:
        mats = _ensure_materials(content)
        trans = _build_transition(transition_name, transition_duration_us, is_overlap=transition_is_overlap)
        # Register transition material
        mats["transitions"].append(trans)
        # Hook transition id into previous segment refs
        _ensure_transition_hook_on_previous_segment(segments, trans["id"])

    # Optional: update a top-level duration if present
    # Try to store/refresh an overall timeline length
    total = 0
    for s in segments:
        st = int(s["target_timerange"]["start"])
        du = int(s["target_timerange"]["duration"])
        total = max(total, st + du)
    content["duration"] = total
    content["modified_time_us"] = _now_ms_like()

def add_folder_to_timeline(content: Dict[str, Any],
                           folder: Path,
                           duration_us: int = 5_000_000,
                           pattern_extensions=(".jpg", ".jpeg", ".png", ".bmp", ".webp"),
                           add_transitions: bool = True,
                           transition_name: str = "Pull in",
                           transition_duration_us: int = 466_666,
                           transition_is_overlap: bool = False) -> int:
    """
    Append all images in `folder` to the timeline, sorted by filename.
    Returns the count of images added.
    """
    folder = folder.resolve()
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in pattern_extensions]
    files.sort(key=lambda p: p.name)

    # Determine the starting offset = end of current timeline
    tracks = _ensure_tracks(content)
    segments = tracks[0]["segments"]
    start_us = 0
    if segments:
        last = segments[-1]
        start_us = int(last["target_timerange"]["start"]) + int(last["target_timerange"]["duration"])

    count = 0
    for f in files:
        add_image_to_timeline(content, f, duration_us=duration_us, start_us=start_us,
                           add_transition_after_previous=add_transitions,
                           transition_name=transition_name,
                           transition_duration_us=transition_duration_us,
                           transition_is_overlap=transition_is_overlap)
        start_us += int(duration_us)
        count += 1
    return count

# ---------- I/O -------------------------------------------------------------

def load_content(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_content(content: Dict[str, Any], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(content, f, indent=2, ensure_ascii=False)

# ---------- CLI -------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Mimic CapCut timeline changes in draft_content.json")
    ap.add_argument("--content", required=True, help="Path to draft_content.json")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--add-image", help="Path to a single image to add to timeline")
    g.add_argument("--add-folder", help="Path to a folder of images (sorted by name)")
    ap.add_argument("--duration-us", type=int, default=5_000_000, help="Per-image duration on timeline (default 5,000,000)")
    ap.add_argument("--no-transitions", action="store_true", help="Do not add transitions between adjacent segments")
    ap.add_argument("--transition-name", default="Pull in", help="Transition display name (default: Pull in)")
    ap.add_argument("--transition-duration-us", type=int, default=466_666, help="Transition duration in microseconds (default ~0.466s)")
    ap.add_argument("--transition-overlap", action="store_true", help="Mark transition as overlap (default: false)")
    ap.add_argument("--start-us", type=int, help="Start time for the image (if --add-image); default appends to the end")
    ap.add_argument("--width", type=int, help="Image width override")
    ap.add_argument("--height", type=int, help="Image height override")
    return ap.parse_args()

def main() -> int:
    args = _parse_args()
    content_path = Path(args.content).resolve()
    if not content_path.exists():
        print(f"[ERROR] draft_content.json not found: {content_path}")
        return 2

    try:
        content = load_content(content_path)

        if args.add_image:
            add_image_to_timeline(
                content,
                Path(args.add_image),
                duration_us=args.duration_us,
                start_us=args.start_us,
                width=args.width,
                height=args.height,
                add_transition_after_previous=(not args.no_transitions),
                transition_name=args.transition_name,
                transition_duration_us=args.transition_duration_us,
                transition_is_overlap=args.transition_overlap
            )
            save_content(content, content_path)
            print(f"[OK] Added 1 image to timeline -> {content_path}")

        elif args.add_folder:
            count = add_folder_to_timeline(
                content,
                Path(args.add_folder),
                duration_us=args.duration_us,
                add_transitions=(not args.no_transitions),
                transition_name=args.transition_name,
                transition_duration_us=args.transition_duration_us,
                transition_is_overlap=args.transition_overlap
            )
            save_content(content, content_path)
            print(f"[OK] Added {count} image(s) to timeline -> {content_path}")

        return 0
    except Exception as e:
        print(f"[ERROR] {e}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
