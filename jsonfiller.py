# jsonfiller.py
from __future__ import annotations
from typing import Dict, List, Tuple, Any, Optional
from pathlib import Path
import uuid
import random
from typing import Optional
try:
    from mutagen import File as MutagenFile  # supports mp3, m4a, etc.
except Exception:
    MutagenFile = None

# Optional image/audio metadata
try:
    from PIL import Image  # pip install Pillow
except Exception:
    Image = None

import contextlib
import wave

US = 1_000_000

# ---------------- Helpers ----------------

def _abs(p: str | Path) -> str:
    return str(Path(p).expanduser().resolve())

def _fname(p: str | Path) -> str:
    return Path(p).name

def _uuid_upper() -> str:
    return str(uuid.uuid4()).upper()

def _uuid_lower() -> str:
    return str(uuid.uuid4()).lower()

def _get_img_size(path: str) -> Tuple[Optional[int], Optional[int]]:
    if Image is None:
        return None, None
    try:
        with Image.open(path) as im:
            return im.width, im.height
    except Exception:
        return None, None

def _get_wav_duration_us(path: str) -> Optional[int]:
    try:
        with contextlib.closing(wave.open(path, 'rb')) as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate > 0:
                return int(frames / float(rate) * US)
    except Exception:
        pass
    return None

def _ensure_content_scaffolding(dc: Dict[str, Any]):
    dc.setdefault("materials", {})
    m = dc["materials"]
    for key in ["videos", "audios", "transitions", "canvases", "beats",
                "material_colors", "placeholder_infos", "sound_channel_mappings", "speeds"]:
        m.setdefault(key, [])
    dc.setdefault("tracks", [])
    # Duration default
    dc.setdefault("duration", 0)
    return dc

def _find_or_create_meta_bucket(meta: Dict[str, Any], type_id: int) -> List[Dict[str, Any]]:
    """
    draft_meta_info.draft_materials is usually a list of buckets like:
      [{"type":0,"value":[...]}]
    """
    meta.setdefault("draft_materials", [])
    for bucket in meta["draft_materials"]:
        if isinstance(bucket, dict) and bucket.get("type") == type_id:
            bucket.setdefault("value", [])
            return bucket["value"]
    # create if not found
    new_bucket = {"type": type_id, "value": []}
    meta["draft_materials"].append(new_bucket)
    return new_bucket["value"]

def _find_or_create_vstore_bucket(vs: Dict[str, Any], type_id: int) -> List[Dict[str, Any]]:
    """
    draft_virtual_store has buckets like:
      [{"type":1,"value":[{"child_id": "..."}]}]
    """
    vs.setdefault("draft_virtual_store", [])
    for bucket in vs["draft_virtual_store"]:
        if isinstance(bucket, dict) and bucket.get("type") == type_id:
            bucket.setdefault("value", [])
            return bucket["value"]
    new_bucket = {"type": type_id, "value": []}
    vs["draft_virtual_store"].append(new_bucket)
    return new_bucket["value"]

# ---------------- Public API ----------------

def add_imports(
    draft_meta_info: Dict[str, Any],
    draft_virtual_store: Dict[str, Any],
    images: List[str],
    sounds: List[str],
    id_strategy: str = "mirror",
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """
    Populate the import catalog (meta) and mirror IDs in virtual_store.
    Returns updated (meta, virtual_store, idmaps).
    """
    dmi = dict(draft_meta_info)  # shallow copy
    dvs = dict(draft_virtual_store)

    meta_items = _find_or_create_meta_bucket(dmi, type_id=0)        # imported items
    vstore_children = _find_or_create_vstore_bucket(dvs, type_id=1) # child_id mirror

    idmaps: Dict[str, Any] = {"images": [], "audios": []}

    # Images
    for img in images:
        path = _abs(img)
        width, height = _get_img_size(path)
        mid = _uuid_lower()  # import-catalog id (lowercase style)
        meta_items.append({
            "id": mid,
            "metetype": "photo",
            "file_Path": path,
            "material_name": _fname(path),
            "width": width,
            "height": height,
            "duration": 5_000_000,  # nominal per-still duration; timeline will decide actual
        })
        vstore_children.append({"child_id": mid})
        idmaps["images"].append({"path": path, "import_id": mid})

    if sounds:
        apath = _abs(sounds[0])
        dur_us = _get_audio_duration_us(apath)
        aud_id = _uuid_lower()
        meta_items.append({
            "id": aud_id,
            "metetype": "music",
            "file_Path": apath,
            "material_name": _fname(apath),
            "duration": dur_us if dur_us is not None else 0,  # will still be synced later if 0
        })
        vstore_children.append({"child_id": aud_id})
        idmaps["audios"].append({"path": apath, "import_id": aud_id})

    return dmi, dvs, idmaps


def build_timeline(
    draft_content: Dict[str, Any],
    images: List[str],
    sounds: List[str],
    default_image_duration_ms: int,
    ordering: str = "numeric",
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Create materials (videos/audios) and tracks (video/audio) in draft_content.
    """
    dc = _ensure_content_scaffolding(dict(draft_content))  # shallow copy

    video_materials = dc["materials"]["videos"]
    audio_materials = dc["materials"]["audios"]

    # -------- Video materials + track --------
    video_track = {
        "id": _uuid_upper(),
        "type": "video",
        "segments": [],
    }

    start_us = 0
    dur_us = default_image_duration_ms * 1000

    for img in images:
        path = _abs(img)
        w, h = _get_img_size(path)
        vm_id = _uuid_upper()

        video_materials.append({
            "id": vm_id,
            "type": "photo",
            "path": path,
            "material_name": _fname(path),
            "width": w,
            "height": h,
            "duration": dur_us,
        })

        seg_id = _uuid_upper()
        video_track["segments"].append({
            "id": seg_id,
            "material_id": vm_id,
            "target_timerange": {"start": start_us, "duration": dur_us},
            "source_timerange": {"start": 0, "duration": dur_us},
            "extra_material_refs": [],
        })
        start_us += dur_us

    total_video_us = start_us
    if video_track["segments"]:
        dc["tracks"].append(video_track)


    # -------- Audio material + track (optional) --------
    audio_seg_dur_us = 0
    if sounds:
        apath = _abs(sounds[0])
        a_dur_us = _get_audio_duration_us(apath)  # <-- real duration if possible
        if a_dur_us is None:
            a_dur_us = total_video_us  # fallback

        am_id = _uuid_upper()
        audio_materials.append({
            "id": am_id,
            "name": _fname(apath),
            "path": apath,
            "duration": a_dur_us,
            "type": "extract_music",
        })

        audio_seg_dur_us = a_dur_us
        audio_track = {
            "id": _uuid_upper(),
            "type": "audio",
            "segments": [{
                "id": _uuid_upper(),
                "material_id": am_id,
                "target_timerange": {"start": 0, "duration": a_dur_us},
                "source_timerange": {"start": 0, "duration": a_dur_us},
                "extra_material_refs": [],
            }],
        }
        dc["tracks"].append(audio_track)


    # -------- Project duration --------
    dc["duration"] = max(total_video_us, audio_seg_dur_us if sounds else total_video_us)


    # Cache for later stages (ops/doctor)
    timeline_cache = {
        "clips": [
            {
                "path": seg["material_id"],  # points to video material id
                "start_us": seg["target_timerange"]["start"],
                "dur_us": seg["target_timerange"]["duration"],
            }
            for seg in video_track["segments"]
        ],
        "audio": [audio_materials[-1]["id"]] if sounds else [],
    }

    return dc, timeline_cache



def _first_existing_child_dir(base: Path) -> str | None:
    if base.exists() and base.is_dir():
        for child in base.iterdir():
            if child.is_dir():
                return str(child)
    return None

def apply_transitions(
    draft_content: Dict[str, Any],
    timeline: Dict[str, Any],
    names: List[str],
    per_cut_probability: float,
    duration_ms_range: tuple[int, int],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    dc = _ensure_content_scaffolding(dict(draft_content))

    # Find video track
    video_track = None
    for tr in dc.get("tracks", []):
        if tr.get("type") == "video":
            video_track = tr
            break
    if not video_track or not video_track.get("segments"):
        return dc, timeline

    cfg_trans = timeline.get("__cfg_transitions__", {})  # optional pass-through
    trans_bucket = dc["materials"]["transitions"]

    # Pull catalog from a place we store in timeline cache OR attach in operations later.
    # Safer: stash into draft_content for now if not already
    catalog = dc.get("__transition_catalog__")
    cache_root = dc.get("__transition_cache_root__")
    if catalog is None or cache_root is None:
        # try to pull from timeline cache injected by the stage caller (initializer)
        catalog = timeline.get("catalog") or []
        cache_root = timeline.get("cache_root")

    # Fallbacks (no catalog => keep existing behavior but will be placeholders)
    if not catalog:
        return dc, timeline

    # Filter by names if provided
    if names:
        catalog = [c for c in catalog if c.get("name") in set(names)] or catalog

    # Prob/duration
    p = max(0.0, min(1.0, float(per_cut_probability)))
    try:
        dmin, dmax = int(duration_ms_range[0]), int(duration_ms_range[1])
        if dmin > dmax: dmin, dmax = dmax, dmin
    except Exception:
        dmin, dmax = 600, 800

    # Walk cuts and add transitions
    segs = video_track["segments"]
    for i in range(len(segs) - 1):
        if random.random() > p:
            continue

        spec = random.choice(catalog)
        name = spec.get("name", "CrossFade")
        is_overlap = bool(spec.get("is_overlap", True))
        duration_us = random.randint(dmin, dmax) * 1000

        # Required IDs from catalog
        effect_id = str(spec.get("effect_id", ""))
        resource_id = str(spec.get("resource_id", effect_id or ""))
        third_resource_id = str(spec.get("third_resource_id", "0"))
        category_id = str(spec.get("category_id", "0"))
        category_name = spec.get("category_name", "")
        platform = "all"
        source_platform = 1  # observed in your JSON

        # Resolve cache path
        path = ""
        if cache_root:
            base = Path(cache_root) / resource_id
            # choose first child dir (hash) to match CapCut cache layout
            sub = _first_existing_child_dir(base)
            if sub:
                path = sub

        # Create a real transition material
        tid = _uuid_upper()
        trans_bucket.append({
            "id": tid,
            "name": name,
            "duration": duration_us,
            "is_overlap": is_overlap,
            "type": "transition",
            "platform": platform,
            "source_platform": source_platform,
            "category_id": category_id,
            "category_name": category_name,
            "effect_id": effect_id,
            "resource_id": resource_id,
            "third_resource_id": third_resource_id,
            "path": path,  # may be "", CapCut can redownload
            "request_id": "", "task_id": "", "video_path": "",
        })

        # Attach to the preceding segment
        refs = segs[i].setdefault("extra_material_refs", [])
        if tid not in refs:
            refs.append(tid)

    return dc, timeline


def _get_audio_duration_us(path: str) -> Optional[int]:
    # WAV (fast, built-in)
    if path.lower().endswith(".wav"):
        dur = _get_wav_duration_us(path)
        if dur: 
            return dur

    # MP3/M4A/others via mutagen
    if MutagenFile is not None:
        try:
            mf = MutagenFile(path)
            if mf is not None and getattr(mf, "info", None) and getattr(mf.info, "length", None):
                return int(mf.info.length * US)
        except Exception:
            pass
    return None
