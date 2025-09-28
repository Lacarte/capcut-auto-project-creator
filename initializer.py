# initializer.py
from __future__ import annotations
from typing import Dict, Any, List, Tuple
from pathlib import Path
import json
import yaml
from jsonfiller import import_sfx_folder

from operations import list_media_files, now_epoch_ms
from jsonfiller import (
    load_json,
    save_json,
    copy_templates,
    ingest_media_into_meta_and_store,
    build_timeline_using_templates,
)
from synchronizer import sync_all


# ------------------------- config & naming -------------------------

def load_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def timestamped_name(pattern: str) -> str:
    return pattern.replace("{timestamp}", str(now_epoch_ms()))

def generate_project_name(pattern: str) -> str:
    """
    Supports:
      - {timestamp}  -> ms since epoch
      - {rand4}      -> 4 digits
      - {rand:N}     -> N digits
    """
    import random, re
    def repl(m):
        token = m.group(1)
        if token == "timestamp":
            return str(now_epoch_ms())
        if token == "rand4":
            return f"{random.randint(0, 9999):04d}"
        if token.startswith("rand:"):
            try:
                n = int(token.split(":")[1])
                return f"{random.randint(0, 10**n - 1):0{n}d}"
            except Exception:
                return token
        return token
    return re.sub(r"\{([^{}]+)\}", repl, pattern)


# ------------------------- filesystem helpers -------------------------

def prepare_out_dir(out_root: Path, project_name: str) -> Path:
    proj_dir = out_root / project_name
    proj_dir.mkdir(parents=True, exist_ok=True)
    return proj_dir

def ensure_required_structure(proj_dir: Path) -> None:
    # create CapCut-required scaffolding (even if empty)
    required_structure = [
        ".locked",
        "adjust_mask",
        "common_attachment",
        "draft_settings",
        "matting",
        "qr_upload",
        "Resources",
        "Resources/audioAlg",
        "Resources/videoAlg",
        "smart_crop",
        "subdraft",
    ]
    for d in required_structure:
        (proj_dir / d).mkdir(parents=True, exist_ok=True)


# ------------------------- reporting helpers -------------------------

def _extract_picked_transitions(dc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Infer the chosen transitions by:
      1) Building a lookup of materials.transitions by id
      2) Scanning the main video track segments; for each cut i→i+1,
         check if seg[i].extra_material_refs contains a transition id.
    Returns a list with stable, human-friendly info:
      [{index, from_segment_id, to_segment_id, name, effect_id, duration_us, is_overlap}, ...]
    """
    mats = (dc or {}).get("materials", {})
    trans_lookup = {t.get("id"): t for t in mats.get("transitions", []) if isinstance(t, dict) and t.get("id")}
    if not trans_lookup:
        return []

    # main video track (first 'video' track)
    tracks = (dc or {}).get("tracks", [])
    video_track = next((t for t in tracks if t.get("type") == "video"), None)
    if not video_track:
        return []

    segs = video_track.get("segments", []) or []
    out: List[Dict[str, Any]] = []
    for i in range(max(0, len(segs) - 1)):
        seg = segs[i]
        next_seg = segs[i + 1]
        refs = seg.get("extra_material_refs", []) or []
        # find the first ref that matches a transition id
        tid = next((r for r in refs if isinstance(r, str) and r in trans_lookup), None)
        if not tid:
            continue
        t = trans_lookup[tid]
        out.append({
            "index": i,  # transition sits between segment i and i+1
            "from_segment_id": seg.get("id"),
            "to_segment_id": next_seg.get("id"),
            "name": t.get("name"),
            "effect_id": t.get("effect_id"),
            "duration_us": t.get("duration"),
            "is_overlap": bool(t.get("is_overlap", True)),
        })
    return out


# ------------------------- pipeline -------------------------

def run_pipeline(cfg_path: Path, project_name: str | None = None) -> Dict[str, Any]:
    cfg_path = Path(cfg_path).resolve()
    cfg = load_config(cfg_path)

    # Name
    pattern = cfg["project"]["name_pattern"]
    project_name = project_name or generate_project_name(pattern)

    # Resolve paths relative to YAML location
    base = cfg_path.parent
    images_dir = (base / cfg["paths"]["images_dir"]).resolve()
    sounds_dir = (base / cfg["paths"]["sounds_dir"]).resolve()
    out_root   = (base / cfg["paths"]["out_root"]).resolve()

    t_dc   = (base / cfg["paths"]["template_draft_content"]).resolve()
    t_dmi  = (base / cfg["paths"]["template_draft_meta_info"]).resolve()
    t_dvs  = (base / cfg["paths"]["template_draft_virtual_store"]).resolve()
    t_kv   = (base / cfg["paths"].get("key_value_map", "")).resolve() if cfg["paths"].get("key_value_map") else None
    t_trans = (base / cfg["paths"].get("transitions_catalog", "")).resolve() if cfg["paths"].get("transitions_catalog") else None

    # Validate templates
    for pth, label in [(t_dc, 'template_draft_content'), (t_dmi, 'template_draft_meta_info'), (t_dvs, 'template_draft_virtual_store')]:
        if not pth.exists():
            raise FileNotFoundError(f"Missing template: {label} -> {pth}")

    # Prepare project dir + scaffold
    proj_dir = prepare_out_dir(out_root, project_name)
    ensure_required_structure(proj_dir)

    # Copy templates into the project dir
    tpl_paths = {"draft_content": t_dc, "draft_meta_info": t_dmi, "draft_virtual_store": t_dvs}
    concrete = copy_templates(tpl_paths, proj_dir)

    # Load working JSONs
    dc  = load_json(concrete["draft_content"])
    dmi = load_json(concrete["draft_meta_info"])
    dvs = load_json(concrete["draft_virtual_store"])

    # Load transitions catalog (as DB)
    catalog: List[Dict[str, Any]] = []
    if t_trans and t_trans.exists():
        try:
            catalog = json.loads(t_trans.read_text(encoding="utf-8")).get("transitions", [])
        except Exception:
            catalog = []

    # Stages
    # 1) Scan
    if cfg["stages"].get("scan_assets", True):
        assets = list_media_files(images_dir, sounds_dir)
    else:
        assets = {"media": [], "sounds": []}

    # 2) Import media (CRUD into meta/store buckets)
    if cfg["stages"].get("import_media", True):
        dmi, dvs, media_entries, sound_entries = ingest_media_into_meta_and_store(
            dmi, dvs, assets["media"], assets["sounds"]
        )
    else:
        media_entries, sound_entries = [], []

    # 3) Build timeline + transitions (template-faithful)
    if cfg["stages"].get("build_timeline", True):
        dc = build_timeline_using_templates(
            dc=dc,
            media=media_entries,
            sounds=sound_entries,
            catalog=catalog,
            policy=cfg["project"]["transition_policy"],
            image_duration_ms=cfg["project"]["image_duration_ms"],
        )

    # Extract picked transitions for the summary (from assembled DC)
    transitions_picked = _extract_picked_transitions(dc)
    transitions_debug = dc.get("_transitions_debug", [])
    dmi, dvs = import_sfx_folder(dmi, dvs, assets_root="assets")

    # 4) Sync & save
    if cfg["stages"].get("sync_and_save", True):
        dc, dmi, dvs = sync_all(
            draft_content=dc,
            draft_meta_info=dmi,
            draft_virtual_store=dvs,
            ops={},  # reserved for future doctor/ops info
            project_name=project_name,
            project_dir=str(proj_dir),
            force_meta_name=True,
        )
        save_json(dc,  concrete["draft_content"])
        save_json(dmi, concrete["draft_meta_info"])
        save_json(dvs, concrete["draft_virtual_store"])

    # Summary (include transitions we actually inserted)

    summary = {
    "project_dir": str(proj_dir),
    "files": {k: str(v) for k, v in concrete.items()},
    "assets": {
        "media":  [str(p) for p in assets["media"]],
        "sounds": [str(p) for p in assets["sounds"]],
    },
    "transitions_loaded": len(catalog),
    "transitions_picked": transitions_picked,
    "transitions_paths": transitions_debug,   # <-- shows path + path_exists per cut
    "name": project_name,
    }

    (proj_dir / "build-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
