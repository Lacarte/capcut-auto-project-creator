"""
Stage pipeline & shared Context for CapCut Auto Project Creator.

Stages operate on a shared Context and can be executed independently.
Utilities expected to exist in your project:
  - jsonfiller.py      (template injectors: media, segments, transitions, audio)
  - operations.py      (timeline math, ids, timestamps)  -> produce ops dict
  - synchronizer.py    (write ops into JSONs; update draft_name/draft_fold_path)
  - doctor.py          (validate/fix JSON integrity)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any, Tuple, Type, Optional, Protocol
import shutil
import json
import time
import uuid
import re
import logging

import yaml

logger = logging.getLogger(__name__)

# ---------------- Context ----------------

@dataclass
class Context:
    # config
    cfg: Dict[str, Any] = field(default_factory=dict)

    # project identity
    project_name: Optional[str] = None
    project_dir: Optional[Path] = None

    # baselines loaded from template_dir
    baselines: Dict[str, Any] = field(default_factory=dict)   # keys: draft_content, draft_meta_info, draft_virtual_store

    # asset lists (ordered)
    images: List[Path] = field(default_factory=list)
    sounds: List[Path] = field(default_factory=list)

    # cross refs & timeline cache
    idmaps: Dict[str, Any] = field(default_factory=dict)      # asset_id -> material_id -> segment_id
    timeline: Dict[str, Any] = field(default_factory=dict)    # spans, tracks, transitions, etc.

    # outputs/diagnostics
    ops: Dict[str, Any] = field(default_factory=dict)         # operations.json
    diagnostics: Dict[str, Any] = field(default_factory=dict) # doctor report

    # resolved useful paths
    template_dir: Optional[Path] = None
    out_root: Optional[Path] = None
    operations_path: Optional[Path] = None
    doctor_report_path: Optional[Path] = None
    draft_content_path: Optional[Path] = None
    draft_meta_info_path: Optional[Path] = None
    draft_virtual_store_path: Optional[Path] = None

# ---------------- Stage protocol/base ----------------

class Stage(Protocol):
    def run(self, ctx: Context, cli_overrides: Dict[str, Any] | None = None) -> Context:
        ...

class StageBase:
    @classmethod
    def name(cls) -> str:
        # kebab-ish but simple
        return getattr(cls, "__name__", "stage").replace("Stage", "").lower()

    def run(self, ctx: Context, cli_overrides: Dict[str, Any] | None = None) -> Context:
        raise NotImplementedError

# ---------------- Helpers ----------------

def _load_yaml(p: Path) -> Dict[str, Any]:
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def _ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p

def _read_json(p: Path) -> Dict[str, Any]:
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

def _write_json_atomic(p: Path, data: Dict[str, Any]):
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(p)

def _copytree(src: Path, dst: Path):
    if dst.exists():
        return
    shutil.copytree(src, dst)

def _abs(p: Path) -> Path:
    return Path(p).expanduser().resolve()

def _timestamp_us_now() -> int:
    return int(time.time() * 1_000_000)

# ---------------- Stages ----------------

class load_configStage(StageBase):
    """1) Parse YAML, normalize paths, init RNG/IDs, set logging if provided in YAML."""
    def __init__(self, config_path: Path):
        self.config_path = _abs(config_path)

    def run(self, ctx: Context, cli_overrides: Dict[str, Any] | None = None) -> Context:
        cfg = _load_yaml(self.config_path)
        ctx.cfg = cfg

        # logging (honor YAML unless CLI overrides provided to main.py)
        lg = cfg.get("logging", {})
        fmt = lg.get("format") or "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        file_ = lg.get("file")
        level = lg.get("level", "INFO")

        # If main.py passed overrides, they’re already applied there.

        # Resolve dirs
        template_dir = _abs(Path(cfg.get("template_dir", "./template-config")))
        out_root = _abs(Path(cfg.get("project_root", "."))) / "out"
        _ensure_dir(out_root)

        ctx.template_dir = template_dir
        ctx.out_root = out_root

        # Naming pattern
        naming = cfg.get("naming", {})
        pattern = naming.get("pattern", "^[A-Z]\\d{4}$")
        examples = naming.get("examples", ["T0001", "T1234"])

        # Generate a name if not provided later
        # We’ll generate simple letter + 4 digits by time-based hash
        ts = int(time.time()) % 9999
        prefix = "T"
        generated = f"{prefix}{ts:04d}"
        ctx.project_name = generated

        logger.info("Config loaded. template_dir=%s out_root=%s project_name=%s",
                    template_dir, out_root, ctx.project_name)
        return ctx


class prepare_project_dirStage(StageBase):
    """2) Create ./out/<project>/ by copying template_dir; ensure required_structure."""
    def run(self, ctx: Context, cli_overrides: Dict[str, Any] | None = None) -> Context:
        if not ctx.template_dir or not ctx.out_root:
            raise RuntimeError("Template or out_root not set (load_config must run first).")

        project_dir = ctx.out_root / ctx.project_name
        _ensure_dir(ctx.out_root)
        if not project_dir.exists():
            _copytree(ctx.template_dir, project_dir)
        ctx.project_dir = project_dir

        # Ensure required structure from YAML
        req = ctx.cfg.get("required_structure", [])
        for rel in req:
            _ensure_dir(project_dir / rel)

        # Resolve important JSON file paths
        ctx.draft_content_path = project_dir / "draft_content.json"
        ctx.draft_meta_info_path = project_dir / "draft_meta_info.json"
        ctx.draft_virtual_store_path = project_dir / "draft_virtual_store.json"
        ctx.operations_path = project_dir / "operations.json"
        ctx.doctor_report_path = project_dir / "doctor_report.json"

        # Load baselines (from template dir copies now present in project_dir)
        ctx.baselines = {
            "draft_content": _read_json(ctx.draft_content_path),
            "draft_meta_info": _read_json(ctx.draft_meta_info_path),
            "draft_virtual_store": _read_json(ctx.draft_virtual_store_path),
        }

        logger.info("Prepared project dir: %s", project_dir)
        return ctx


class scan_assetsStage(StageBase):
    """3) Scan assets/images and assets/sounds. Enforce numeric order for images."""
    IMG_EXT_DEFAULTS = [".jpg", ".jpeg", ".png", ".bmp", ".webp", ".webm"]
    SND_EXT_DEFAULTS = [".mp3", ".wav", ".m4a"]
    NUM_RX = re.compile(r"(\d+)")

    def _resolve_candidates(self, raw: str, ctx: Context) -> List[Path]:
        """
        Try multiple base directories for a given path:
          1) As given (absolute or relative to CWD)
          2) Relative to YAML file's folder (template_dir's parent is a good proxy if you keep config there)
          3) Relative to repo root (ctx.out_root.parent)
          4) Relative to the project dir (once created)
        Returns existing directories (deduped).
        """
        cand: List[Path] = []
        p = Path(raw)
        cand.append(p if p.is_absolute() else Path.cwd() / p)

        if ctx.template_dir:
            cand.append(ctx.template_dir.parent / raw)

        if ctx.out_root:
            cand.append(ctx.out_root.parent / raw)

        if ctx.project_dir:
            cand.append(ctx.project_dir / ".." / raw)

        # Dedup & keep only existing directories
        seen, out = set(), []
        for c in cand:
            rr = c.resolve()
            if rr not in seen and rr.exists():
                out.append(rr)
                seen.add(rr)
        return out

    def run(self, ctx: Context, cli_overrides: Dict[str, Any] | None = None) -> Context:
        assets = ctx.cfg.get("assets", {})
        images_dir_raw = assets.get("images_dir", "../assets/images")
        sounds_dir_raw = assets.get("sounds_dir", "../assets/sounds")
        img_exts = [s.lower() for s in assets.get("image_extensions", self.IMG_EXT_DEFAULTS)]
        snd_exts = [s.lower() for s in assets.get("sound_extensions", self.SND_EXT_DEFAULTS)]

        img_dirs = self._resolve_candidates(images_dir_raw, ctx)
        snd_dirs = self._resolve_candidates(sounds_dir_raw, ctx)

        def numerickey(p: Path) -> tuple[int, str]:
            m = self.NUM_RX.search(p.stem)
            return (int(m.group(1)) if m else 10**9, p.name.lower())

        # Images
        for d in img_dirs:
            imgs = [p for p in d.iterdir() if p.is_file() and p.suffix.lower() in img_exts]
            if imgs:
                imgs.sort(key=numerickey)
                ctx.images = imgs
                logger.info("Found %d image(s) in %s", len(imgs), d)
                break
        else:
            logger.warning("Images dir not found or empty. Tried: %s", [str(x) for x in ([Path(images_dir_raw)] + img_dirs)])

        # Sounds
        for d in snd_dirs:
            snds = [p for p in d.iterdir() if p.is_file() and p.suffix.lower() in snd_exts]
            if snds:
                snds.sort(key=numerickey)
                ctx.sounds = snds
                logger.info("Found %d sound(s) in %s", len(snds), d)
                break
        else:
            logger.info("Sounds dir not found or empty. Tried: %s", [str(x) for x in ([Path(sounds_dir_raw)] + snd_dirs)])

        logger.info("Scanned assets: %d image(s), %d sound(s).", len(ctx.images), len(ctx.sounds))
        return ctx
    """3) Scan assets/images and assets/sounds. Enforce numeric order for images."""
    IMG_EXT_DEFAULTS = [".jpg", ".jpeg", ".png", ".bmp", ".webp", ".webm"]
    SND_EXT_DEFAULTS = [".mp3", ".wav", ".m4a"]
    NUM_RX = re.compile(r"(\d+)")

    def run(self, ctx: Context, cli_overrides: Dict[str, Any] | None = None) -> Context:
        assets = ctx.cfg.get("assets", {})
        images_dir = _abs(Path(assets.get("images_dir", "../assets/images")))
        sounds_dir = _abs(Path(assets.get("sounds_dir", "../assets/sounds")))
        img_exts = [s.lower() for s in assets.get("image_extensions", self.IMG_EXT_DEFAULTS)]
        snd_exts = [s.lower() for s in assets.get("sound_extensions", self.SND_EXT_DEFAULTS)]

        def numerickey(p: Path) -> tuple[int, str]:
            m = self.NUM_RX.search(p.stem)
            return (int(m.group(1)) if m else 10**9, p.name.lower())

        if images_dir.exists():
            imgs = [p for p in images_dir.iterdir() if p.is_file() and p.suffix.lower() in img_exts]
            imgs.sort(key=numerickey)
            ctx.images = imgs
        else:
            logger.warning("Images dir not found: %s", images_dir)

        if sounds_dir.exists():
            snds = [p for p in sounds_dir.iterdir() if p.is_file() and p.suffix.lower() in snd_exts]
            snds.sort(key=numerickey)
            ctx.sounds = snds
        else:
            logger.info("Sounds dir not found (ok if silent video): %s", sounds_dir)

        logger.info("Scanned assets: %d image(s), %d sound(s).", len(ctx.images), len(ctx.sounds))
        return ctx


class import_mediaStage(StageBase):
    """4) Add media entries into JSONs (no timeline yet)."""
    def run(self, ctx: Context, cli_overrides: Dict[str, Any] | None = None) -> Context:
        from jsonfiller import add_imports  # you implement

        updated_meta, updated_vstore, idmaps = add_imports(
            draft_meta_info=ctx.baselines["draft_meta_info"],
            draft_virtual_store=ctx.baselines["draft_virtual_store"],
            images=[str(p) for p in ctx.images],
            sounds=[str(p) for p in ctx.sounds],
            id_strategy=ctx.cfg.get("ids", {}).get("strategy", "mirror"),
        )
        ctx.baselines["draft_meta_info"] = updated_meta
        ctx.baselines["draft_virtual_store"] = updated_vstore
        ctx.idmaps.update(idmaps or {})
        logger.info("Imported media. Total idmaps: %d", len(ctx.idmaps))
        return ctx


class build_timelineStage(StageBase):
    """5) Lay out images sequentially; attach audio track."""
    def run(self, ctx: Context, cli_overrides: Dict[str, Any] | None = None) -> Context:
        from jsonfiller import build_timeline  # you implement

        tl_cfg = ctx.cfg.get("timeline", {})
        default_ms = int(tl_cfg.get("default_image_duration_ms", 5000))
        ordering = tl_cfg.get("ordering", "numeric")

        draft_content, timeline_cache = build_timeline(
            draft_content=ctx.baselines["draft_content"],
            images=[str(p) for p in ctx.images],
            sounds=[str(p) for p in ctx.sounds],
            default_image_duration_ms=default_ms,
            ordering=ordering,
        )
        ctx.baselines["draft_content"] = draft_content
        ctx.timeline = timeline_cache or {}
        logger.info("Timeline built with %d clip(s).", len(ctx.timeline.get("clips", [])))
        return ctx


class apply_transitionsStage(StageBase):
    def run(self, ctx: Context, cli_overrides=None) -> Context:
        from jsonfiller import apply_transitions
        tr_cfg = ctx.cfg.get("transitions", {})
        # inject catalog + cache_root into timeline cache for the filler
        ctx.timeline["catalog"] = tr_cfg.get("catalog", [])
        ctx.timeline["cache_root"] = tr_cfg.get("cache_root")
        draft_content, timeline_cache = apply_transitions(
            draft_content=ctx.baselines["draft_content"],
            timeline=ctx.timeline,
            names=tr_cfg.get("names", []),  # optional allow-list
            per_cut_probability=float(tr_cfg.get("per_cut_probability", 0.65)),
            duration_ms_range=tuple(tr_cfg.get("duration_ms_range", [600, 800])),
        )
        ctx.baselines["draft_content"] = draft_content
        if timeline_cache:
            ctx.timeline = timeline_cache
        return ctx



class operationsStage(StageBase):
    """7) Compute totals, per-clip times, IDs, timestamps → operations.json."""
    def run(self, ctx: Context, cli_overrides: Dict[str, Any] | None = None) -> Context:
        from operations import compute_operations  # you implement

        ops = compute_operations(
            draft_content=ctx.baselines["draft_content"],
            draft_meta_info=ctx.baselines["draft_meta_info"],
            draft_virtual_store=ctx.baselines["draft_virtual_store"],
            timeline=ctx.timeline,
            idmaps=ctx.idmaps,
            now_timestamp_us=_timestamp_us_now(),
        )
        ctx.ops = ops or {}
        logger.info("Operations computed.")
        return ctx


class synchronizerStage(StageBase):
    """8) Merge ops into all JSONs; sync IDs & references; update meta project name rules."""
    def run(self, ctx: Context, cli_overrides: Dict[str, Any] | None = None) -> Context:
        from synchronizer import sync_all  # you implement

        # Allow CLI override of project_root (if user passed --project-root)
        if cli_overrides and cli_overrides.get("project_root"):
            # Not strictly needed unless you want to relocate; here we only pass into sync
            ctx.cfg["project_root"] = cli_overrides["project_root"]

        draft_content, draft_meta_info, draft_virtual_store = sync_all(
            draft_content=ctx.baselines["draft_content"],
            draft_meta_info=ctx.baselines["draft_meta_info"],
            draft_virtual_store=ctx.baselines["draft_virtual_store"],
            ops=ctx.ops,
            project_name=ctx.project_name,
            project_dir=str(ctx.project_dir) if ctx.project_dir else None,
            # Special Rule: replace meta name/path with generated project name
            force_meta_name=True,   # your sync_all should set: draft_fold_path=project_name, draft_name=project_name
        )
        ctx.baselines["draft_content"] = draft_content
        ctx.baselines["draft_meta_info"] = draft_meta_info
        ctx.baselines["draft_virtual_store"] = draft_virtual_store

        logger.info("Synchronization complete.")
        return ctx


class doctorStage(StageBase):
    """9) Validate JSON integrity; autofix (YAML or CLI --fix)."""
    def run(self, ctx: Context, cli_overrides: Dict[str, Any] | None = None) -> Context:
        from doctor import inspect_and_fix  # you implement

        autofix_yaml = bool(ctx.cfg.get("doctor", {}).get("autofix", True))
        autofix_cli = bool(cli_overrides and cli_overrides.get("doctor_autofix"))
        strict = bool(ctx.cfg.get("doctor", {}).get("strict", True))

        report = inspect_and_fix(
            draft_content=ctx.baselines["draft_content"],
            draft_meta_info=ctx.baselines["draft_meta_info"],
            draft_virtual_store=ctx.baselines["draft_virtual_store"],
            strict=strict,
            autofix=autofix_cli or autofix_yaml,
        )
        ctx.diagnostics = report or {}
        logger.info("Doctor finished. issues=%s", len(ctx.diagnostics.get("issues", [])))
        return ctx


class write_jsonStage(StageBase):
    """10) Atomic write of JSON triplet + ops + doctor report."""
    def run(self, ctx: Context, cli_overrides: Dict[str, Any] | None = None) -> Context:
        if not ctx.project_dir:
            raise RuntimeError("Project directory not prepared.")

        # Optionally backup
        adv = ctx.cfg.get("advanced", {})
        if adv.get("backup_on_overwrite", True):
            bdir = Path(adv.get("backup_dir", "./.capcut_backups")).expanduser().resolve()
            _ensure_dir(bdir)
            stamp = int(time.time())
            snap = bdir / f"{ctx.project_name}-{stamp}"
            _ensure_dir(snap)
            for f in ["draft_content.json", "draft_meta_info.json", "draft_virtual_store.json"]:
                src = ctx.project_dir / f
                if src.exists():
                    shutil.copy2(src, snap / f)

        # Write current
        _write_json_atomic(ctx.draft_content_path, ctx.baselines["draft_content"])
        _write_json_atomic(ctx.draft_meta_info_path, ctx.baselines["draft_meta_info"])
        _write_json_atomic(ctx.draft_virtual_store_path, ctx.baselines["draft_virtual_store"])
        _write_json_atomic(ctx.operations_path, ctx.ops or {})
        _write_json_atomic(ctx.doctor_report_path, ctx.diagnostics or {})

        logger.info("Wrote JSONs to %s", ctx.project_dir)
        return ctx

# ---------------- Registry & builder ----------------

STAGE_REGISTRY: Dict[str, Type[StageBase]] = {
    "load_config": load_configStage,
    "prepare_project_dir": prepare_project_dirStage,
    "scan_assets": scan_assetsStage,
    "import_media": import_mediaStage,
    "build_timeline": build_timelineStage,
    "apply_transitions": apply_transitionsStage,
    "operations": operationsStage,
    "synchronizer": synchronizerStage,
    "doctor": doctorStage,
    "write_json": write_jsonStage,
}

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
