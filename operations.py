# operations.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import subprocess
import json
import math
import logging

log = logging.getLogger(__name__)

# Prefer local repo lib/ffprobe.exe; fallback to PATH "ffprobe"
FFPROBE_PATH = Path(__file__).resolve().parent / "lib" / "ffprobe.exe"


# =========================
# Probing (images/videos)
# =========================

@dataclass
class ProbedMedia:
    path: Path
    media_type: str  # "image" or "video"
    width: int
    height: int
    duration_us: int  # images: default; videos: actual
    fps: Optional[float]


def _run_ffprobe(path: Path) -> Optional[dict]:
    try:
        exe = str(FFPROBE_PATH) if FFPROBE_PATH.exists() else "ffprobe"
        cmd = [
            exe, "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration,avg_frame_rate",
            "-of", "json", str(path)
        ]
        out = subprocess.check_output(cmd)
        return json.loads(out.decode("utf-8"))
    except Exception as e:
        log.debug("[ffprobe] failed for %s: %s", path, e)
        return None


def _fps_from_ffprobe(avg_frame_rate: Optional[str]) -> Optional[float]:
    if not avg_frame_rate:
        return None
    if "/" in avg_frame_rate:
        num, den = avg_frame_rate.split("/", 1)
        try:
            num_f = float(num); den_f = float(den)
            return num_f / den_f if den_f != 0 else None
        except Exception:
            return None
    try:
        return float(avg_frame_rate)
    except Exception:
        return None


def probe_media_or_image(path: Path, default_image_duration_ms: int) -> ProbedMedia:
    ext = path.suffix.lower()
    is_video = ext in {".mp4", ".mov", ".mkv", ".m4v", ".avi", ".webm", ".3gp", ".mts", ".m2ts"}

    # Sensible fallbacks
    width = 1920
    height = 1080
    fps = None
    duration_us = int(default_image_duration_ms * 1000)

    info = _run_ffprobe(path)
    if info and info.get("streams"):
        st = info["streams"][0]
        width = int(st.get("width") or width)
        height = int(st.get("height") or height)
        fps = _fps_from_ffprobe(st.get("avg_frame_rate"))
        if is_video:
            dur_s = st.get("duration")
            if dur_s is not None:
                try:
                    duration_us = int(float(dur_s) * 1_000_000)
                except Exception:
                    pass

    return ProbedMedia(
        path=path,
        media_type="video" if is_video else "image",
        width=width,
        height=height,
        duration_us=duration_us,
        fps=fps,
    )


def natural_key(p: Path) -> Tuple[int, str]:
    """Sort key: trailing number in stem if present (1,2,10…), then name."""
    import re
    s = p.stem
    nums = re.findall(r"\d+", s)
    return (int(nums[-1]) if nums else math.inf, s.lower())


# =========================
# Operations summary
# =========================

def compute_operations(
    draft_content: Dict[str, Any],
    draft_meta_info: Dict[str, Any],
    draft_virtual_store: Dict[str, Any],
    timeline_cache: Dict[str, Any],
    idmaps: Dict[str, Any],
    generated_at_us: int,
) -> Dict[str, Any]:
    """Build a compact, human/debug-friendly summary of the project.

    This is consumed by later stages (synchronizer/doctor) and is safe to evolve
    without breaking CapCut JSON format. It does **not** mutate inputs.
    """
    # Collect clips from draft_content (authoritative) or timeline cache
    clips = []
    vtrack = next((t for t in draft_content.get("tracks", []) if t.get("type") == "video"), None)
    if vtrack:
        for idx, seg in enumerate(vtrack.get("segments", []), start=1):
            tr = seg.get("target_timerange", {})
            clips.append({
                "i": idx,
                "segment_id": seg.get("id"),
                "material_id": seg.get("material_id"),
                "start_us": int(tr.get("start", 0)),
                "dur_us": int(tr.get("duration", 0)),
                "extra_materials": len(seg.get("extra_material_refs", [])),
            })
    elif timeline_cache and timeline_cache.get("clips"):
        # fall back to whatever build_timeline cached
        for idx, clip in enumerate(timeline_cache["clips"], start=1):
            clips.append({
                "i": idx,
                "segment_id": clip.get("segment_id", ""),
                "material_id": clip.get("material_id", ""),
                "start_us": int(clip.get("start_us", 0)),
                "dur_us": int(clip.get("dur_us", 0)),
                "extra_materials": 0,
            })

    # Collect audio info
    audio_info = []
    atrack = next((t for t in draft_content.get("tracks", []) if t.get("type") == "audio"), None)
    if atrack:
        for idx, seg in enumerate(atrack.get("segments", []), start=1):
            tr = seg.get("target_timerange", {})
            audio_info.append({
                "i": idx,
                "segment_id": seg.get("id"),
                "material_id": seg.get("material_id"),
                "start_us": int(tr.get("start", 0)),
                "dur_us": int(tr.get("duration", 0)),
            })

    # Collect transitions info
    transitions_info = []
    if "materials" in draft_content and "transitions" in draft_content["materials"]:
        for idx, trans in enumerate(draft_content["materials"]["transitions"], start=1):
            transitions_info.append({
                "i": idx,
                "id": trans.get("id"),
                "name": trans.get("name", "Unknown"),
                "duration_us": int(trans.get("duration", 0)),
                "effect_id": trans.get("effect_id", ""),
                "is_overlap": trans.get("is_overlap", False),
                "has_cache_path": bool(trans.get("path", "")),
            })

    # Compute total duration from content if not set
    computed_total = 0
    if clips:
        computed_total = max((c["start_us"] + c["dur_us"] for c in clips), default=0)
    content_total = int(draft_content.get("duration", 0) or 0)
    total_us = max(content_total, computed_total)

    # Calculate audio duration
    audio_duration_us = 0
    if audio_info:
        audio_duration_us = max((a["start_us"] + a["dur_us"] for a in audio_info), default=0)

    summary = {
        "generated_at_us": int(generated_at_us),
        "project": {
            "name": draft_meta_info.get("draft_name"),
            "folder": draft_meta_info.get("draft_fold_path"),
            "tracks": len(draft_content.get("tracks", [])),
            "clips": len(clips),
            "transitions": len(transitions_info),
            "duration_us": total_us,
            "audio_duration_us": audio_duration_us,
            "duration_mismatch": abs(total_us - audio_duration_us) > 1000 if audio_duration_us > 0 else False,
        },
        "clips": clips,
        "audio": audio_info,
        "transitions": transitions_info,
        "idmaps": idmaps or {},
        "stats": {
            "total_video_materials": len(draft_content.get("materials", {}).get("videos", [])),
            "total_audio_materials": len(draft_content.get("materials", {}).get("audios", [])),
            "total_transition_materials": len(transitions_info),
            "total_accessory_materials": (
                len(draft_content.get("materials", {}).get("speeds", [])) +
                len(draft_content.get("materials", {}).get("placeholder_infos", [])) +
                len(draft_content.get("materials", {}).get("sound_channel_mappings", []))
            ),
        }
    }
    return summary


__all__ = [
    "ProbedMedia",
    "probe_media_or_image",
    "natural_key",
    "compute_operations",
]