#!/usr/bin/env python3
"""
CapCut Auto Project Creator - Enhanced Version

Automatically generates CapCut video editing projects with proper structure and configuration.
Supports custom naming, template copying, and metadata management.

Usage:
    python main.py                    # Create with random name
    python main.py --name P1234       # Create with specific name
    python main.py --dry-run          # Preview without creating
    python main.py --list             # Show existing projects
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

# --- Logging Setup ----------------------------------------------------------
def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure logging with appropriate level and format."""
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
    """Application configuration."""
    template_dir: Path = Path("template-config")
    project_root: Path = Path(".")
    config_file: Optional[Path] = Path("capcut_creator_config.yaml")
    required_structure: List[str] = None
    
    def __post_init__(self):
        if self.required_structure is None:
            self.required_structure = [
                ".locked",                # file (empty)
                "adjust_mask",            # directories below
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
    def from_file(cls, config_path: Path) -> Config:
        """Load configuration from YAML or JSON file."""
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
    """Application exit codes."""
    SUCCESS = 0
    GENERAL_ERROR = 1
    INVALID_INPUT = 2
    FILE_NOT_FOUND = 3
    PERMISSION_ERROR = 4
    USER_CANCELLED = 5

# --- Project Name Management ------------------------------------------------
class ProjectNameValidator:
    """Validates and generates project names."""
    
    PATTERN = re.compile(r'^[A-Z]\d{4}$')
    
    @classmethod
    def validate(cls, name: str) -> bool:
        """
        Validate project name format: Letter + 4 digits.
        
        Args:
            name: Project name to validate
            
        Returns:
            True if valid, False otherwise
        """
        return bool(cls.PATTERN.match(name))
    
    @classmethod
    def generate_random(cls) -> str:
        """
        Generate a random project name: Letter + 4 digits (e.g., A0923).
        
        Returns:
            Random project name
        """
        letter = random.choice(string.ascii_uppercase)
        number = random.randint(0, 9999)
        return f"{letter}{number:04d}"

# --- Project Manager --------------------------------------------------------
class CapCutProjectManager:
    """Manages CapCut project creation and maintenance."""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def create_project(self, 
                      project_name: str, 
                      dry_run: bool = False,
                      force: bool = False) -> Path:
        """
        Create a new CapCut project.
        
        Args:
            project_name: Name of the project
            dry_run: If True, only simulate creation
            force: If True, overwrite existing projects
            
        Returns:
            Path to created project
            
        Raises:
            FileExistsError: If project exists and force is False
            FileNotFoundError: If template directory doesn't exist
        """
        project_path = self.config.project_root / project_name
        
        # Check for existing project
        if project_path.exists() and not force:
            if not self._prompt_overwrite(project_name):
                raise FileExistsError(f"Project {project_name} already exists")
        
        if dry_run:
            self._simulate_creation(project_name, project_path)
            return project_path
        
        try:
            # Create project
            project_path.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Creating project: {project_name}")
            
            # Create structure
            self._create_structure(project_path)
            
            # Copy template
            self._copy_template(project_path)
            
            # Update metadata
            self._update_metadata(project_path, project_name)
            
            self.logger.info(f"✅ Successfully created project: {project_name}")
            self.logger.info(f"📂 Location: {project_path.resolve()}")
            
            return project_path
            
        except Exception as e:
            self.logger.error(f"Failed to create project: {e}")
            # Rollback on failure
            if project_path.exists():
                self._cleanup_failed_project(project_path)
            raise
    
    def list_projects(self) -> List[str]:
        """
        List existing projects.
        
        Returns:
            List of project names
        """
        projects = []
        
        if not self.config.project_root.exists():
            return projects
        
        for item in self.config.project_root.iterdir():
            if item.is_dir() and self._is_valid_project(item):
                projects.append(item.name)
        
        return sorted(projects)
    
    def _create_structure(self, base: Path) -> None:
        """Create the required CapCut folder structure."""
        for item in self.config.required_structure:
            path = base / item
            
            if item.endswith(".locked"):
                # Create as file
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch(exist_ok=True)
                self.logger.debug(f"Created file: {path}")
            else:
                # Create as directory
                path.mkdir(parents=True, exist_ok=True)
                self.logger.debug(f"Created directory: {path}")
    
    def _copy_template(self, dest: Path) -> None:
        """Copy template files to project directory."""
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
                
                # Show progress
                if total_files > 0:
                    progress = (copied / total_files) * 100
                    self.logger.debug(f"Copy progress: {progress:.1f}%")
                    
            except Exception as e:
                self.logger.error(f"Error copying {src}: {e}")
                raise
    
    def _update_metadata(self, project_path: Path, project_name: str) -> None:
        """Update draft_meta_info.json with project details."""
        meta_file = project_path / "draft_meta_info.json"
        
        if not meta_file.exists():
            self.logger.warning("draft_meta_info.json not found; skipping metadata update")
            return
        
        try:
            # Read existing metadata
            with meta_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Update draft_name
            data["draft_name"] = project_name
            
            # Update draft_fold_path
            if "draft_fold_path" in data:
                data["draft_fold_path"] = self._update_draft_path(
                    data["draft_fold_path"], 
                    project_name
                )
            
            # Add creation timestamp
            data["creation_timestamp"] = datetime.now().isoformat()
            
            # Write updated metadata
            with meta_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            self.logger.info(f"Updated metadata: draft_name={project_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to update metadata: {e}")
            raise
    
    def _update_draft_path(self, path_value: str, project_name: str) -> str:
        """Update draft path with new project name."""
        pattern = re.compile(r"(.*?com\.lveditor\.draft[\\/])(.+)?")
        match = pattern.match(path_value)
        
        if match:
            prefix = match.group(1)
            return prefix + project_name
        
        return path_value
    
    def _is_valid_project(self, path: Path) -> bool:
        """Check if a directory is a valid CapCut project."""
        # Check for key indicators
        indicators = [
            path / ".locked",
            path / "draft_meta_info.json",
            path / "Resources"
        ]
        return any(indicator.exists() for indicator in indicators)
    
    def _prompt_overwrite(self, project_name: str) -> bool:
        """Prompt user for overwrite confirmation."""
        response = input(f"⚠️  Project '{project_name}' exists. Overwrite? [y/N]: ")
        return response.lower() == 'y'
    
    def _simulate_creation(self, project_name: str, project_path: Path) -> None:
        """Simulate project creation for dry-run mode."""
        self.logger.info(f"🔄 DRY-RUN: Would create project '{project_name}'")
        self.logger.info(f"📂 Location: {project_path.resolve()}")
        self.logger.info("📋 Actions that would be performed:")
        self.logger.info("  - Create project directory")
        self.logger.info("  - Create CapCut folder structure")
        self.logger.info("  - Copy template files")
        self.logger.info("  - Update metadata")
    
    def _cleanup_failed_project(self, project_path: Path) -> None:
        """Clean up partially created project after failure."""
        try:
            if project_path.exists():
                shutil.rmtree(project_path)
                self.logger.info(f"Cleaned up failed project: {project_path}")
        except Exception as e:
            self.logger.error(f"Failed to cleanup: {e}")

# --- CLI Interface ----------------------------------------------------------
def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Enhanced CapCut Auto Project Creator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Create project with random name
  %(prog)s --name P1234              # Create project with specific name
  %(prog)s --dry-run                 # Preview without creating
  %(prog)s --list                    # List existing projects
  %(prog)s --config my_config.yaml   # Use custom configuration
        """
    )
    
    parser.add_argument(
        "--name",
        help="Project name (Letter+4digits). Random if omitted."
    )
    
    parser.add_argument(
        "--template",
        help="Path to template-config folder"
    )
    
    parser.add_argument(
        "--root",
        help="Path where projects will be created"
    )
    
    parser.add_argument(
        "--config",
        help="Path to configuration file (YAML or JSON)"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without making changes"
    )
    
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing projects without prompting"
    )
    
    parser.add_argument(
        "--list",
        action="store_true",
        help="List existing projects"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    return parser.parse_args()

# --- Main Execution ---------------------------------------------------------
def main() -> int:
    """
    Main entry point for the application.
    
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    try:
        # Parse arguments
        args = parse_arguments()
        
        # Setup logging
        global logger
        logger = setup_logging(args.verbose)
        
        # Load configuration
        config = Config()
        if args.config:
            config = Config.from_file(Path(args.config))
        
        # Override config with CLI arguments
        if args.template:
            config.template_dir = Path(args.template)
        if args.root:
            config.project_root = Path(args.root)
        
        # Create manager
        manager = CapCutProjectManager(config)
        
        # Handle list command
        if args.list:
            projects = manager.list_projects()
            if projects:
                print("\n📋 Existing projects:")
                for proj in projects:
                    print(f"  • {proj}")
            else:
                print("No projects found.")
            return ExitCode.SUCCESS.value
        
        # Generate or validate project name
        if args.name:
            project_name = args.name.strip()
            if not ProjectNameValidator.validate(project_name):
                logger.error(f"Invalid project name format: {project_name}")
                logger.info("Expected format: Letter + 4 digits (e.g., A1234)")
                return ExitCode.INVALID_INPUT.value
        else:
            project_name = ProjectNameValidator.generate_random()
            logger.info(f"Generated project name: {project_name}")
        
        # Create project
        project_path = manager.create_project(
            project_name,
            dry_run=args.dry_run,
            force=args.force
        )
        
        # Output for script integration
        if not args.dry_run:
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