# operations.py
from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path
import uuid
import time
import random
import re
import subprocess
import shlex
import math

MICROS_PER_MS = 1_000
MICROS_PER_SEC = 1_000_000

# ------------------ time & id helpers ------------------

def now_epoch_ms() -> int:
    return int(time.time() * 1000)

def gen_uuid(lowercase: bool = True) -> str:
    u = str(uuid.uuid4())
    return u.lower() if lowercase else u

def ms_to_us(ms: int) -> int:
    return int(ms) * MICROS_PER_MS

# ------------------ timeline helpers ------------------

def compute_track_positions(n: int, clip_ms: int, trans_ms: int) -> List[Tuple[int, int]]:
    """
    Return [(start_us, dur_us)] for n clips.
    Conservative baseline:
      - All clips advance by clip_ms regardless of transition overlap.
      - Overlap is visually handled by CapCut via transition refs.
    """
    out: List[Tuple[int, int]] = []
    cur_ms = 0
    for _ in range(n):
        out.append((ms_to_us(cur_ms), ms_to_us(clip_ms)))
        cur_ms += clip_ms
    return out

def choose_transition(catalog: List[Dict[str, Any]], policy: Dict[str, Any], rr_idx: int) -> Dict[str, Any]:
    if not catalog:
        return {}
    mode = (policy.get("mode") or "random").lower()
    if mode == "fixed":
        name = policy.get("fixed_name", "")
        for t in catalog:
            if t.get("name") == name:
                return t
        return random.choice(catalog)
    if mode == "round_robin":
        return catalog[rr_idx % len(catalog)]
    return random.choice(catalog)

def clamp_transition_duration_ms(cat_entry: Dict[str, Any], desired_ms: int) -> int:
    mn = int(cat_entry.get("min_duration_ms", 200))
    mx = int(cat_entry.get("max_duration_ms", 2000))
    d  = int(desired_ms)
    return max(mn, min(mx, d))

# ------------------ media scanning (mixed images & videos) ------------------

_IMAGE_EXTS = {".jpg",".jpeg",".png",".bmp",".webp",".gif",".tif",".tiff"}
_VIDEO_EXTS = {".mp4",".mov",".mkv",".avi",".webm",".m4v"}
_AUDIO_EXTS = {".mp3",".wav",".aac",".m4a",".flac",".ogg"}

def _numeric_key(p: Path) -> tuple[int, str]:
    """
    Sort by numeric filename stem when possible (1,2,10),
    otherwise push to the end and use case-insensitive stem.
    """
    stem = p.stem
    m = re.fullmatch(r"(\d+)", stem)
    return (int(m.group(1)) if m else 10**12, stem.lower())

def _is_media(p: Path) -> bool:
    ex = p.suffix.lower()
    return ex in _IMAGE_EXTS or ex in _VIDEO_EXTS

def _is_audio(p: Path) -> bool:
    return p.suffix.lower() in _AUDIO_EXTS

def list_media_files(images_dir: Path, sounds_dir: Path) -> Dict[str, List[Path]]:
    media: List[Path] = []
    sounds: List[Path] = []
    images_dir = Path(images_dir)
    sounds_dir = Path(sounds_dir)

    if images_dir.exists():
        media = sorted(
            [p for p in images_dir.iterdir() if p.is_file() and _is_media(p)],
            key=_numeric_key
        )
    if sounds_dir.exists():
        sounds = sorted([p for p in sounds_dir.iterdir() if p.is_file() and _is_audio(p)])

    return {"media": media, "sounds": sounds}

# ------------------ audio duration probing ------------------

def _ffprobe_duration_seconds(path: Path) -> Optional[float]:
    """Return duration in seconds using ffprobe, if available on PATH."""
    try:
        cmd = ["ffprobe", "-v", "error",
               "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1",
               str(path)]
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=False)
        s = out.decode("utf-8", "ignore").strip()
        if s:
            return float(s)
    except Exception:
        pass
    return None

def _mutagen_duration_seconds(path: Path) -> Optional[float]:
    try:
        from mutagen import File as MutagenFile  # type: ignore
        mf = MutagenFile(str(path))
        if mf and getattr(mf, "info", None) and getattr(mf.info, "length", None):
            return float(mf.info.length)
    except Exception:
        pass
    return None

def _wave_duration_seconds(path: Path) -> Optional[float]:
    if path.suffix.lower() not in {".wav", ".wave"}:
        return None
    try:
        import wave
        with wave.open(str(path), "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            if rate > 0:
                return frames / float(rate)
    except Exception:
        pass
    return None

def probe_audio_duration_us(path: Path) -> Optional[int]:
    """
    Try multiple strategies to get accurate audio duration.
    Order: ffprobe -> mutagen -> wave -> None
    Returns microseconds, or None if unknown.
    """
    path = Path(path)
    for fn in (_ffprobe_duration_seconds, _mutagen_duration_seconds, _wave_duration_seconds):
        sec = fn(path)
        if sec and sec > 0:
            return int(round(sec * MICROS_PER_SEC))
    return None
