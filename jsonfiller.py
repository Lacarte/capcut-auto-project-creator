# jsonfiller.py
from __future__ import annotations
from typing import Dict, Any, List, Tuple
from pathlib import Path
import json
import shutil

from operations import (
    gen_uuid,
    ms_to_us,
    compute_track_positions,
    choose_transition,
    clamp_transition_duration_ms,
    probe_audio_duration_us,
    MICROS_PER_SEC,
)

# ---------- IO helpers ----------

def load_json(path: Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)

def save_json(data: Dict[str, Any], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def copy_templates(template_paths: Dict[str, Path], out_dir: Path) -> Dict[str, Path]:
    out: Dict[str, Path] = {}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for key, src in template_paths.items():
        src = Path(src)
        if not src.exists():
            raise FileNotFoundError(f"Template not found for '{key}': {src}")
        dst = out_dir / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        out[key] = dst
    return out

# ---------- Import (CRUD) ----------

def _ensure_bucket(lst: List[Dict[str, Any]], t: int) -> Dict[str, Any]:
    for g in lst:
        if g.get("type") == t:
            g.setdefault("value", [])
            return g
    g = {"type": t, "value": []}
    lst.append(g)
    return g

def _metetype_for_path(p: Path) -> str:
    ex = p.suffix.lower()
    if ex in {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}:
        return "video"
    if ex in {".mp3", ".wav", ".aac", ".m4a", ".flac", ".ogg"}:
        return "music"
    return "photo"

def ingest_media_into_meta_and_store(
    dmi: Dict[str, Any],
    dvs: Dict[str, Any],
    media: List[Path],
    sounds: List[Path],
) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    RESET imports/links, then insert current assets with ABSOLUTE paths:
      - draft_meta_info.draft_materials[type=0].value[]  (imports)
      - draft_virtual_store.draft_virtual_store[type=1].value[]  (child links)

    Returns:
      media_entries  = [{ material_id (import-id), path(abs), metetype }, ...]
      sound_entries  = [{ material_id (import-id), path(abs), metetype }, ...]
    """
    dmi.setdefault("draft_materials", [])
    dvs.setdefault("draft_virtual_store", [])
    meta_imports = _ensure_bucket(dmi["draft_materials"], 0)
    vs_links     = _ensure_bucket(dvs["draft_virtual_store"], 1)

    # Clear stale template entries
    meta_imports["value"].clear()
    vs_links["value"].clear()

    media_entries: List[Dict[str, Any]] = []
    sound_entries: List[Dict[str, Any]] = []

    def _add_import(p: Path) -> Dict[str, Any]:
        p_abs = Path(p).resolve()
        mid = gen_uuid(lowercase=True)
        metetype = _metetype_for_path(p_abs)
        imp = {
            "id": mid,
            "type": 0,
            "file_Path": str(p_abs),          # <-- ABSOLUTE
            "metetype": metetype,
            "extra_info": p_abs.name,
            "width": 0, "height": 0,
            "roughcut_time_range": {"start": 0, "duration": -1},
            "sub_time_range": {"start": -1, "duration": -1},
            "item_source": 1,
            "md5": "",
        }
        meta_imports["value"].append(imp)
        vs_links["value"].append({"child_id": mid, "parent_id": ""})
        return imp

    for p in media:
        imp = _add_import(p)
        media_entries.append({
            "material_id": imp["id"],         # import-id (used later as local_material_id)
            "path": imp["file_Path"],         # ABSOLUTE
            "metetype": imp["metetype"],
        })

    for p in sounds:
        imp = _add_import(p)
        sound_entries.append({
            "material_id": imp["id"],         # import-id (used later as local_material_id)
            "path": imp["file_Path"],         # ABSOLUTE
            "metetype": imp["metetype"],
        })

    return dmi, dvs, media_entries, sound_entries

# ---------- Timeline ----------

def _new_speed(mats: Dict[str, Any]) -> str:
    i = gen_uuid(False)
    mats.setdefault("speeds", []).append({"id": i, "type": "speed", "mode": 0, "speed": 1.0, "curve_speed": None})
    return i

def _new_placeholder(mats: Dict[str, Any]) -> str:
    i = gen_uuid(False)
    mats.setdefault("placeholder_infos", []).append({
        "id": i, "type": "placeholder_info", "meta_type": "none",
        "error_path": "", "error_text": "", "res_path": "", "res_text": ""
    })
    return i

def _new_sound_channel_mapping(mats: Dict[str, Any]) -> str:
    i = gen_uuid(False)
    mats.setdefault("sound_channel_mappings", []).append({"id": i, "type": "", "is_config_open": False, "audio_channel_mapping": 0})
    return i

def _new_beats(mats: Dict[str, Any]) -> str:
    """Create a beats material to match CapCut’s audio extras (minimal)."""
    i = gen_uuid(False)
    mats.setdefault("beats", []).append({
        "id": i,
        "type": "beats",
        "mode": 404,
        "gear": 404,
        "gear_count": 0,
        "enable_ai_beats": False,
        "user_beats": [],
        "ai_beats": {"beats_url": "", "beats_path": "", "melody_url": "", "melody_path": "", "melody_percents": [0.0], "beat_speed_infos": []},
        "user_delete_ai_beats": None
    })
    return i

def _new_vocal_separation(mats: Dict[str, Any]) -> str:
    """Create a minimal vocal_separation material as seen in your sample."""
    i = gen_uuid(False)
    mats.setdefault("vocal_separations", []).append({
        "id": i,
        "type": "vocal_separation",
        "choice": 0,
        "enter_from": "",
        "final_algorithm": "",
        "production_path": "",
        "removed_sounds": [],
        "time_range": None
    })
    return i

def build_timeline_using_templates(
    dc: Dict[str, Any],
    media: List[Dict[str, Any]],
    sounds: List[Dict[str, Any]],
    catalog: List[Dict[str, Any]],
    policy: Dict[str, Any],
    image_duration_ms: int
) -> Dict[str, Any]:
    mats = dc.setdefault("materials", {})
    # Reset template items
    mats["videos"] = []
    mats["audios"] = []
    mats["transitions"] = []
    mats["speeds"] = []
    mats["placeholder_infos"] = []
    mats["sound_channel_mappings"] = []
    mats["beats"] = []                 # <-- to match your audio-only sample
    mats["vocal_separations"] = []     # <-- to match your audio-only sample
    dc["tracks"] = []

    # main video track
    main_track = {
        "type": "video",
        "segments": [],
        "id": gen_uuid(False),
        "name": "",
        "flag": 0,
        "attribute": 0,
        "is_default_name": True,
    }
    dc["tracks"].append(main_track)

    positions = compute_track_positions(len(media), image_duration_ms, 0)
    rr = 0
    timeline_end = 0

    # Build video/photo segments (unchanged from prior version)
    for idx, (m, pos) in enumerate(zip(media, positions)):
        start_us, dur_us = pos
        mtype = "video" if m.get("metetype") == "video" else "photo"
        mat_id = gen_uuid(False)
        seg_id = gen_uuid(False)

        vpath = str(Path(m["path"]).resolve())
        mats["videos"].append({
            "id": mat_id,
            "type": mtype,
            "name": Path(vpath).name,
            "path": vpath,                    # ABSOLUTE
            "duration": dur_us,
            "has_audio": False,
            "material_name": Path(vpath).name,
        })

        speed_id = _new_speed(mats)
        ph_id    = _new_placeholder(mats)
        scm_id   = _new_sound_channel_mapping(mats)

        seg = {
            "id": seg_id,
            "material_id": mat_id,
            "target_timerange": {"start": start_us, "duration": dur_us},
            "source_timerange": {"start": 0, "duration": dur_us},
            "speed": 1.0,
            "visible": True,
            "source": "segmentsourcenormal",
            "extra_material_refs": [speed_id, ph_id],
        }

        if idx < len(media) - 1 and catalog:
            t = choose_transition(catalog, policy, rr_idx=rr); rr += 1
            dur_ms = clamp_transition_duration_ms(t, policy.get("max_duration_ms", t.get("default_duration_ms", 600)))
            trans_id = gen_uuid(False)
            path = t.get("path_template", "")
            eff_id = str(t.get("effect_id", ""))
            if path and "{effect_id}" in path:
                path = path.replace("{effect_id}", eff_id)

            mats["transitions"].append({
                "id": trans_id,
                "type": "transition",
                "name": t.get("name"),
                "effect_id": t.get("effect_id"),
                "resource_id": t.get("resource_id", eff_id),
                "third_resource_id": t.get("third_resource_id", eff_id),
                "category_id": t.get("category_id"),
                "category_name": t.get("category_name"),
                "is_overlap": bool(t.get("is_overlap", True)),
                "duration": ms_to_us(dur_ms),
                "platform": t.get("platform", "all"),
                "source_platform": t.get("source_platform", 1),
                "path": path,
            })
            seg["extra_material_refs"].append(trans_id)

        seg["extra_material_refs"].append(scm_id)
        main_track["segments"].append(seg)
        timeline_end = max(timeline_end, start_us + dur_us)

    # --- AUDIO: true length, editable tail, proper extras, and link to import ---
    audio_end = 0
    if sounds:
        a0 = sounds[0]
        apath = Path(a0["path"]).resolve()
        audio_us = probe_audio_duration_us(apath)
        if not audio_us or audio_us <= 0:
            audio_us = max(timeline_end, 30 * MICROS_PER_SEC)

        # Accessory materials for audio
        speed_id = _new_speed(mats)
        ph_id    = _new_placeholder(mats)
        beats_id = _new_beats(mats)                # present in your sample
        scm_id   = _new_sound_channel_mapping(mats)
        vs_id    = _new_vocal_separation(mats)     # present in your sample

        amid = gen_uuid(False)
        aseg = gen_uuid(False)

        # Audio material (mirror key fields from your sample—still minimal)
        mats["audios"].append({
            "id": amid,
            "type": "extract_music",
            "name": apath.name,
            "path": str(apath),                     # ABSOLUTE
            "duration": int(audio_us),
            "category_id": "",
            "category_name": "local",
            "check_flag": 1,
            "local_material_id": a0["material_id"], # <-- link to import (critical)
            "ai_music_type": 0,
            "ai_music_generate_scene": 0,
            "source_platform": 0,
        })

        dc["tracks"].append({
            "type": "audio",
            "segments": [{
                "id": aseg,
                "material_id": amid,
                "target_timerange": {"start": 0, "duration": int(audio_us)},
                "source_timerange": {"start": 0, "duration": int(audio_us)},
                # match your sample order: speed, placeholder, beats, scm, vocal_separation
                "extra_material_refs": [speed_id, ph_id, beats_id, scm_id, vs_id],
                "source": "segmentsourcenormal",
                "visible": True,
                "speed": 1.0,
                "volume": 1.0,
                "is_loop": False,
            }],
            "id": gen_uuid(False),
            "name": "",
            "flag": 0,
            "attribute": 0,
            "is_default_name": True,
        })
        audio_end = int(audio_us)

    # Project duration expands to cover audio if longer
    dc["duration"] = max(timeline_end, audio_end)
    return dc
