#!/usr/bin/env python3
"""
CapCut Auto Project Creator - Enhanced Version (+ Image Pipeline)

Creates a CapCut project, then (optionally) imports images from assets/images,
syncs draft_virtual_store.json, and lays them on the timeline with transitions.

Usage:
    python main.py                                  # Create with random name, process images from assets/images if present
    python main.py --name P1234                     # Create with specific name
    python main.py --dry-run                        # Preview without creating
    python main.py --list                           # Show existing projects
    python main.py --images-dir assets/images       # Specify images directory
    python main.py --no-media                       # Skip media import/timeline steps
"""

from __future__ import annotations
import argparse
import json
import logging
import random
import re
import shutil
import string
import sys
import yaml
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

# --- Bring in our helper modules --------------------------------------------
# They must live next to this file: capcut_draft_utils.py, capcut_virtual_store_utils.py, capcut_content_utils.py
try:
    import capcut_draft_utils as meta_utils
    import capcut_virtual_store_utils as store_utils
    import capcut_content_utils as content_utils
except Exception as e:
    # We'll only error out if we actually try to use media pipeline.
    meta_utils = None
    store_utils = None
    content_utils = None

# --- Logging Setup ----------------------------------------------------------
def setup_logging(verbose: bool = False) -> logging.Logger:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)

logger = setup_logging()

# --- Configuration ----------------------------------------------------------
@dataclass
class Config:
    template_dir: Path = Path("template-config")
    project_root: Path = Path(".")
    config_file: Optional[Path] = Path("capcut_creator_config.yaml")
    required_structure: List[str] = None
    
    def __post_init__(self):
        if self.required_structure is None:
            self.required_structure = [
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
    
    @classmethod
    def from_file(cls, config_path: Path) -> 'Config':
        if not config_path.exists():
            logger.debug(f"Config file not found: {config_path}")
            return cls()
        try:
            with config_path.open('r') as f:
                if config_path.suffix in ['.yaml', '.yml']:
                    data = yaml.safe_load(f)
                elif config_path.suffix == '.json':
                    data = json.load(f)
                else:
                    logger.warning(f"Unknown config format: {config_path.suffix}")
                    return cls()
            return cls(
                template_dir=Path(data.get('template_dir', cls.template_dir)),
                project_root=Path(data.get('project_root', cls.project_root)),
                required_structure=data.get('required_structure', cls.required_structure)
            )
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return cls()

# --- Exit Codes -------------------------------------------------------------
class ExitCode(Enum):
    SUCCESS = 0
    GENERAL_ERROR = 1
    INVALID_INPUT = 2
    FILE_NOT_FOUND = 3
    PERMISSION_ERROR = 4
    USER_CANCELLED = 5

# --- Project Name Management ------------------------------------------------
class ProjectNameValidator:
    PATTERN = re.compile(r'^[A-Z]\d{4}$')
    
    @classmethod
    def validate(cls, name: str) -> bool:
        return bool(cls.PATTERN.match(name))
    
    @classmethod
    def generate_random(cls) -> str:
        letter = random.choice(string.ascii_uppercase)
        number = random.randint(0, 9999)
        return f"{letter}{number:04d}"

# --- Project Manager --------------------------------------------------------
class CapCutProjectManager:
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def create_project(self, project_name: str, dry_run: bool = False, force: bool = False) -> Path:
        project_path = self.config.project_root / project_name
        
        if project_path.exists() and not force:
            if not self._prompt_overwrite(project_name):
                raise FileExistsError(f"Project {project_name} already exists")
        
        if dry_run:
            self._simulate_creation(project_name, project_path)
            return project_path
        
        try:
            project_path.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Creating project: {project_name}")
            self._create_structure(project_path)
            self._copy_template(project_path)
            self._update_metadata(project_path, project_name)
            self.logger.info(f"✅ Successfully created project: {project_name}")
            self.logger.info(f"📂 Location: {project_path.resolve()}")
            return project_path
        except Exception as e:
            self.logger.error(f"Failed to create project: {e}")
            if project_path.exists():
                self._cleanup_failed_project(project_path)
            raise
    
    def list_projects(self) -> List[str]:
        projects = []
        if not self.config.project_root.exists():
            return projects
        for item in self.config.project_root.iterdir():
            if item.is_dir() and self._is_valid_project(item):
                projects.append(item.name)
        return sorted(projects)
    
    def _create_structure(self, base: Path) -> None:
        for item in self.config.required_structure:
            path = base / item
            if item.endswith(".locked"):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch(exist_ok=True)
                self.logger.debug(f"Created file: {path}")
            else:
                path.mkdir(parents=True, exist_ok=True)
                self.logger.debug(f"Created directory: {path}")
    
    def _copy_template(self, dest: Path) -> None:
        template_dir = self.config.template_dir
        if not template_dir.exists():
            raise FileNotFoundError(f"Template directory not found: {template_dir.resolve()}")
        self.logger.info(f"Copying template from: {template_dir}")
        total_files = sum(1 for _ in template_dir.rglob('*') if _.is_file())
        copied = 0
        for entry in template_dir.iterdir():
            src = entry
            dst = dest / entry.name
            try:
                if src.is_dir():
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                    copied += sum(1 for _ in src.rglob('*') if _.is_file())
                else:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                    copied += 1
                if total_files > 0:
                    progress = (copied / total_files) * 100
                    self.logger.debug(f"Copy progress: {progress:.1f}%")
            except Exception as e:
                self.logger.error(f"Error copying {src}: {e}")
                raise
    
    def _update_metadata(self, project_path: Path, project_name: str) -> None:
        meta_file = project_path / "draft_meta_info.json"
        if not meta_file.exists():
            self.logger.warning("draft_meta_info.json not found; skipping metadata update")
            return
        try:
            with meta_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            data["draft_name"] = project_name
            if "draft_fold_path" in data:
                data["draft_fold_path"] = self._update_draft_path(data["draft_fold_path"], project_name)
            data["creation_timestamp"] = datetime.now().isoformat()
            with meta_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            self.logger.info(f"Updated metadata: draft_name={project_name}")
        except Exception as e:
            self.logger.error(f"Failed to update metadata: {e}")
            raise
    
    def _update_draft_path(self, path_value: str, project_name: str) -> str:
        pattern = re.compile(r"(.*?com\\.lveditor\\.draft[\\\\/])(.+)?")
        match = pattern.match(path_value)
        if match:
            prefix = match.group(1)
            return prefix + project_name
        return path_value
    
    def _is_valid_project(self, path: Path) -> bool:
        indicators = [path / ".locked", path / "draft_meta_info.json", path / "Resources"]
        return any(indicator.exists() for indicator in indicators)
    
    def _prompt_overwrite(self, project_name: str) -> bool:
        response = input(f"⚠️  Project '{project_name}' exists. Overwrite? [y/N]: ")
        return response.lower() == 'y'
    
    def _simulate_creation(self, project_name: str, project_path: Path) -> None:
        self.logger.info(f"🔄 DRY-RUN: Would create project '{project_name}'")
        self.logger.info(f"📂 Location: {project_path.resolve()}")
        self.logger.info("📋 Actions that would be performed:")
        self.logger.info("  - Create project directory")
        self.logger.info("  - Create CapCut folder structure")
        self.logger.info("  - Copy template files")
        self.logger.info("  - Update metadata")
    
    def _cleanup_failed_project(self, project_path: Path) -> None:
        try:
            if project_path.exists():
                shutil.rmtree(project_path)
                self.logger.info(f"Cleaned up failed project: {project_path}")
        except Exception as e:
            self.logger.error(f"Failed to cleanup: {e}")

# --- Helpers for media pipeline ---------------------------------------------
def _collect_images(images_dir: Path) -> List[Path]:
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    if not images_dir.exists():
        return []
    imgs = [p for p in images_dir.iterdir() if p.is_file() and p.suffix.lower() in exts]
    # Sort numerically if names like 1.jpg, 2.jpg...
    def sort_key(p: Path):
        stem = p.stem
        return (int(stem) if stem.isdigit() else 10**9, stem)
    imgs.sort(key=sort_key)
    return imgs

def _timeline_total_duration_us(content: dict) -> int:
    tracks = content.get("tracks", [])
    if not tracks:
        return 0
    total = 0
    for s in tracks[0].get("segments", []):
        start = int(s["target_timerange"]["start"])
        dur = int(s["target_timerange"]["duration"])
        total = max(total, start + dur)
    return total

# --- CLI Interface ----------------------------------------------------------
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enhanced CapCut Auto Project Creator (+ Image Pipeline)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Create project with random name
  %(prog)s --name P1234              # Create project with specific name
  %(prog)s --dry-run                 # Preview without creating
  %(prog)s --list                    # List existing projects
  %(prog)s --config my_config.yaml   # Use custom configuration
  %(prog)s --images-dir assets/images --duration-us 5000000
        """
    )
    parser.add_argument("--name", help="Project name (Letter+4digits). Random if omitted.")
    parser.add_argument("--template", help="Path to template-config folder")
    parser.add_argument("--root", help="Path where projects will be created")
    parser.add_argument("--config", help="Path to configuration file (YAML or JSON)")
    parser.add_argument("--dry-run", action="store_true", help="Preview actions without making changes")
    parser.add_argument("--force", action="store_true", help="Overwrite existing projects without prompting")
    parser.add_argument("--list", action="store_true", help="List existing projects")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    # Media pipeline options
    parser.add_argument("--no-media", action="store_true", help="Skip importing images and building timeline")
    parser.add_argument("--images-dir", default="assets/images", help="Directory with images (default: assets/images)")
    parser.add_argument("--duration-us", type=int, default=5_000_000, help="Per-image duration on timeline (default 5,000,000)")
    parser.add_argument("--no-placeholder", action="store_true", help="Do NOT add tiny placeholder before first image in meta")
    parser.add_argument("--no-transitions", action="store_true", help="Do NOT add transitions between segments")
    parser.add_argument("--transition-name", default="Pull in", help="Transition name (default: Pull in)")
    parser.add_argument("--transition-duration-us", type=int, default=466_666, help="Transition duration (µs) default ~0.466s")
    parser.add_argument("--transition-overlap", action="store_true", help="Mark transition as overlap (default False)")
    return parser.parse_args()

# --- Main Execution ---------------------------------------------------------
def main() -> int:
    try:
        args = parse_arguments()
        global logger
        logger = setup_logging(args.verbose)
        
        # Load configuration
        config = Config()
        if args.config:
            config = Config.from_file(Path(args.config))
        if args.template:
            config.template_dir = Path(args.template)
        if args.root:
            config.project_root = Path(args.root)
        
        manager = CapCutProjectManager(config)
        
        if args.list:
            projects = manager.list_projects()
            if projects:
                print("\n📋 Existing projects:")
                for proj in projects:
                    print(f"  • {proj}")
            else:
                print("No projects found.")
            return ExitCode.SUCCESS.value
        
        if args.name:
            project_name = args.name.strip()
            if not ProjectNameValidator.validate(project_name):
                logger.error(f"Invalid project name format: {project_name}")
                logger.info("Expected format: Letter + 4 digits (e.g., A1234)")
                return ExitCode.INVALID_INPUT.value
        else:
            project_name = ProjectNameValidator.generate_random()
            logger.info(f"Generated project name: {project_name}")
        
        project_path = manager.create_project(project_name, dry_run=args.dry_run, force=args.force)
        
        if args.dry_run or args.no_media:
            if not args.no_media:
                logger.info("DRY-RUN: would now import images, sync virtual store, and build timeline")
            print(f"project_name={project_name}")
            print(f"folder_name={project_name}")
            print(f"project_path={project_path.resolve()}")
            return ExitCode.SUCCESS.value
        
        # --- Media pipeline --------------------------------------------------
        if not (meta_utils and store_utils and content_utils):
            logger.error("Helper modules not found. Ensure capcut_*_utils.py files are present.")
            return ExitCode.GENERAL_ERROR.value
        
        images_dir = Path(args.images_dir)
        images = _collect_images(images_dir)
        if not images:
            logger.warning(f"No images found in {images_dir}. Skipping media pipeline.")
            print(f"project_name={project_name}")
            print(f"folder_name={project_name}")
            print(f"project_path={project_path.resolve()}")
            return ExitCode.SUCCESS.value
        
        logger.info(f"Found {len(images)} image(s) in {images_dir}")
        
        meta_path = project_path / "draft_meta_info.json"
        store_path = project_path / "draft_virtual_store.json"
        content_path = project_path / "draft_content.json"
        
        # 1) Import images into meta (placeholder only for first unless disabled)
        include_placeholder = not args.no_placeholder
        meta = meta_utils.load_draft(meta_path)
        for idx, img in enumerate(images):
            meta_utils.add_image_to_draft(
                meta,
                img.resolve(),
                duration_us=args.duration_us,
                include_placeholder_if_first=(include_placeholder and idx == 0)
            )
        meta_utils.save_draft(meta, meta_path)
        logger.info("Updated draft_meta_info.json with images")
        
        # 2) Sync virtual store from meta
        meta_for_store = store_utils.load_json(meta_path)
        ids = store_utils.extract_image_material_ids_from_meta(meta_for_store)
        store = store_utils.build_virtual_store(ids)
        store_utils.save_json(store, store_path)
        logger.info("Rebuilt draft_virtual_store.json")
        
        # 3) Place on timeline with transitions
        content = content_utils.load_content(content_path)
        for img in images:
            content_utils.add_image_to_timeline(
                content,
                img.resolve(),
                duration_us=args.duration_us,
                add_transition_after_previous=(not args.no_transitions),
                transition_name=args.transition_name,
                transition_duration_us=args.transition_duration_us,
                transition_is_overlap=args.transition_overlap
            )
        content_utils.save_content(content, content_path)
        logger.info("Updated draft_content.json with timeline segments and transitions")
        
        # 4) Update meta tm_duration from content
        total = _timeline_total_duration_us(content)
        meta2 = meta_utils.load_draft(meta_path)
        if total > 0:
            meta2["tm_duration"] = total
        meta2["tm_draft_modified"] = int(datetime.now().timestamp() * 1_000_000)
        meta_utils.save_draft(meta2, meta_path)
        logger.info(f"Synced tm_duration={total} and modified time in draft_meta_info.json")
        
        print(f"project_name={project_name}")
        print(f"folder_name={project_name}")
        print(f"project_path={project_path.resolve()}")
        return ExitCode.SUCCESS.value
        
    except FileExistsError:
        logger.error("Project creation cancelled by user")
        return ExitCode.USER_CANCELLED.value
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return ExitCode.FILE_NOT_FOUND.value
    except PermissionError as e:
        logger.error(f"Permission denied: {e}")
        return ExitCode.PERMISSION_ERROR.value
    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user")
        return ExitCode.USER_CANCELLED.value
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return ExitCode.GENERAL_ERROR.value

if __name__ == "__main__":
    sys.exit(main())
