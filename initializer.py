"""
Initializer & stage pipeline for CapCut Auto Project Creator.

This file fixes the NameError by ensuring STAGE_REGISTRY is defined **after**
all stage classes. It also keeps a single canonical Context and consistent
use of ctx.config.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional, Protocol
import shutil
import json
import time
import re
import logging

import yaml

logger = logging.getLogger(__name__)

# =========================
# Context
# =========================

@dataclass
class Context:
    """Shared pipeline state container."""

    # Loaded YAML configuration
    config: Dict[str, Any] = field(default_factory=dict)

    # Back-compat alias used by some older stages (safe to keep)
    cfg: Dict[str, Any] = field(default_factory=dict)

    # Derived name & directories
    project_name: Optional[str] = None
    project_dir: Optional[Path] = None

    # Baseline JSON dicts loaded from the template directory
    baselines: Dict[str, Any] = field(default_factory=dict)  # keys: draft_content, draft_meta_info, draft_virtual_store

    # Discovered assets (legacy image/audio flow expected by jsonfiller)
    images: List[Path] = field(default_factory=list)
    sounds: List[Path] = field(default_factory=list)

    # Cross refs & timeline cache
    idmaps: Dict[str, Any] = field(default_factory=dict)      # id maps returned by jsonfiller.add_imports
    timeline: Dict[str, Any] = field(default_factory=dict)    # layout summary from jsonfiller.build_timeline/apply_transitions

    # Outputs/diagnostics
    ops: Dict[str, Any] = field(default_factory=dict)
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    # Resolved useful paths
    template_dir: Optional[Path] = None
    out_root: Optional[Path] = None
    draft_content_path: Optional[Path] = None
    draft_meta_info_path: Optional[Path] = None
    draft_virtual_store_path: Optional[Path] = None
    operations_path: Optional[Path] = None
    doctor_report_path: Optional[Path] = None


# =========================
# Stage Protocol / Base
# =========================

class Stage(Protocol):
    @classmethod
    def name(cls) -> str: ...
    def run(self, ctx: Context, cli_overrides: Dict[str, Any] | None = None) -> Context: ...


class StageBase:
    @classmethod
    def name(cls) -> str:
        return getattr(cls, "__name__", "stage").replace("Stage", "").lower()

    def run(self, ctx: Context, cli_overrides: Dict[str, Any] | None = None) -> Context:
        raise NotImplementedError


# =========================
# Helpers
# =========================

def _abs(p: Path | str) -> Path:
    return Path(p).expanduser().resolve()


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _copytree(src: Path, dst: Path) -> None:
    if dst.exists():
        return
    shutil.copytree(src, dst)


def _load_yaml(p: Path) -> Dict[str, Any]:
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_json(p: Path) -> Dict[str, Any]:
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json_atomic(p: Path, data: Dict[str, Any]) -> None:
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(p)


def _backup_if_exists(p: Path) -> None:
    if not p.exists():
        return
    bak = p.with_suffix(p.suffix + ".bak")
    try:
        if bak.exists():
            bak.unlink()
        shutil.copy2(p, bak)
    except Exception:
        logger.warning("Could not create backup for %s", p)


def _natural_sort_key(path: Path) -> tuple[int, str]:
    """Sort by trailing number in the stem if present (1,2,10…), then name"""
    m = re.search(r"(\d+)$", path.stem)
    return (int(m.group(1)) if m else 10**9, path.name.lower())


# =========================
# Stages
# =========================

class load_configStage(StageBase):
    """1) Parse YAML, normalize paths, set defaults, generate a project name."""

    def __init__(self, config_path: Path):
        self.config_path = _abs(config_path)

    def run(self, ctx: Context, cli_overrides: Dict[str, Any] | None = None) -> Context:
        cfg = _load_yaml(self.config_path)

        # Allow CLI to override project_root if provided
        if cli_overrides and cli_overrides.get("project_root"):
            cfg["project_root"] = cli_overrides["project_root"]

        # Resolve key paths
        template_dir = _abs(Path(cfg.get("template_dir", "./template-config")))
        out_root = _abs(Path(cfg.get("project_root", "."))) / "out"
        _ensure_dir(out_root)

        # Generate project name if none supplied yet
        ts = int(time.time()) % 9999
        project_name = cfg.get("project_name") or f"T{ts:04d}"

        # Attach to context (both new and legacy fields)
        ctx.config = cfg
        ctx.cfg = cfg  # back-compat for older stages
        ctx.template_dir = template_dir
        ctx.out_root = out_root
        ctx.project_name = project_name

        logger.info("Config loaded. template_dir=%s out_root=%s project_name=%s", template_dir, out_root, project_name)
        return ctx


class prepare_project_dirStage(StageBase):
    """2) Create the output project directory and load template JSON baselines."""

    def run(self, ctx: Context, cli_overrides: Dict[str, Any] | None = None) -> Context:
        if not ctx.template_dir or not ctx.out_root:
            raise RuntimeError("Template or out_root not set (load_config must run first).")

        project_dir = ctx.out_root / (ctx.project_name or "T0000")
        _ensure_dir(ctx.out_root)
        if not project_dir.exists():
            _copytree(ctx.template_dir, project_dir)
        ctx.project_dir = project_dir

        # Where we will write
        ctx.draft_content_path = project_dir / "draft_content.json"
        ctx.draft_meta_info_path = project_dir / "draft_meta_info.json"
        ctx.draft_virtual_store_path = project_dir / "draft_virtual_store.json"
        ctx.operations_path = project_dir / "operations.json"
        ctx.doctor_report_path = project_dir / "doctor_report.json"

        # Load baselines FROM TEMPLATE (not from project dir)
        tmpl_dc = ctx.template_dir / "draft_content.json"
        tmpl_dmi = ctx.template_dir / "draft_meta_info.json"
        tmpl_dvs = ctx.template_dir / "draft_virtual_store.json"
        ctx.baselines = {
            "draft_content": _load_json(tmpl_dc) if tmpl_dc.exists() else {},
            "draft_meta_info": _load_json(tmpl_dmi) if tmpl_dmi.exists() else {},
            "draft_virtual_store": _load_json(tmpl_dvs) if tmpl_dvs.exists() else {},
        }

        # Ensure required structure directories/files (from YAML)
        for rel in ctx.config.get("required_structure", []):
            _ensure_dir(project_dir / rel)

        logger.info("Prepared project dir: %s", project_dir)
        return ctx


class scan_assetsStage(StageBase):
    """3) Discover images & sounds; natural numeric order."""

    def run(self, ctx: Context, cli_overrides: Dict[str, Any] | None = None) -> Context:
        a = ctx.config.get("assets", {})
        images_dir_raw = a.get("images_dir", "assets/images")
        sounds_dir_raw = a.get("sounds_dir", "assets/sounds")
        img_exts = set(e.lower() for e in a.get("image_extensions", [".jpg", ".jpeg", ".png", ".webp"]))
        snd_exts = set(e.lower() for e in a.get("sound_extensions", [".mp3", ".m4a", ".wav"]))

        images_dir = _abs(images_dir_raw)
        sounds_dir = _abs(sounds_dir_raw)

        if images_dir.exists():
            imgs = [p for p in images_dir.iterdir() if p.is_file() and p.suffix.lower() in img_exts]
            imgs.sort(key=_natural_sort_key)
            ctx.images = imgs
            logger.info("Found %d image(s) in %s", len(imgs), images_dir)
        else:
            logger.warning("Images dir not found: %s", images_dir)

        if sounds_dir.exists():
            snds = [p for p in sounds_dir.iterdir() if p.is_file() and p.suffix.lower() in snd_exts]
            snds.sort(key=_natural_sort_key)
            ctx.sounds = snds
            logger.info("Found %d sound(s) in %s", len(snds), sounds_dir)
        else:
            logger.info("Sounds dir not found: %s", sounds_dir)
        return ctx


class import_mediaStage(StageBase):
    """4) Populate meta & virtual_store using jsonfiller.add_imports (images/sounds)."""

    def run(self, ctx: Context, cli_overrides: Dict[str, Any] | None = None) -> Context:
        from jsonfiller import add_imports  # uses image/audio lists
        dmi = ctx.baselines.get("draft_meta_info", {})
        dvs = ctx.baselines.get("draft_virtual_store", {})
        images = [str(p) for p in ctx.images]
        sounds = [str(p) for p in ctx.sounds]

        dmi2, dvs2, idmaps = add_imports(dmi, dvs, images, sounds)
        ctx.baselines["draft_meta_info"] = dmi2
        ctx.baselines["draft_virtual_store"] = dvs2
        ctx.idmaps = idmaps or {}
        logger.info("Imported media: images=%d sounds=%d", len(images), len(sounds))
        return ctx


class build_timelineStage(StageBase):
    """5) Create materials & tracks using jsonfiller.build_timeline."""

    def run(self, ctx: Context, cli_overrides: Dict[str, Any] | None = None) -> Context:
        from jsonfiller import build_timeline
        tl = ctx.config.get("timeline", {})
        default_ms = int(tl.get("default_image_duration_ms", 5000))
        ordering = tl.get("ordering", "numeric")

        dc0 = ctx.baselines.get("draft_content", {})
        images = [str(p) for p in ctx.images]
        sounds = [str(p) for p in ctx.sounds]
        dc1, timeline_cache = build_timeline(dc0, images, sounds, default_ms, ordering=ordering, idmaps=ctx.idmaps)
        ctx.baselines["draft_content"] = dc1
        ctx.timeline = timeline_cache or {}
        logger.info("Timeline built with %d clip(s).", len(ctx.timeline.get("clips", [])))
        return ctx


class apply_transitionsStage(StageBase):
    """6) Apply real transitions with proper CapCut formatting and cache paths."""

    def run(self, ctx: Context, cli_overrides: Dict[str, Any] | None = None) -> Context:
        from jsonfiller import apply_transitions
        tr = ctx.config.get("transitions", {})
        
        # Extract transition configuration
        catalog = tr.get("catalog", [])
        prob = float(tr.get("per_cut_probability", 0.0))
        dur_rng = tr.get("duration_ms_range", [800, 1200])
        cache_root = tr.get("cache_root", "")
        
        if not isinstance(dur_rng, (list, tuple)) or len(dur_rng) != 2:
            dur_rng = [800, 1200]
            
        # Build transition config dict
        transition_config = {
            "catalog": catalog,
            "cache_root": cache_root
        }
        
        dc1, timeline_cache = apply_transitions(
            ctx.baselines["draft_content"],
            ctx.timeline,
            transition_config,
            prob,
            (int(dur_rng[0]), int(dur_rng[1])),
        )
        ctx.baselines["draft_content"] = dc1
        ctx.timeline = timeline_cache or ctx.timeline
        
        logger.info("Transitions applied (catalog=%d effects, p=%.2f).", len(catalog), prob)
        return ctx


class operationsStage(StageBase):
    """7) Compute operations payload (summary info for synchronizer/doctor)."""

    def run(self, ctx: Context, cli_overrides: Dict[str, Any] | None = None) -> Context:
        from operations import compute_operations
        now_us = int(time.time() * 1_000_000)
        ctx.ops = compute_operations(
            ctx.baselines.get("draft_content", {}),
            ctx.baselines.get("draft_meta_info", {}),
            ctx.baselines.get("draft_virtual_store", {}),
            ctx.timeline,
            ctx.idmaps,
            now_us,
        )
        return ctx


class synchronizerStage(StageBase):
    """8) Sync draft_name/draft_fold_path and mirror metadata."""

    def run(self, ctx: Context, cli_overrides: Dict[str, Any] | None = None) -> Context:
        from synchronizer import sync_all
        dc, dmi, dvs = sync_all(
            ctx.baselines.get("draft_content", {}),
            ctx.baselines.get("draft_meta_info", {}),
            ctx.baselines.get("draft_virtual_store", {}),
            ctx.ops,
            ctx.project_name or "T0000",
            str(ctx.project_dir) if ctx.project_dir else None,
            True,
        )
        ctx.baselines["draft_content"] = dc
        ctx.baselines["draft_meta_info"] = dmi
        ctx.baselines["draft_virtual_store"] = dvs
        return ctx


class doctorStage(StageBase):
    """9) Validate JSON integrity; autofix (YAML or CLI --fix)."""

    def run(self, ctx: Context, cli_overrides: Dict[str, Any] | None = None) -> Context:
        from doctor import inspect_and_fix
        cfg = ctx.config.get("doctor", {})
        autofix_yaml = bool(cfg.get("autofix", True))
        strict = bool(cfg.get("strict", True))
        autofix_cli = bool(cli_overrides and cli_overrides.get("doctor_autofix"))
        report = inspect_and_fix(
            draft_content=ctx.baselines.get("draft_content", {}),
            draft_meta_info=ctx.baselines.get("draft_meta_info", {}),
            draft_virtual_store=ctx.baselines.get("draft_virtual_store", {}),
            strict=strict,
            autofix=(autofix_cli or autofix_yaml),
        )
        ctx.diagnostics = report or {}
        logger.info("Doctor finished. issues=%s", len(ctx.diagnostics.get("issues", [])))
        return ctx


class write_jsonStage(StageBase):
    """10) Write JSON triplet + ops + doctor report (atomic + optional backups)."""

    def run(self, ctx: Context, cli_overrides: Dict[str, Any] | None = None) -> Context:
        if not ctx.project_dir:
            raise RuntimeError("Project directory not prepared.")

        adv = ctx.config.get("advanced", {})
        do_backup = bool(adv.get("backup_on_overwrite", True))

        # Targets
        dc_p = ctx.draft_content_path or (ctx.project_dir / "draft_content.json")
        dmi_p = ctx.draft_meta_info_path or (ctx.project_dir / "draft_meta_info.json")
        dvs_p = ctx.draft_virtual_store_path or (ctx.project_dir / "draft_virtual_store.json")
        ops_p = ctx.operations_path or (ctx.project_dir / "operations.json")
        doc_p = ctx.doctor_report_path or (ctx.project_dir / "doctor_report.json")

        if do_backup:
            for p in (dc_p, dmi_p, dvs_p, ops_p, doc_p):
                _backup_if_exists(p)

        _save_json_atomic(dc_p, ctx.baselines.get("draft_content", {}))
        _save_json_atomic(dmi_p, ctx.baselines.get("draft_meta_info", {}))
        _save_json_atomic(dvs_p, ctx.baselines.get("draft_virtual_store", {}))
        _save_json_atomic(ops_p, ctx.ops or {})
        _save_json_atomic(doc_p, ctx.diagnostics or {})

        logger.info("Wrote JSON files to %s", ctx.project_dir)
        return ctx


# =========================
# Builder & Registry (MUST be after class definitions)
# =========================

def build_pipeline(config_path: Path) -> Tuple[List[StageBase], Context]:
    stages: List[StageBase] = [
        load_configStage(config_path),
        prepare_project_dirStage(),
        scan_assetsStage(),
        import_mediaStage(),
        build_timelineStage(),
        apply_transitionsStage(),
        operationsStage(),
        synchronizerStage(),
        doctorStage(),
        write_jsonStage(),
    ]
    return stages, Context()


# Exported registry for CLI help and external selection
STAGE_REGISTRY: Dict[str, type] = {
    load_configStage.name(): load_configStage,
    prepare_project_dirStage.name(): prepare_project_dirStage,
    scan_assetsStage.name(): scan_assetsStage,
    import_mediaStage.name(): import_mediaStage,
    build_timelineStage.name(): build_timelineStage,
    apply_transitionsStage.name(): apply_transitionsStage,
    operationsStage.name(): operationsStage,
    synchronizerStage.name(): synchronizerStage,
    doctorStage.name(): doctorStage,
    write_jsonStage.name(): write_jsonStage,
}

__all__ = [
    "Context",
    "Stage",
    "StageBase",
    "build_pipeline",
    "STAGE_REGISTRY",
]