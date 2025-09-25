# operations.py
from __future__ import annotations
from typing import Dict, Any

def compute_operations(
    draft_content: Dict[str, Any],
    draft_meta_info: Dict[str, Any],
    draft_virtual_store: Dict[str, Any],
    timeline: Dict[str, Any],
    idmaps: Dict[str, Any],
    now_timestamp_us: int,
) -> Dict[str, Any]:
    """
    Minimal ops payload the synchronizer/doctor can consume.
    """
    duration_us = int(draft_content.get("duration", 0))
    ops = {
        "generated_at_us": now_timestamp_us,
        "project_total_duration_us": duration_us,
        "counts": {
            "clips": len(timeline.get("clips", [])),
            "audio_tracks": 1 if timeline.get("audio") else 0,
        },
        "idmaps": idmaps,
    }
    return ops
