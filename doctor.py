# doctor.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


# ----------------------------
# Helpers
# ----------------------------

def _ensure_material_buckets(dc: Dict[str, Any]) -> None:
    mats = dc.setdefault("materials", {})
    for key in (
        "videos", "audios", "transitions",
        "speeds", "placeholder_infos", "sound_channel_mappings",
        # optional buckets CapCut may add on its own:
        "beats", "loudnesses", "material_colors", "material_animations", "canvas_colors"
    ):
        mats.setdefault(key, [])
    dc.setdefault("tracks", [])


def _first_track(dc: Dict[str, Any], kind: str) -> Optional[Dict[str, Any]]:
    return next((t for t in dc.get("tracks", []) if t.get("type") == kind), None)


def _video_span(dc: Dict[str, Any]) -> int:
    vtrack = _first_track(dc, "video")
    if not vtrack:
        return 0
    end = 0
    for seg in vtrack.get("segments", []) or []:
        tr = seg.get("target_timerange") or {}
        end = max(end, int(tr.get("start", 0) or 0) + int(tr.get("duration", 0) or 0))
    return end


def _audio_span(dc: Dict[str, Any]) -> int:
    atrack = _first_track(dc, "audio")
    if not atrack:
        return 0
    end = 0
    for seg in atrack.get("segments", []) or []:
        tr = seg.get("target_timerange") or {}
        end = max(end, int(tr.get("start", 0) or 0) + int(tr.get("duration", 0) or 0))
    return end


def _material_index(dc: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    idx: Dict[str, Dict[str, Any]] = {}
    mats = dc.get("materials", {})
    for bucket in mats.values():
        for item in bucket or []:
            mid = item.get("id")
            if mid:
                idx[str(mid)] = item
    return idx


def _import_ids(dmi: Dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for bucket in dmi.get("draft_materials", []):
        if bucket.get("type") != 0:
            continue
        for v in bucket.get("value", []) or []:
            _id = v.get("id")
            if _id:
                ids.add(str(_id))
    return ids


# ----------------------------
# Public API
# ----------------------------

def inspect_and_fix(
    draft_content: Dict[str, Any],
    draft_meta_info: Dict[str, Any],
    draft_virtual_store: Dict[str, Any],
    *,
    strict: bool = False,
    autofix: bool = False,
) -> Dict[str, Any]:
    """
    Validate basic CapCut invariants and (optionally) apply minimal safe fixes.
    Returns a report:
      {
        "issues": [...],
        "fixes": [...],
        "patched": bool,
        "draft_content": <possibly modified>,
        "draft_meta_info": <possibly modified>,
        "draft_virtual_store": <unchanged>,
        "summary": {...}
      }
    """
    dc = dict(draft_content or {})
    dmi = dict(draft_meta_info or {})
    dvs = dict(draft_virtual_store or {})

    issues: List[str] = []
    fixes: List[str] = []
    patched = False

    # Ensure scaffolding
    _ensure_material_buckets(dc)

    # 1) Existence of tracks
    vtrack = _first_track(dc, "video")
    if not vtrack:
        issues.append("Missing video track.")
        if autofix:
            vtrack = {"id": "VIDEO_TRACK", "type": "video", "segments": []}
            dc["tracks"].append(vtrack)
            fixes.append("Inserted empty video track.")
            patched = True

    atrack = _first_track(dc, "audio")
    # It's OK if there is no audio track; do not autofix by default.

    # 2) Segment.material_id must exist in materials index
    index = _material_index(dc)
    if vtrack:
        for idx_s, seg in enumerate(vtrack.get("segments", []) or []):
            mid = str(seg.get("material_id", ""))
            if not mid or mid not in index:
                issues.append(f"Video segment {idx_s} references missing material_id={mid!r}.")

    if atrack:
        for idx_s, seg in enumerate(atrack.get("segments", []) or []):
            mid = str(seg.get("material_id", ""))
            if not mid or mid not in index:
                issues.append(f"Audio segment {idx_s} references missing material_id={mid!r}.")

    # 3) local_material_id must match an import id
    import_ids = _import_ids(dmi)
    for vm in dc.get("materials", {}).get("videos", []) or []:
        lmid = vm.get("local_material_id")
        if not lmid:
            issues.append(f"Video material {vm.get('id')} missing local_material_id.")
        elif str(lmid) not in import_ids:
            issues.append(f"Video material {vm.get('id')} local_material_id not found in draft_meta_info imports.")

    for am in dc.get("materials", {}).get("audios", []) or []:
        lmid = am.get("local_material_id")
        if not lmid:
            issues.append(f"Audio material {am.get('id')} missing local_material_id.")
        elif str(lmid) not in import_ids:
            issues.append(f"Audio material {am.get('id')} local_material_id not found in draft_meta_info imports.")

    # 4) Duration synchrony (content vs meta)
    video_span = _video_span(dc)
    audio_span = _audio_span(dc)
    expected_duration = max(video_span, audio_span)
    content_duration = int(dc.get("duration", 0) or 0)
    if content_duration != expected_duration:
        issues.append(f"draft_content.duration={content_duration} but expected {expected_duration}.")
        if autofix:
            dc["duration"] = expected_duration
            fixes.append(f"Set draft_content.duration={expected_duration}.")
            patched = True

    tm = int(dmi.get("tm_duration", 0) or 0)
    if tm != int(dc.get("duration", 0) or 0):
        issues.append(f"draft_meta_info.tm_duration={tm} does not mirror draft_content.duration={dc.get('duration', 0)}.")
        if autofix:
            dmi["tm_duration"] = int(dc.get("duration", 0) or 0)
            fixes.append(f"Mirrored draft_meta_info.tm_duration={dmi['tm_duration']}.")
            patched = True

    # 5) Transition references sanity (optional)
    if vtrack:
        segs = vtrack.get("segments", []) or []
        for i in range(len(segs) - 1):
            seg = segs[i]
            # If a transition is referenced, ensure the ref id points to a transition
            refs = list(seg.get("extra_material_refs", []) or [])
            for ref in refs:
                mat = index.get(ref)
                if mat and mat.get("type") == "transition":
                    # Check basic duration safety
                    tdur = int(mat.get("duration", 0) or 0)
                    prev_d = int(seg.get("target_timerange", {}).get("duration", 0) or 0)
                    next_d = int(segs[i + 1].get("target_timerange", {}).get("duration", 0) or 0)
                    if tdur < 200_000 or (prev_d and next_d and tdur > min(prev_d, next_d)):
                        issues.append(
                            f"Transition {ref} duration {tdur}us not safe for cut {i}->{i+1} (prev={prev_d}, next={next_d})."
                        )

    # 6) Basic meta stamping (name/folder path) — we only warn here
    if not dmi.get("draft_name"):
        issues.append("draft_meta_info.draft_name is empty.")
    if not dmi.get("draft_fold_path"):
        issues.append("draft_meta_info.draft_fold_path is empty.")

    report = {
        "issues": issues,
        "fixes": fixes,
        "patched": patched,
        "draft_content": dc,
        "draft_meta_info": dmi,
        "draft_virtual_store": dvs,  # we do not modify vstore here
        "summary": {
            "video_span_us": video_span,
            "audio_span_us": audio_span,
            "content_duration_us": int(dc.get("duration", 0) or 0),
            "tm_duration_us": int(dmi.get("tm_duration", 0) or 0),
            "num_video_segments": len((_first_track(dc, "video") or {}).get("segments", []) or []),
            "num_audio_segments": len((_first_track(dc, "audio") or {}).get("segments", []) or []),
            "num_transitions": len(dc.get("materials", {}).get("transitions", []) or []),
        },
    }

    # Log a brief summary
    log.info(
        "doctor: issues=%d patched=%s content_dur=%dus tm=%dus",
        len(issues),
        patched,
        report["summary"]["content_duration_us"],
        report["summary"]["tm_duration_us"],
    )
    if strict and issues:
        log.warning("doctor(strict) found issues: %s", issues)

    return report
