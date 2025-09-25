#!/usr/bin/env python3
"""
capcut_pipeline.py
------------------
Context-driven, composable pipeline for creating CapCut projects.

Each stage accepts & returns a single `Context` object, enabling you to run
the full pipeline or any slice (e.g., only import images, only build timeline).

Stages implemented (in order):
  1) LOAD_CONFIG_AND_STRUCTURE
  2) IMPORT_MEDIA_TO_META
  3) BUILD_VIRTUAL_STORE
  4) BUILD_TIMELINE_CONTENT
  5) ADD_TRANSITIONS
  6) DOCTOR_DIAGNOSE_OR_FIX (optional)

Usage examples:
  # Full pipeline (auto name from config or random like "T8812")
  python capcut_pipeline.py --config capcut_creator_config.yaml --all

  # Only (2)->(4): import images and build timeline (no transitions)
  python capcut_pipeline.py --config capcut_creator_config.yaml \
      --stages IMPORT_MEDIA_TO_META BUILD_VIRTUAL_STORE BUILD_TIMELINE_CONTENT --no-transitions

  # Diagnose or fix an existing project directory
  python capcut_pipeline.py --project T8812 --stages DOCTOR_DIAGNOSE_OR_FIX --diagnose
  python capcut_pipeline.py --project T8812 --stages DOCTOR_DIAGNOSE_OR_FIX --fix

Requirements:
  - capcut_draft_utils.py
  - capcut_virtual_store_utils.py
  - capcut_content_utils.py
  - capcut_transitions_utils.py (optional if you skip transitions)
  - capcut_project_doctor.py (for DOCTOR stage)
  - PyYAML (pip install pyyaml)
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import shutil
import string
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

# 3rd party (optional but recommended)
try:
    import yaml  # type: ignore
except Exception:
    yaml = None

# Local helpers provided by your project (already uploaded)
import capcut_draft_utils as meta_utils
import capcut_virtual_store_utils as store_utils
from capcut_content_utils import sync_timeline_from_meta, load_content
try:
    from capcut_transitions_utils import add_transitions_to_content
except Exception:
    add_transitions_to_content = None  # Transitions can be skipped

# Always-on ID sync
try:
    from comprehensive_id_sync_fixer import CapCutIDSynchronizer
except Exception:
    CapCutIDSynchronizer = None

# ---------------------------- Logging ---------------------------------------
logger = logging.getLogger("capcut.pipeline")

def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

# ---------------------------- Context ---------------------------------------

@dataclass
class Context:
    # Configurable inputs
    config_path: Optional[Path] = None
    project_name: Optional[str] = None
    project_root: Path = Path('.')
    template_dir: Path = Path('template-config')
    images_dir: Path = Path('assets/images')

    # Runtime flags
    include_placeholder: bool = True
    add_transitions_flag: bool = True
    transition_name: str = "Pull in"
    transition_duration_us: int = 466_666
    transition_is_overlap: bool = False
    per_image_duration_us: int = 5_000_000
    auto_id_sync: bool = True  # NEW: always run ID sync fixer unless disabled

    # Doctor flags
    doctor_mode: Optional[str] = None  # "diagnose" | "fix" | None

    # Derived paths
    project_path: Optional[Path] = None
    meta_path: Optional[Path] = None
    store_path: Optional[Path] = None
    content_path: Optional[Path] = None

    # Loaded / computed data snapshots
    yaml_config: Dict[str, Any] = field(default_factory=dict)
    meta_json: Dict[str, Any] = field(default_factory=dict)
    store_json: Dict[str, Any] = field(default_factory=dict)
    content_json: Dict[str, Any] = field(default_factory=dict)

    images: List[Path] = field(default_factory=list)
    material_ids_in_meta: List[str] = field(default_factory=list)

    # Simple report info
    notes: List[str] = field(default_factory=list)

# ---------------------------- Stages Enum -----------------------------------

class Stage(Enum):
    LOAD_CONFIG_AND_STRUCTURE = auto()
    IMPORT_MEDIA_TO_META = auto()
    BUILD_VIRTUAL_STORE = auto()
    BUILD_TIMELINE_CONTENT = auto()
    ADD_TRANSITIONS = auto()
    ALWAYS_ID_SYNC = auto()
    DOCTOR_DIAGNOSE_OR_FIX = auto()

# ---------------------------- Utility funcs ---------------------------------

def _gen_project_name(prefix_letter: str = None) -> str:
    letter = (prefix_letter or random.choice(string.ascii_uppercase))[:1]
    number = random.randint(0, 9999)
    return f"{letter}{number:04d}"

def _collect_images(images_dir: Path) -> List[Path]:
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    if not images_dir.exists():
        return []
    files = [p for p in images_dir.iterdir() if p.is_file() and p.suffix.lower() in exts]
    def key(p: Path):
        try:
            return (0, int(p.stem))
        except ValueError:
            return (1, p.stem)
    files.sort(key=key)
    return files

# ---------------------------- Stage Impl ------------------------------------

def stage_load_config_and_structure(ctx: Context) -> Context:
    # 1) Load YAML
    if ctx.config_path and ctx.config_path.exists():
        if yaml is None:
            raise RuntimeError("PyYAML not installed. Run: pip install pyyaml")
        with ctx.config_path.open('r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
        ctx.yaml_config = cfg
        logger.info(f"Loaded config: {ctx.config_path}")
    else:
        logger.info("No config file provided or not found; using defaults")

    # Derive from config (w/ fallbacks)
    cfg = ctx.yaml_config
    ctx.project_root = Path(cfg.get('project_root', ctx.project_root))
    ctx.template_dir = Path(cfg.get('template_dir', ctx.template_dir))
    ctx.images_dir = Path(cfg.get('images_dir', ctx.images_dir))

    ctx.include_placeholder = bool(cfg.get('include_placeholder', ctx.include_placeholder))
    media_cfg = cfg.get('media', {}) or {}
    ctx.per_image_duration_us = int(media_cfg.get('per_image_duration_us', ctx.per_image_duration_us))

    trans_cfg = cfg.get('transitions', {}) or {}
    ctx.add_transitions_flag = bool(trans_cfg.get('enabled', ctx.add_transitions_flag))
    ctx.transition_name = str(trans_cfg.get('name', ctx.transition_name))
    ctx.transition_duration_us = int(trans_cfg.get('duration_us', ctx.transition_duration_us))
    ctx.transition_is_overlap = bool(trans_cfg.get('is_overlap', ctx.transition_is_overlap))

    # Project name
    ctx.project_name = ctx.project_name or cfg.get('project_name') or _gen_project_name(cfg.get('project_prefix', 'T'))

    # Create project directory + required structure from template
    ctx.project_root.mkdir(parents=True, exist_ok=True)
    ctx.project_path = ctx.project_root / ctx.project_name
    if ctx.project_path.exists():
        logger.info(f"Project exists: {ctx.project_path}")
    else:
        ctx.project_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created project folder: {ctx.project_path}")

    # Copy template-config tree (files & dirs)
    if ctx.template_dir.exists():
        for entry in ctx.template_dir.iterdir():
            src = entry
            dst = ctx.project_path / entry.name
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        logger.info(f"Copied template-config into project: {ctx.template_dir}")
    else:
        logger.warning(f"template_dir not found: {ctx.template_dir}")

    # Set main json paths
    ctx.meta_path = ctx.project_path / 'draft_meta_info.json'
    ctx.store_path = ctx.project_path / 'draft_virtual_store.json'
    ctx.content_path = ctx.project_path / 'draft_content.json'

    # Update draft_meta_info basic fields if present
    if ctx.meta_path.exists():
        meta = meta_utils.load_draft(ctx.meta_path)
        meta['draft_name'] = ctx.project_name
        meta['creation_timestamp'] = datetime.now().isoformat()
        meta['tm_draft_modified'] = int(datetime.now().timestamp() * 1_000_000)
        meta_utils.save_draft(meta, ctx.meta_path)
        ctx.meta_json = meta
        logger.info("Updated draft_meta_info.json with project name & timestamps")
    else:
        logger.warning("draft_meta_info.json missing in template; stages can still proceed after import")

    # Load images list now for convenience
    ctx.images = _collect_images(ctx.images_dir)
    logger.info(f"Images discovered: {len(ctx.images)} in {ctx.images_dir}")

    ctx.notes.append("Structure ready")
    return ctx


def stage_import_media_to_meta(ctx: Context) -> Context:
    if not ctx.meta_path or not ctx.meta_path.exists():
        raise FileNotFoundError(f"meta json not found: {ctx.meta_path}")
    if not ctx.images:
        logger.warning("No images to import; skipping")
        return ctx

    meta = meta_utils.load_draft(ctx.meta_path)
    for idx, img in enumerate(ctx.images):
        meta_utils.add_image_to_draft(
            meta,
            img.resolve(),
            duration_us=ctx.per_image_duration_us,
            include_placeholder_if_first=(ctx.include_placeholder and idx == 0),
        )
    meta_utils.save_draft(meta, ctx.meta_path)
    ctx.meta_json = meta
    logger.info(f"Imported {len(ctx.images)} image(s) into draft_meta_info.json")

    # Capture ordered material ids (including placeholder first if present)
    ids = store_utils.extract_image_material_ids_from_meta(meta)
    ctx.material_ids_in_meta = ids
    logger.debug(f"Material IDs in meta: {ids}")

    ctx.notes.append("Media imported to meta")
    return ctx


def stage_build_virtual_store(ctx: Context) -> Context:
    if not ctx.material_ids_in_meta:
        # lazy extract if previous stage wasn't run in this session
        if ctx.meta_json:
            ids = store_utils.extract_image_material_ids_from_meta(ctx.meta_json)
        elif ctx.meta_path and ctx.meta_path.exists():
            ids = store_utils.extract_image_material_ids_from_meta(store_utils.load_json(ctx.meta_path))
        else:
            raise RuntimeError("Cannot build virtual store: no meta available")
        ctx.material_ids_in_meta = ids

    store = store_utils.build_virtual_store(ctx.material_ids_in_meta)
    store_utils.save_json(store, ctx.store_path)
    ctx.store_json = store
    logger.info(f"Virtual store built with {len(ctx.material_ids_in_meta)} link(s)")

    ctx.notes.append("Virtual store synced")
    return ctx


def stage_build_timeline_content(ctx: Context) -> Context:
    if not (ctx.content_path and ctx.meta_path):
        raise RuntimeError("Missing content/meta paths")
    if not ctx.meta_path.exists():
        raise FileNotFoundError(f"meta json not found: {ctx.meta_path}")
    if not ctx.content_path.exists():
        raise FileNotFoundError(f"content json not found: {ctx.content_path}")

    # Build timeline entirely from meta (IDs preserved)
    sync_timeline_from_meta(
        ctx.content_path,
        ctx.meta_path,
        duration_us=ctx.per_image_duration_us,
        add_transitions=False,  # transitions handled by next stage
        transition_name=ctx.transition_name,
        transition_duration_us=ctx.transition_duration_us,
        transition_is_overlap=ctx.transition_is_overlap,
    )

    # Optionally sync tm_duration back to meta
    try:
        c_json = load_content(ctx.content_path)
        ctx.content_json = c_json
        # compute duration
        total = 0
        segments = (c_json.get('tracks') or [{}])[0].get('segments', [])
        for seg in segments:
            start = int(seg['target_timerange']['start'])
            dur = int(seg['target_timerange']['duration'])
            total = max(total, start + dur)
        meta = ctx.meta_json or meta_utils.load_draft(ctx.meta_path)
        meta['tm_duration'] = total
        meta['tm_draft_modified'] = int(datetime.now().timestamp() * 1_000_000)
        meta_utils.save_draft(meta, ctx.meta_path)
        ctx.meta_json = meta
        logger.info(f"Timeline built ({len(segments)} segments), total={total} µs")
    except Exception as e:
        logger.warning(f"Post-build duration sync skipped: {e}")

    ctx.notes.append("Timeline content built")
    return ctx


def stage_add_transitions(ctx: Context) -> Context:
    if not ctx.add_transitions_flag:
        logger.info("Transitions disabled by config/flag; skipping")
        return ctx
    if add_transitions_to_content is None:
        logger.warning("capcut_transitions_utils not available; skipping transitions stage")
        return ctx
    if not (ctx.content_path and ctx.content_path.exists()):
        raise FileNotFoundError(f"content json not found: {ctx.content_path}")

    ok = add_transitions_to_content(
        ctx.content_path,
        transition_type=ctx.transition_name,
        duration_us=ctx.transition_duration_us,
        is_overlap=ctx.transition_is_overlap,
        skip_first=True,
    )
    if ok:
        logger.info("Transitions added successfully")
        ctx.notes.append("Transitions added")
    else:
        logger.warning("Failed to add transitions; continuing")
        ctx.notes.append("Transitions failed")
    return ctx


def stage_always_id_sync(ctx: Context) -> Context:
    """Always run the comprehensive ID sync fixer after content/transition build.
    Creates a backup and forces IDs to match across meta, content, and store.
    """
    if not ctx.auto_id_sync:
        logger.info("Auto ID sync disabled; skipping")
        return ctx
    if CapCutIDSynchronizer is None:
        logger.warning("comprehensive_id_sync_fixer unavailable; skipping auto ID sync")
        return ctx
    if not ctx.project_path:
        logger.warning("Project path not set; skipping auto ID sync")
        return ctx

    try:
        syncer = CapCutIDSynchronizer(ctx.project_path)
        # We can run diagnose first to log state, but we always fix per requirement
        report = syncer.diagnose()
        issues = report.get("issues", [])
        if issues:
            logger.info("Auto ID sync: pre-check found issues; running fix")
        else:
            logger.info("Auto ID sync: no issues reported; enforcing fix anyway for safety")
        ok = syncer.fix()
        if ok:
            ctx.notes.append("Auto ID sync enforced")
            logger.info("Auto ID sync completed successfully")
            # refresh in-memory snapshots
            if ctx.meta_path and ctx.meta_path.exists():
                ctx.meta_json = meta_utils.load_draft(ctx.meta_path)
            if ctx.content_path and ctx.content_path.exists():
                try:
                    ctx.content_json = load_content(ctx.content_path)
                except Exception:
                    pass
            if ctx.store_path and ctx.store_path.exists():
                try:
                    ctx.store_json = store_utils.load_json(ctx.store_path)
                except Exception:
                    pass
        else:
            ctx.notes.append("Auto ID sync failed")
            logger.warning("Auto ID sync reported failure")
    except Exception as e:
        logger.warning(f"Auto ID sync crashed: {e}")
        ctx.notes.append(f"Auto ID sync error: {e}")
    return ctx
    if add_transitions_to_content is None:
        logger.warning("capcut_transitions_utils not available; skipping transitions stage")
        return ctx
    if not (ctx.content_path and ctx.content_path.exists()):
        raise FileNotFoundError(f"content json not found: {ctx.content_path}")

    ok = add_transitions_to_content(
        ctx.content_path,
        transition_type=ctx.transition_name,
        duration_us=ctx.transition_duration_us,
        is_overlap=ctx.transition_is_overlap,
        skip_first=True,
    )
    if ok:
        logger.info("Transitions added successfully")
        ctx.notes.append("Transitions added")
    else:
        logger.warning("Failed to add transitions; continuing")
        ctx.notes.append("Transitions failed")
    return ctx


def stage_doctor(ctx: Context) -> Context:
    """Run diagnosis or fix via capcut_project_doctor or comprehensive fixer."""
    if ctx.doctor_mode not in {"diagnose", "fix"}:
        logger.info("Doctor stage requested without mode; skipping")
        return ctx

    # Prefer the newer comprehensive fixer if present
    fixer = Path(__file__).parent / 'comprehensive_id_sync_fixer.py'
    doctor = Path(__file__).parent / 'capcut_project_doctor.py'

    import subprocess, sys
    script = fixer if fixer.exists() else doctor
    if not script.exists():
        logger.warning("No doctor/fixer script found; skipping")
        return ctx

    cmd = [sys.executable, str(script), '--project', str(ctx.project_path)]
    if ctx.doctor_mode == 'diagnose':
        cmd.append('--diagnose')
    else:
        cmd.append('--fix')

    logger.info(f"Running: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=False)
        ctx.notes.append(f"Doctor executed: {ctx.doctor_mode}")
    except Exception as e:
        logger.warning(f"Doctor failed: {e}")
    return ctx

# ---------------------------- Orchestrator ----------------------------------

STAGE_FUNCS = {
    Stage.LOAD_CONFIG_AND_STRUCTURE: stage_load_config_and_structure,
    Stage.IMPORT_MEDIA_TO_META: stage_import_media_to_meta,
    Stage.BUILD_VIRTUAL_STORE: stage_build_virtual_store,
    Stage.BUILD_TIMELINE_CONTENT: stage_build_timeline_content,
    Stage.ADD_TRANSITIONS: stage_add_transitions,
    Stage.ALWAYS_ID_SYNC: stage_always_id_sync,
    Stage.DOCTOR_DIAGNOSE_OR_FIX: stage_doctor,
}

# ---------------------------- CLI ------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="CapCut Context Pipeline")
    p.add_argument('--config', type=Path, help='Path to capcut_creator_config.yaml')
    p.add_argument('--project', help='Existing project name (otherwise generated)')
    p.add_argument('--project-root', type=Path, help='Root folder for projects')
    p.add_argument('--images-dir', type=Path, help='Folder with input images')
    p.add_argument('--template-dir', type=Path, help='Template-config folder')

    p.add_argument('--duration-us', type=int, help='Per-image duration in microseconds')
    p.add_argument('--no-placeholder', action='store_true', help='Do not insert placeholder before first image')

    p.add_argument('--no-transitions', action='store_true', help='Disable transitions stage')
    p.add_argument('--transition-name', default='Pull in')
    p.add_argument('--transition-duration-us', type=int, default=466_666)
    p.add_argument('--transition-overlap', action='store_true')

    # Auto ID sync control
    p.add_argument('--no-auto-id-sync', action='store_true', help='Disable always-on ID synchronization stage')

    # Doctor controls
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--diagnose', action='store_true')
    mode.add_argument('--fix', action='store_true')

    # Stage selection
    p.add_argument('--all', action='store_true', help='Run all stages')
    p.add_argument('--stages', nargs='+', help='Specific stages to run, in order')

    p.add_argument('-v', '--verbose', action='store_true')
    return p.parse_args()


def main() -> int:
    args = parse_args()
    setup_logging(args.verbose)

    # Build initial context from CLI
    ctx = Context()
    ctx.config_path = args.config
    ...
    ctx.doctor_mode = 'diagnose' if args.diagnose else ('fix' if args.fix else None)

    # Resolve stage list
    stages: List[Stage] = []

    if args.all and args.stages:
        logger.warning("--all provided with --stages; honoring explicit --stages order")

    if args.stages:
        try:
            stages = [Stage[s] for s in args.stages]
        except KeyError as e:
            valid = ', '.join(s.name for s in Stage)
            raise SystemExit(f"Invalid stage {e}. Valid: {valid}")
    elif args.all:
        stages = [
            Stage.LOAD_CONFIG_AND_STRUCTURE,
            Stage.IMPORT_MEDIA_TO_META,
            Stage.BUILD_VIRTUAL_STORE,
            Stage.BUILD_TIMELINE_CONTENT,
            Stage.ADD_TRANSITIONS,
            Stage.ALWAYS_ID_SYNC,
            Stage.DOCTOR_DIAGNOSE_OR_FIX,
        ]
    else:
        # default minimal slice
        stages = [
            Stage.LOAD_CONFIG_AND_STRUCTURE,
            Stage.IMPORT_MEDIA_TO_META,
            Stage.BUILD_VIRTUAL_STORE,
            Stage.BUILD_TIMELINE_CONTENT,
            Stage.ADD_TRANSITIONS,
            Stage.ALWAYS_ID_SYNC,
        ]

    # Execute stages
    for st in stages:
        logger.info(f"==== Stage: {st.name} ====")
        func = STAGE_FUNCS[st]
        ctx = func(ctx)


    # Final summary
    logger.info("\nPipeline complete. Summary:")
    logger.info(f"  Project: {ctx.project_name}")
    logger.info(f"  Path:    {ctx.project_path}")
    logger.info(f"  Images:  {len(ctx.images)} imported")
    if ctx.notes:
        for note in ctx.notes:
            logger.info(f"  - {note}")

    # Print outputs (useful for scripting)
    print(f"project_name={ctx.project_name}")
    print(f"project_path={ctx.project_path}")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
