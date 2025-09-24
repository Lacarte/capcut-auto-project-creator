#!/usr/bin/env python3
"""
CapCut Auto Project Creator - FINAL COMPREHENSIVE VERSION
========================================================
Complete implementation with:
- Proper ID synchronization across all JSON files
- Enhanced field structures matching manual CapCut projects
- Fixed draft_fold_path updating
- Comprehensive error handling and validation
- Full material structure with all required fields

Usage:
    python main.py                                  # Create with random name, auto-process images
    python main.py --name P1234                     # Create with specific name
    python main.py --images-dir assets/images       # Specify images directory
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
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

# --- Import our enhanced helper modules --------------------------------------------
try:
    import capcut_draft_utils as meta_utils
    import capcut_virtual_store_utils as store_utils
    from capcut_content_utils import sync_timeline_from_meta, load_content  # Enhanced version
except Exception as e:
    print(f"ERROR: Missing helper modules: {e}")
    print("Ensure capcut_draft_utils.py, capcut_virtual_store_utils.py, and capcut_content_utils.py are present")
    sys.exit(1)

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

# --- Enhanced Project Manager -----------------------------------------------
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
            self.logger.info(f"Successfully created project: {project_name}")
            self.logger.info(f"Location: {project_path.resolve()}")
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
        for entry in template_dir.iterdir():
            src = entry
            dst = dest / entry.name
            try:
                if src.is_dir():
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
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
            
            # Update project name
            data["draft_name"] = project_name
            
            # Fix draft_fold_path to use actual project name
            if "draft_fold_path" in data:
                data["draft_fold_path"] = self._update_draft_path(data["draft_fold_path"], project_name)
                self.logger.info(f"Updated draft_fold_path: {data['draft_fold_path']}")
            
            # Add creation timestamp
            data["creation_timestamp"] = datetime.now().isoformat()
            
            # Update modification time
            data["tm_draft_modified"] = int(datetime.now().timestamp() * 1_000_000)
            
            with meta_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"Updated metadata: draft_name={project_name}")
        except Exception as e:
            self.logger.error(f"Failed to update metadata: {e}")
            raise
    
    def _update_draft_path(self, path_value: str, project_name: str) -> str:
        """
        FIXED: Update draft_fold_path to use actual project name.
        Handles both Windows and Unix path separators properly.
        """
        # Pattern to match the CapCut draft path structure
        pattern = re.compile(r"(.*?com\.lveditor\.draft[/\\])(.+)$")
        match = pattern.match(path_value)
        
        if match:
            prefix = match.group(1)
            new_path = prefix + project_name
            self.logger.debug(f"Path pattern matched: {path_value} -> {new_path}")
            return new_path
        else:
            # Fallback for edge cases
            base_pattern = re.compile(r"(.*?com\.lveditor\.draft[/\\]?).*$")
            base_match = base_pattern.match(path_value)
            if base_match:
                new_path = base_match.group(1).rstrip('/\\') + '/' + project_name
                self.logger.debug(f"Fallback path update: {path_value} -> {new_path}")
                return new_path
            else:
                # Last resort
                new_path = str(Path(path_value).parent / project_name)
                self.logger.debug(f"Last resort path update: {path_value} -> {new_path}")
                return new_path
    
    def _is_valid_project(self, path: Path) -> bool:
        indicators = [path / ".locked", path / "draft_meta_info.json", path / "Resources"]
        return any(indicator.exists() for indicator in indicators)
    
    def _prompt_overwrite(self, project_name: str) -> bool:
        response = input(f"Project '{project_name}' exists. Overwrite? [y/N]: ")
        return response.lower() == 'y'
    
    def _simulate_creation(self, project_name: str, project_path: Path) -> None:
        self.logger.info(f"DRY-RUN: Would create project '{project_name}'")
        self.logger.info(f"Location: {project_path.resolve()}")
        self.logger.info("Actions that would be performed:")
        self.logger.info("  - Create project directory")
        self.logger.info("  - Create CapCut folder structure")
        self.logger.info("  - Copy template files")
        self.logger.info("  - Update metadata with correct project name and paths")
    
    def _cleanup_failed_project(self, project_path: Path) -> None:
        try:
            if project_path.exists():
                shutil.rmtree(project_path)
                self.logger.info(f"Cleaned up failed project: {project_path}")
        except Exception as e:
            self.logger.error(f"Failed to cleanup: {e}")

# --- Enhanced Media Pipeline ------------------------------------------------
def collect_images(images_dir: Path) -> List[Path]:
    """Collect and sort image files from directory."""
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    if not images_dir.exists():
        return []
    
    imgs = [p for p in images_dir.iterdir() if p.is_file() and p.suffix.lower() in exts]
    
    # Sort numerically if names like 1.jpg, 2.jpg, else alphabetically
    def sort_key(p: Path):
        stem = p.stem
        try:
            return (0, int(stem))  # Numeric sort
        except ValueError:
            return (1, stem)  # Alphabetic sort
    
    imgs.sort(key=sort_key)
    return imgs

def calculate_timeline_duration(content: dict) -> int:
    """Calculate total timeline duration from segments."""
    tracks = content.get("tracks", [])
    if not tracks:
        return 0
    
    total = 0
    for segment in tracks[0].get("segments", []):
        start = int(segment["target_timerange"]["start"])
        duration = int(segment["target_timerange"]["duration"])
        total = max(total, start + duration)
    
    return total

def process_media_pipeline(project_path: Path, 
                          images_dir: Path, 
                          args: argparse.Namespace) -> bool:
    """
    ENHANCED: Process the complete media pipeline with proper ID synchronization.
    Returns True if successful, False otherwise.
    """
    images = collect_images(images_dir)
    if not images:
        logger.warning(f"No images found in {images_dir}")
        return False
    
    logger.info(f"Found {len(images)} image(s) to process")
    
    # File paths
    meta_path = project_path / "draft_meta_info.json"
    store_path = project_path / "draft_virtual_store.json"
    content_path = project_path / "draft_content.json"
    
    try:
        # Step 1: Import images into meta file
        logger.info("Step 1: Importing images to draft_meta_info.json")
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
        logger.info("✓ Updated draft_meta_info.json with images")
        
        # Step 2: Rebuild virtual store with synchronized IDs
        logger.info("Step 2: Rebuilding draft_virtual_store.json")
        meta_for_store = store_utils.load_json(meta_path)
        ids = store_utils.extract_image_material_ids_from_meta(meta_for_store)
        store = store_utils.build_virtual_store(ids)
        store_utils.save_json(store, store_path)
        logger.info(f"✓ Rebuilt virtual store with {len(ids)} material references")
        
        # Step 3: CRITICAL - Build timeline with synchronized IDs
        logger.info("Step 3: Building timeline with synchronized material IDs")
        sync_timeline_from_meta(
            content_path,
            meta_path,
            duration_us=args.duration_us,
            add_transitions=(not args.no_transitions),
            transition_name=args.transition_name,
            transition_duration_us=args.transition_duration_us,
            transition_is_overlap=args.transition_overlap
        )
        logger.info("✓ Built timeline with synchronized IDs")
        
        # Step 4: Update meta file with final timeline duration
        logger.info("Step 4: Syncing timeline duration")
        content = load_content(content_path)
        total_duration = calculate_timeline_duration(content)
        
        if total_duration > 0:
            meta = meta_utils.load_draft(meta_path)
            meta["tm_duration"] = total_duration
            meta["tm_draft_modified"] = int(datetime.now().timestamp() * 1_000_000)
            meta_utils.save_draft(meta, meta_path)
            logger.info(f"✓ Synced timeline duration: {total_duration} microseconds")
        
        logger.info("SUCCESS: Media pipeline completed with full ID synchronization")
        return True
        
    except Exception as e:
        logger.error(f"Media pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        return False

# --- CLI Interface ----------------------------------------------------------
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enhanced CapCut Auto Project Creator - Complete ID Synchronization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Create with random name, auto-process images
  %(prog)s --name P1234              # Create project with specific name
  %(prog)s --images-dir assets/images --duration-us 3000000  # 3-second duration
  %(prog)s --dry-run --name TEST     # Preview project creation
  %(prog)s --list                    # Show existing projects
        """
    )
    
    # Project creation options
    parser.add_argument("--name", help="Project name (Letter+4digits, e.g. P1234)")
    parser.add_argument("--template", help="Path to template-config folder")
    parser.add_argument("--root", help="Path where projects will be created")
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating")
    parser.add_argument("--force", action="store_true", help="Overwrite existing projects")
    parser.add_argument("--list", action="store_true", help="List existing projects")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    
    # Media pipeline options
    parser.add_argument("--no-media", action="store_true", help="Skip media import")
    parser.add_argument("--images-dir", default="assets/images", 
                       help="Images directory (default: assets/images)")
    parser.add_argument("--duration-us", type=int, default=5_000_000, 
                       help="Per-image duration in microseconds (default: 5,000,000 = 5 seconds)")
    parser.add_argument("--no-placeholder", action="store_true", 
                       help="Don't add placeholder before first image")
    parser.add_argument("--no-transitions", action="store_true", 
                       help="Don't add transitions between segments")
    parser.add_argument("--transition-name", default="Pull in", 
                       help="Transition name (default: Pull in)")
    parser.add_argument("--transition-duration-us", type=int, default=466_666, 
                       help="Transition duration microseconds (default: ~0.47s)")
    parser.add_argument("--transition-overlap", action="store_true", 
                       help="Mark transitions as overlap")
    
    return parser.parse_args()

# --- Main Execution ---------------------------------------------------------
def main() -> int:
    try:
        args = parse_arguments()
        global logger
        logger = setup_logging(args.verbose)
        
        # Load configuration
        config = Config()
        if args.template:
            config.template_dir = Path(args.template)
        if args.root:
            config.project_root = Path(args.root)
        
        manager = CapCutProjectManager(config)
        
        # Handle list command
        if args.list:
            projects = manager.list_projects()
            if projects:
                print("\nExisting projects:")
                for proj in projects:
                    print(f"  • {proj}")
            else:
                print("No projects found.")
            return ExitCode.SUCCESS.value
        
        # Validate or generate project name
        if args.name:
            project_name = args.name.strip()
            if not ProjectNameValidator.validate(project_name):
                logger.error(f"Invalid project name format: {project_name}")
                logger.info("Expected format: Letter + 4 digits (e.g., P1234)")
                return ExitCode.INVALID_INPUT.value
        else:
            project_name = ProjectNameValidator.generate_random()
            logger.info(f"Generated project name: {project_name}")
        
        # Create project
        project_path = manager.create_project(project_name, dry_run=args.dry_run, force=args.force)
        
        # Handle dry-run or no-media
        if args.dry_run or args.no_media:
            if not args.no_media:
                logger.info("DRY-RUN: Would process media pipeline with ID synchronization")
            print(f"project_name={project_name}")
            print(f"project_path={project_path.resolve()}")
            return ExitCode.SUCCESS.value
        
        # Process media pipeline
        images_dir = Path(args.images_dir)
        if images_dir.exists():
            success = process_media_pipeline(project_path, images_dir, args)
            if not success:
                logger.warning("Media pipeline failed, but project structure was created")
        else:
            logger.info(f"No images directory found at {images_dir}, skipping media pipeline")
        
        # Final success message
        logger.info(f"Project creation completed successfully!")
        print(f"project_name={project_name}")
        print(f"project_path={project_path.resolve()}")
        print("Your CapCut project should now open and play correctly!")
        
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