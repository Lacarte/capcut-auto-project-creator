# jsonfiller.py - CapCut‑compatible fillers (imports → materials → segments → transitions)
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import json
import subprocess
import logging
import uuid
import random

log = logging.getLogger(__name__)

# Prefer local repo lib/ffprobe.exe; fallback to PATH "ffprobe"
FFPROBE_PATH = Path(__file__).resolve().parent / "lib" / "ffprobe.exe"

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".m4v", ".avi", ".webm", ".3gp", ".mts", ".m2ts"}
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac"}
IMG_EXT   = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

# ----------------------------
# Small utils
# ----------------------------

def _uuid_lower() -> str: return str(uuid.uuid4()).lower()

def _uuid_upper() -> str: return str(uuid.uuid4()).upper()

def _abs(p: str | Path) -> str: return str(Path(p).expanduser().resolve())

def _fname(p: str | Path) -> str: return Path(p).name

def _is_video(path: str | Path) -> bool: return Path(path).suffix.lower() in VIDEO_EXT

def _is_audio(path: str | Path) -> bool: return Path(path).suffix.lower() in AUDIO_EXT

def _is_image(path: str | Path) -> bool: return Path(path).suffix.lower() in IMG_EXT


# ----------------------------
# Probing helpers
# ----------------------------

def _ffprobe(cmd_args: List[str]) -> Optional[dict]:
    try:
        exe = str(FFPROBE_PATH) if FFPROBE_PATH.exists() else "ffprobe"
        out = subprocess.check_output([exe, *cmd_args])
        return json.loads(out.decode("utf-8"))
    except Exception as e:
        log.debug("ffprobe error: %s", e)
        return None


def _probe_video_meta(path: str) -> Tuple[int, int, int]:
    """Return (width, height, duration_us). Falls back to (1920,1080,5s)."""
    info = _ffprobe([
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration",
        "-of", "json", path,
    ])
    w, h, dur_us = 1920, 1080, 5_000_000
    if info and info.get("streams"):
        st = info["streams"][0]
        try: w = int(st.get("width") or w)
        except Exception: pass
        try: h = int(st.get("height") or h)
        except Exception: pass
        try:
            if st.get("duration") is not None:
                dur_us = int(float(st["duration"]) * 1_000_000)
        except Exception:
            pass
    return w, h, dur_us


def _get_audio_duration_us(path: str) -> Optional[int]:
    info = _ffprobe([
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json", path,
    ])
    try:
        if info and info.get("format") and info["format"].get("duration") is not None:
            return int(float(info["format"]["duration"]) * 1_000_000)
    except Exception:
        pass
    return None


def _get_img_size(path: str) -> Tuple[int, int]:
    # Try Pillow if available; otherwise fallback to 1920x1080
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.width, im.height
    except Exception:
        return 1920, 1080


# ----------------------------
# JSON scaffolding helpers
# ----------------------------

def _find_or_create_meta_bucket(dmi: Dict[str, Any], *, type_id: int) -> List[dict]:
    buckets = dmi.setdefault("draft_materials", [])
    bucket = next((b for b in buckets if b.get("type") == type_id), None)
    if bucket is None:
        bucket = {"type": type_id, "value": []}
        buckets.append(bucket)
    bucket.setdefault("value", [])
    return bucket["value"]


def _find_or_create_vstore_bucket(dvs: Dict[str, Any], *, type_id: int) -> List[dict]:
    buckets = dvs.setdefault("draft_virtual_store", [])
    bucket = next((b for b in buckets if b.get("type") == type_id), None)
    if bucket is None:
        bucket = {"type": type_id, "value": []}
        buckets.append(bucket)
    bucket.setdefault("value", [])
    return bucket["value"]


def _ensure_content_scaffolding(dc: Dict[str, Any]) -> Dict[str, Any]:
    mats = dc.setdefault("materials", {})
    mats.setdefault("videos", [])
    mats.setdefault("audios", [])
    mats.setdefault("transitions", [])
    mats.setdefault("speeds", [])
    mats.setdefault("placeholder_infos", [])
    mats.setdefault("sound_channel_mappings", [])
    dc.setdefault("tracks", [])
    return dc


def _create_accessory_materials(dc: Dict[str, Any], num_segments: int) -> Tuple[List[str], List[str], List[str]]:
    """Create speed, placeholder_info, and sound_channel_mapping materials for each segment."""
    speeds = dc["materials"]["speeds"]
    placeholder_infos = dc["materials"]["placeholder_infos"]
    sound_mappings = dc["materials"]["sound_channel_mappings"]
    
    speed_ids: List[str] = []
    placeholder_ids: List[str] = []
    sound_mapping_ids: List[str] = []
    
    for _ in range(num_segments):
        # Speed material (1.0x speed)
        speed_id = _uuid_upper()
        speeds.append({
            "curve_speed": None,
            "id": speed_id,
            "mode": 0,
            "speed": 1.0,
            "type": "speed"
        })
        speed_ids.append(speed_id)
        
        # Placeholder info
        placeholder_id = _uuid_upper()
        placeholder_infos.append({
            "error_path": "",
            "error_text": "",
            "id": placeholder_id,
            "meta_type": "none",
            "res_path": "",
            "res_text": "",
            "type": "placeholder_info"
        })
        placeholder_ids.append(placeholder_id)
        
        # Sound channel mapping
        sound_id = _uuid_upper()
        sound_mappings.append({
            "audio_channel_mapping": 0,
            "id": sound_id,
            "is_config_open": False,
            "type": ""
        })
        sound_mapping_ids.append(sound_id)
    
    return speed_ids, placeholder_ids, sound_mapping_ids


def _resolve_transition_cache_path(cache_root: str, effect_id: str) -> str:
    """Try to find the cached transition effect path."""
    if not cache_root or not effect_id:
        return ""
    
    cache_path = Path(cache_root) / effect_id
    if cache_path.exists():
        # Find the actual effect file in the cache directory
        for item in cache_path.iterdir():
            if item.is_file() and not item.name.startswith('.'):
                return str(cache_path / item.name)
        return str(cache_path)
    return ""


# ----------------------------
# PUBLIC API
# ----------------------------

def add_imports(
    draft_meta_info: Dict[str, Any],
    draft_virtual_store: Dict[str, Any],
    images: List[str],
    sounds: List[str],
    id_strategy: str = "mirror",
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Register media in meta & virtual_store using CapCut-compliant keys.

    Returns (draft_meta_info, draft_virtual_store, idmaps)
    where idmaps = {"images":[{"path","import_id"}], "audios":[...]}.
    """
    dmi = dict(draft_meta_info)
    dvs = dict(draft_virtual_store)

    meta_items = _find_or_create_meta_bucket(dmi, type_id=0)
    vstore_children = _find_or_create_vstore_bucket(dvs, type_id=1)

    idmaps: Dict[str, Any] = {"images": [], "audios": []}

    # Images list may contain both photos and videos
    for img in images:
        path = _abs(img)
        import_id = _uuid_lower()
        if _is_video(path):
            w, h, dur_us = _probe_video_meta(path)
            payload = {
                "id": import_id,
                "path": path,
                "file_name": _fname(path),
                "file_Path": path,            # <- add legacy mirror
                "material_name": _fname(path),
                "width": w,
                "height": h,
                "duration": dur_us,
                "category_name": "local",
                "source_platform": 0,
            }
        else:
            w, h = _get_img_size(path)
            payload = {
                "id": import_id,
                "path": path,
                "file_name": _fname(path),
                "file_Path": path,            # <- add legacy mirror
                "material_name": _fname(path),
                "width": w,
                "height": h,
                "category_name": "local",
                "source_platform": 0,
            }
        meta_items.append(payload)
        vstore_children.append({"child_id": import_id})
        idmaps["images"].append({"path": path, "import_id": import_id})

    # Single audio support (extend as needed)
    if sounds:
        apath = _abs(sounds[0])
        dur_us = _get_audio_duration_us(apath) or 0
        aud_imp_id = _uuid_lower()
        meta_items.append({
            "id": aud_imp_id,
            "path": apath,
            "file_name": _fname(apath),
            "file_Path": apath,             # <- legacy mirror
            "material_name": _fname(apath),
            "duration": dur_us,
            "category_name": "local",
            "source_platform": 0,
        })
        vstore_children.append({"child_id": aud_imp_id})
        idmaps["audios"].append({"path": apath, "import_id": aud_imp_id})

    return dmi, dvs, idmaps


def build_timeline(
    draft_content: Dict[str, Any],
    images: List[str],
    sounds: List[str],
    default_image_duration_ms: int,
    ordering: str = "numeric",
    idmaps: Optional[Dict[str, Any]] = None,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Create materials & segments on tracks, wiring local_material_id correctly."""
    dc = _ensure_content_scaffolding(dict(draft_content))

    videos = dc["materials"]["videos"]
    audios = dc["materials"]["audios"]

    vtrack = next((t for t in dc["tracks"] if t.get("type") == "video"), None)
    if vtrack is None:
        vtrack = {"id": _uuid_upper(), "type": "video", "segments": []}  # ensure track id
        dc["tracks"].append(vtrack)
    segments = vtrack["segments"]

    # Map path -> import id produced by add_imports
    imp_map: Dict[str, str] = {}
    if idmaps:
        for rec in idmaps.get("images", []):
            imp_map[rec["path"]] = rec["import_id"]
        for rec in idmaps.get("audios", []):
            imp_map[rec["path"]] = rec["import_id"]

    # Create accessory materials for all segments
    speed_ids, placeholder_ids, sound_mapping_ids = _create_accessory_materials(dc, len(images))

    # Natural numeric ordering already handled by caller; we keep input order
    t_cursor = 0
    cache = {"clips": [], "audio": []}

    for i, p in enumerate(images):
        path = _abs(p)
        local_id = imp_map.get(path)
        if _is_video(path):
            w, h, dur_us = _probe_video_meta(path)
            mat_id = _uuid_upper()
            videos.append({
                "id": mat_id,
                "local_material_id": local_id,   # keep this
                "type": "video",                 # <-- add this line
                "path": path,
                "width": w,
                "height": h,
                "duration": dur_us,
                "category_name": "local",
                "source_platform": 0,
            })

            seg_id = _uuid_upper()
            segments.append({
                "id": seg_id,
                "material_id": mat_id,
                "target_timerange": {"start": t_cursor, "duration": dur_us},
                "source_timerange": {"start": 0, "duration": dur_us},
                "extra_material_refs": [
                    speed_ids[i],
                    placeholder_ids[i],
                    sound_mapping_ids[i]
                ],
                "common_keyframes": [],
                "clip": {"scale": {"x": 1.0, "y": 1.0}, "uniform_scale": {"on": True}},
            })
            cache["clips"].append({"material_id": mat_id, "path": path, "start_us": t_cursor, "dur_us": dur_us})
            t_cursor += dur_us
        else:
            w, h = _get_img_size(path)
            dur_us = int(default_image_duration_ms) * 1000
            mat_id = _uuid_upper()
            videos.append({  # Store photos in videos[] with type="photo" for compatibility
                "id": mat_id,
                "local_material_id": local_id,
                "type": "photo",
                "path": path,
                "width": w,
                "height": h,
                "duration": dur_us,
                "category_name": "local",
                "source_platform": 0,
            })
            seg_id = _uuid_upper()
            segments.append({
                "id": seg_id,
                "material_id": mat_id,
                "target_timerange": {"start": t_cursor, "duration": dur_us},
                "source_timerange": {"start": 0, "duration": dur_us},
                "extra_material_refs": [
                    speed_ids[i],
                    placeholder_ids[i],
                    sound_mapping_ids[i]
                ],
                "common_keyframes": [],
                "clip": {"scale": {"x": 1.0, "y": 1.0}, "uniform_scale": {"on": True}},
            })
            cache["clips"].append({"material_id": mat_id, "path": path, "start_us": t_cursor, "dur_us": dur_us})
            t_cursor += dur_us

    video_duration = t_cursor
    
    # Handle audio track - create accessory materials for audio segments too
    audio_duration = 0
    if sounds:
        apath = _abs(sounds[0])
        aud_imp = imp_map.get(apath)
        dur_us = _get_audio_duration_us(apath)
        
        if dur_us is None or dur_us == 0:
            log.warning("Could not determine audio duration for %s, using video duration", apath)
            dur_us = video_duration
        
        audio_duration = dur_us
        am_id = _uuid_upper()
        audios.append({
            "id": am_id,
            "local_material_id": aud_imp,
            "path": apath,
            "type": "extract_music",         # <-- add
            "name": _fname(apath),           # <-- add
            "duration": dur_us,
        })
        
        atrack = next((t for t in dc["tracks"] if t.get("type") == "audio"), None)
        if atrack is None:
            atrack = {"id": _uuid_upper(), "type": "audio", "segments": []}  # ensure track id
            dc["tracks"].append(atrack)
        
        # Create accessory materials for the audio segment
        audio_speed_id = _uuid_upper()
        dc["materials"]["speeds"].append({
            "curve_speed": None,
            "id": audio_speed_id,
            "mode": 0,
            "speed": 1.0,
            "type": "speed"
        })
        
        audio_placeholder_id = _uuid_upper()
        dc["materials"]["placeholder_infos"].append({
            "error_path": "",
            "error_text": "",
            "id": audio_placeholder_id,
            "meta_type": "none",
            "res_path": "",
            "res_text": "",
            "type": "placeholder_info"
        })
        
        audio_sound_id = _uuid_upper()
        dc["materials"]["sound_channel_mappings"].append({
            "audio_channel_mapping": 0,
            "id": audio_sound_id,
            "is_config_open": False,
            "type": ""
        })
        
        seg_id = _uuid_upper()
        atrack["segments"].append({
            "id": seg_id,
            "material_id": am_id,
            "target_timerange": {"start": 0, "duration": dur_us},
            "source_timerange": {"start": 0, "duration": dur_us},
            "extra_material_refs": [
                audio_speed_id,
                audio_placeholder_id,
                audio_sound_id
            ]
        })
        cache["audio"].append({"material_id": am_id, "path": apath, "start_us": 0, "dur_us": dur_us})
    
    # Set project duration to max of video and audio
    dc["duration"] = max(video_duration, audio_duration)

    return dc, cache

def apply_transitions(
    draft_content: Dict[str, Any],
    timeline: Dict[str, Any],
    names: List[str],
    per_cut_probability: float,
    duration_ms_range: tuple[int, int],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    dc = _ensure_content_scaffolding(dict(draft_content))

    # Find video track with at least two segments
    vtrack = next((t for t in dc.get("tracks", []) if t.get("type") == "video"), None)
    if not vtrack:
        log.info("[transitions] no video track; skipping")
        return dc, timeline
    segs = vtrack.get("segments", [])
    if len(segs) < 2:
        log.info("[transitions] <2 segments; skipping")
        return dc, timeline

    # Catalog/cache path injected by initializer
    catalog = (timeline or {}).get("catalog") or []
    cache_root = (timeline or {}).get("cache_root")
    if not catalog:
        log.info("[transitions] empty catalog; skipping")
        return dc, timeline

    # Optional allow-list; if it empties out, fall back to full catalog
    if names:
        wanted = set(names)
        filtered = [c for c in catalog if c.get("name") in wanted]
        if filtered:
            catalog = filtered

    # Probability & duration guard rails
    p = max(0.0, min(1.0, float(per_cut_probability)))
    try:
        dmin, dmax = int(duration_ms_range[0]), int(duration_ms_range[1])
    except Exception:
        dmin, dmax = 600, 800
    if dmin > dmax:
        dmin, dmax = dmax, dmin

    transitions = dc["materials"].setdefault("transitions", [])
    added = 0

    for i in range(len(segs) - 1):
        if random.random() > p:
            continue

        spec = random.choice(catalog)
        # compute a safe duration that fits both clips; ≥200ms
        want_us = random.randint(dmin, dmax) * 1000
        prev_us = int(segs[i].get("target_timerange", {}).get("duration", 0) or 0)
        next_us = int(segs[i+1].get("target_timerange", {}).get("duration", 0) or 0)
        dur_us  = max(200_000, min(want_us, prev_us or want_us, next_us or want_us))

        effect_id = str(spec.get("effect_id") or spec.get("resource_id") or "")
        path = _resolve_transition_cache_path(cache_root, effect_id) if effect_id else ""

        tid = _uuid_upper()
        transitions.append({
            "id": tid,
            "name": spec.get("name", "Transition"),
            "duration": dur_us,
            "is_overlap": bool(spec.get("is_overlap", True)),
            "category_id": str(spec.get("category_id", "25822")),
            "category_name": spec.get("category_name", "Trending"),
            "effect_id": effect_id,
            "resource_id": str(spec.get("resource_id", effect_id)),
            # In many CapCut drafts this mirrors effect_id; fall back to effect_id if unset
            "third_resource_id": str(spec.get("third_resource_id", effect_id or "0")),
            "platform": "all",
            "source_platform": 1,
            "type": "transition",
            "path": path,
            "video_path": "",
            "request_id": "",
            "task_id": "",
            "is_ai_transition": False,
        })

        # Insert into PRECEDING segment, after speed & placeholder (index 2)
        refs = segs[i].setdefault("extra_material_refs", [])
        insert_pos = 2 if len(refs) >= 2 else len(refs)
        if tid not in refs:
            refs.insert(insert_pos, tid)
            added += 1

    log.info("[transitions] catalog=%d cuts=%d added=%d",
             len(catalog), max(0, len(segs) - 1), added)
    return dc, timeline




__all__ = [
    "add_imports",
    "build_timeline", 
    "apply_transitions",
]
