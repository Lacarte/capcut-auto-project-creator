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
    RESET imports/links, then insert current assets with ABSOLUTE paths.
    """
    dmi.setdefault("draft_materials", [])
    dvs.setdefault("draft_virtual_store", [])
    meta_imports = _ensure_bucket(dmi["draft_materials"], 0)
    vs_links     = _ensure_bucket(dvs["draft_virtual_store"], 1)

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
            "file_Path": str(p_abs),          # ABSOLUTE
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
        media_entries.append({"material_id": imp["id"], "path": imp["file_Path"], "metetype": imp["metetype"]})

    for p in sounds:
        imp = _add_import(p)
        sound_entries.append({"material_id": imp["id"], "path": imp["file_Path"], "metetype": imp["metetype"]})

    return dmi, dvs, media_entries, sound_entries

# ---------- Accessory creators ----------

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

# ---------- Transition path resolver ----------

def _resolve_transition_effect_path(raw_path: str) -> Tuple[str, Dict[str, Any]]:
    """
    Given a template path like .../effect/{effect_id}/,
    return the actual directory CapCut expects:
      - Prefer a child dir containing config.json/extra.json (hash folder).
      - Else if current dir already has them, keep it.
      - Else fall back to '' (let CapCut resolve by IDs).
    Returns (resolved_path, debug_info).
    """
    dbg = {"given": raw_path, "exists": False, "used": "", "has_config": False,
           "has_extra": False, "has_content": False, "has_main_scene": False}
    if not raw_path:
        return "", dbg
    root = Path(raw_path)
    if not root.exists() or not root.is_dir():
        return "", dbg
    dbg["exists"] = True

    def _score_dir(d: Path) -> Tuple[int, Dict[str, bool]]:
        has_config = (d / "config.json").exists()
        has_extra = (d / "extra.json").exists()
        has_content = (d / "content.json").exists()
        has_main_scene = (d / "main.scene").exists()
        score = int(has_config) * 4 + int(has_extra) * 3 + int(has_content) * 2 + int(has_main_scene)
        return score, {"has_config": has_config, "has_extra": has_extra, "has_content": has_content, "has_main_scene": has_main_scene}

    # 1) If root itself looks like an effect payload folder, use it
    score_root, flags_root = _score_dir(root)
    if score_root > 0:
        dbg.update(flags_root)
        dbg["used"] = str(root)
        return str(root), dbg

    # 2) Prefer a child dir with config/extra (hash folder)
    candidates = [d for d in root.iterdir() if d.is_dir() and not d.name.endswith("_tmp")]
    best = None
    best_flags = None
    best_score = -1
    for d in candidates:
        score, flags = _score_dir(d)
        if score > best_score:
            best, best_score, best_flags = d, score, flags

    if best and best_score > 0:
        dbg.update(best_flags)
        dbg["used"] = str(best)
        return str(best), dbg

    # 3) Fallback: choose first subdir (some packs put payload under a nested folder like AmazingAuto_out/)
    if candidates:
        d = candidates[0]
        # try one more level (AmazingAuto_out)
        deeper = [c for c in d.iterdir() if c.is_dir()]
        if deeper:
            # pick a deeper one that has content.json/main.scene if available
            deep_best = None
            deep_flags = None
            deep_score = -1
            for c in deeper:
                score, flags = _score_dir(c)
                if score > deep_score:
                    deep_best, deep_score, deep_flags = c, score, flags
            if deep_best:
                dbg.update(deep_flags)
                dbg["used"] = str(deep_best)
                return str(deep_best), dbg
        dbg["used"] = str(d)
        return str(d), dbg

    # 4) Nothing convincing; let CapCut resolve by IDs
    return "", dbg

# ---------- Timeline ----------

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
    mats["beats"] = []
    mats["vocal_separations"] = []
    dc["tracks"] = []
    dc["_transitions_debug"] = []  # for summary

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

    # Build video/photo segments
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
            "path": vpath,
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
            "extra_material_refs": [speed_id, ph_id],  # transition id appended (if any), then scm
        }

        # Transition after this segment if there's a next one
        if idx < len(media) - 1 and catalog:
            t = choose_transition(catalog, policy, rr_idx=rr); rr += 1
            dur_ms = clamp_transition_duration_ms(t, policy.get("max_duration_ms", t.get("default_duration_ms", 600)))
            trans_id = gen_uuid(False)

            # Build a path from template, then resolve to the HASH folder if present
            raw_path = t.get("path_template", "")
            eff_id = str(t.get("effect_id", ""))
            if raw_path and "{effect_id}" in raw_path:
                raw_path = raw_path.replace("{effect_id}", eff_id)

            resolved_path, dbg = _resolve_transition_effect_path(raw_path)

            mats["transitions"].append({
                "id": trans_id,
                "type": "transition",
                "name": t.get("name"),
                "effect_id": eff_id,
                "resource_id": str(t.get("resource_id", eff_id)),
                "third_resource_id": str(t.get("third_resource_id", eff_id)),
                "category_id": str(t.get("category_id", "")),
                "category_name": t.get("category_name", ""),
                "is_overlap": bool(t.get("is_overlap", True)),
                "duration": ms_to_us(dur_ms),
                "platform": t.get("platform", "all"),
                "source_platform": int(t.get("source_platform", 1)),
                "path": resolved_path,  # <- use the resolved deep folder or ''
                "material_is_purchased": str(t.get("material_is_purchased", "1")),
                "is_vip": bool(t.get("is_vip", False)),
            })
            seg["extra_material_refs"].append(trans_id)

            # Debug record for summary
            dc["_transitions_debug"].append({
                "index": idx,
                "transition_id": trans_id,
                "name": t.get("name"),
                "effect_id": eff_id,
                "duration_ms": int(dur_ms),
                "given_path": raw_path,
                "resolved_path": resolved_path,
                "path_exists": bool(resolved_path),
                **{k: v for k, v in dbg.items() if k in ("has_config","has_extra","has_content","has_main_scene")}
            })

        seg["extra_material_refs"].append(scm_id)
        main_track["segments"].append(seg)
        timeline_end = max(timeline_end, start_us + dur_us)

    # AUDIO: true length, editable tail, proper extras, and link to import
    audio_end = 0
    if sounds:
        a0 = sounds[0]
        apath = Path(a0["path"]).resolve()
        audio_us = probe_audio_duration_us(apath)
        if not audio_us or audio_us <= 0:
            audio_us = max(timeline_end, 30 * MICROS_PER_SEC)

        speed_id = _new_speed(mats)
        ph_id    = _new_placeholder(mats)
        beats_id = _new_beats(mats)
        scm_id   = _new_sound_channel_mapping(mats)
        vs_id    = _new_vocal_separation(mats)

        amid = gen_uuid(False)
        aseg = gen_uuid(False)

        mats["audios"].append({
            "id": amid,
            "type": "extract_music",
            "name": apath.name,
            "path": str(apath),
            "duration": int(audio_us),
            "category_id": "",
            "category_name": "local",
            "check_flag": 1,
            "local_material_id": a0["material_id"],
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
