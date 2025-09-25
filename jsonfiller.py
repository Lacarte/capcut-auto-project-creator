# jsonfiller.py - Enhanced with proper CapCut compatibility
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import json
import subprocess
import logging
import uuid
import re
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
    
    speed_ids = []
    placeholder_ids = []
    sound_mapping_ids = []
    
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
            meta_items.append({
                "id": import_id,
                "path": path,
                "file_name": _fname(path),
                "width": w,
                "height": h,
                "duration": dur_us,
                "category_name": "local",
                "source_platform": 0,
            })
        else:
            w, h = _get_img_size(path)
            meta_items.append({
                "id": import_id,
                "path": path,
                "file_name": _fname(path),
                "width": w,
                "height": h,
                # no duration for photos required
                "category_name": "local",
                "source_platform": 0,
            })
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
        vtrack = {"type": "video", "segments": []}
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
                "local_material_id": local_id,  # CRITICAL LINK
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
            "duration": dur_us,
        })
        
        atrack = next((t for t in dc["tracks"] if t.get("type") == "audio"), None)
        if atrack is None:
            atrack = {"type": "audio", "segments": []}
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
    timeline_cache: Dict[str, Any],
    transition_config: Dict[str, Any],
    per_cut_probability: float,
    duration_ms_range: Tuple[int, int],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Apply real transitions with proper CapCut formatting and cache paths."""
    if not transition_config or not transition_config.get("catalog"):
        return draft_content, timeline_cache

    dc = dict(draft_content)
    mats = dc.setdefault("materials", {})
    transitions = mats.setdefault("transitions", [])

    vtrack = next((t for t in dc.get("tracks", []) if t.get("type") == "video"), None)
    if not vtrack:
        return dc, timeline_cache
    segs = vtrack.get("segments", [])
    if len(segs) < 2:
        return dc, timeline_cache

    catalog = transition_config.get("catalog", [])
    cache_root = transition_config.get("cache_root", "")
    lo, hi = duration_ms_range
    lo = max(200, int(lo))
    hi = max(lo, int(hi))

    for i in range(len(segs) - 1):
        if random.random() > per_cut_probability:
            continue
            
        # Pick a random transition from catalog
        transition_def = random.choice(catalog)
        dur_us = int(random.randint(lo, hi) * 1000)
        tr_id = _uuid_upper()
        
        # Resolve cache path if possible
        effect_id = transition_def.get("effect_id", "")
        cache_path = _resolve_transition_cache_path(cache_root, effect_id)
        
        transition_material = {
            "id": tr_id,
            "name": transition_def.get("name", "Transition"),
            "duration": dur_us,
            "is_overlap": transition_def.get("is_overlap", True),
            "category_id": transition_def.get("category_id", "25822"),
            "category_name": transition_def.get("category_name", "remen"),
            "effect_id": effect_id,
            "resource_id": transition_def.get("resource_id", effect_id),
            "third_resource_id": transition_def.get("third_resource_id", "0"),
            "platform": "all",
            "source_platform": 1,
            "type": "transition",
            "path": cache_path,
            "video_path": "",
            "request_id": "",
            "task_id": "",
            "is_ai_transition": False
        }
        
        transitions.append(transition_material)
        
        # Add transition ID to the segment's extra_material_refs
        if "extra_material_refs" not in segs[i]:
            segs[i]["extra_material_refs"] = []
        segs[i]["extra_material_refs"].insert(0, tr_id)  # Insert at beginning

    return dc, timeline_cache


__all__ = [
    "add_imports",
    "build_timeline", 
    "apply_transitions",
]