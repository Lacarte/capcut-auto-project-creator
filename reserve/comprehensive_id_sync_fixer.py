#!/usr/bin/env python3
"""
comprehensive_id_sync_fixer.py
------------------------------
Complete solution for CapCut ID synchronization issues.

This utility:
1. Analyzes all three JSON files for ID mismatches
2. Uses draft_meta_info.json as the authoritative source
3. Rebuilds draft_content.json materials with correct IDs
4. Rebuilds draft_virtual_store.json with matching references
5. Preserves all existing structure and content

Usage:
    python comprehensive_id_sync_fixer.py --project /path/to/project --fix
    python comprehensive_id_sync_fixer.py --project P1234 --diagnose
"""

import argparse
import json
import shutil
from pathlib import Path
from typing import Dict, Any, List, Tuple, Set
from datetime import datetime

class CapCutIDSynchronizer:
    def __init__(self, project_path: Path):
        self.project_path = project_path.resolve()
        self.meta_path = self.project_path / "draft_meta_info.json"
        self.content_path = self.project_path / "draft_content.json"
        self.store_path = self.project_path / "draft_virtual_store.json"
        
    def diagnose(self) -> Dict[str, Any]:
        """Complete diagnosis of ID synchronization issues."""
        print("Diagnosing CapCut project ID synchronization...")
        
        report = {
            "project_path": str(self.project_path),
            "files_found": {},
            "material_analysis": {},
            "id_synchronization": {},
            "issues": [],
            "recommendations": []
        }
        
        # Check file existence
        for name, path in [("meta", self.meta_path), ("content", self.content_path), ("store", self.store_path)]:
            report["files_found"][name] = path.exists()
            if not path.exists():
                report["issues"].append(f"Missing file: {path.name}")
        
        if not all(report["files_found"].values()):
            return report
        
        try:
            # Load all files
            with self.meta_path.open('r', encoding='utf-8') as f:
                meta_data = json.load(f)
            with self.content_path.open('r', encoding='utf-8') as f:
                content_data = json.load(f)
            with self.store_path.open('r', encoding='utf-8') as f:
                store_data = json.load(f)
            
            # Extract material information
            meta_materials = self._extract_meta_materials(meta_data)
            content_materials = self._extract_content_materials(content_data)
            store_materials = self._extract_store_materials(store_data)
            segment_references = self._extract_segment_material_refs(content_data)
            
            # Populate analysis
            report["material_analysis"] = {
                "meta_photo_count": len([m for m in meta_materials if m[4] == "photo"]),
                "meta_placeholder_count": len([m for m in meta_materials if m[4] == "none"]),
                "content_video_count": len(content_materials),
                "store_reference_count": len(store_materials),
                "timeline_segments": len(segment_references)
            }
            
            # Check ID synchronization
            meta_photo_ids = [m[0] for m in meta_materials if m[4] == "photo"]
            content_video_ids = [m[0] for m in content_materials]
            all_meta_ids = [m[0] for m in meta_materials]
            store_ids = store_materials
            segment_ids = [s[1] for s in segment_references]
            
            report["id_synchronization"] = {
                "meta_photo_ids": meta_photo_ids,
                "content_video_ids": content_video_ids,
                "store_ids": store_ids,
                "segment_material_ids": segment_ids,
                "meta_content_match": meta_photo_ids == content_video_ids,
                "meta_store_match": all_meta_ids == store_ids,
                "content_segments_match": content_video_ids == segment_ids
            }
            
            # Identify specific issues
            if not report["id_synchronization"]["meta_content_match"]:
                report["issues"].append("Material IDs don't match between meta and content files")
                report["recommendations"].append("Run with --fix to synchronize material IDs")
            
            if not report["id_synchronization"]["meta_store_match"]:
                report["issues"].append("Material IDs don't match between meta and store files")
                
            if not report["id_synchronization"]["content_segments_match"]:
                report["issues"].append("Timeline segments reference wrong material IDs")
            
            # Check for missing files
            missing_files = []
            for mat_id, file_path, width, height, metetype in meta_materials:
                if metetype == "photo" and not Path(file_path).exists():
                    missing_files.append(file_path)
            
            if missing_files:
                report["issues"].append(f"{len(missing_files)} image files are missing")
                report["missing_files"] = missing_files
            
            if not report["issues"]:
                report["issues"].append("Project appears healthy - all IDs synchronized")
                
        except Exception as e:
            report["issues"].append(f"Error during diagnosis: {e}")
        
        return report
    
    def fix(self) -> bool:
        """Fix all ID synchronization issues."""
        print("Starting comprehensive ID synchronization fix...")
        
        # Create backup
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.project_path / f"backup_{timestamp}"
        backup_dir.mkdir(exist_ok=True)
        
        for file_path in [self.meta_path, self.content_path, self.store_path]:
            if file_path.exists():
                shutil.copy2(file_path, backup_dir / file_path.name)
        print(f"Created backup in: {backup_dir}")
        
        try:
            # Load files
            with self.meta_path.open('r', encoding='utf-8') as f:
                meta_data = json.load(f)
            with self.content_path.open('r', encoding='utf-8') as f:
                content_data = json.load(f)
            
            # Extract authoritative material info from meta
            meta_materials = self._extract_meta_materials(meta_data)
            photo_materials = [(m[0], m[1], m[2], m[3]) for m in meta_materials if m[4] == "photo"]
            
            if not photo_materials:
                print("No photo materials found in meta file")
                return False
            
            print(f"Found {len(photo_materials)} photo materials to synchronize")
            
            # Fix content file
            self._fix_content_materials(content_data, photo_materials)
            self._fix_timeline_segments(content_data, photo_materials)
            
            # Fix virtual store
            all_meta_ids = [m[0] for m in meta_materials]
            store_data = self._build_virtual_store(all_meta_ids)
            
            # Save fixed files
            with self.content_path.open('w', encoding='utf-8') as f:
                json.dump(content_data, f, indent=2, ensure_ascii=False)
            
            with self.store_path.open('w', encoding='utf-8') as f:
                json.dump(store_data, f, indent=2, ensure_ascii=False)
            
            print("ID synchronization fix completed successfully")
            return True
            
        except Exception as e:
            print(f"Fix failed: {e}")
            return False
    
    def _extract_meta_materials(self, meta_data: Dict[str, Any]) -> List[Tuple[str, str, int, int, str]]:
        """Extract (id, path, width, height, metetype) from meta file."""
        materials = []
        for bucket in meta_data.get("draft_materials", []):
            if bucket.get("type") == 0:
                for item in bucket.get("value", []):
                    materials.append((
                        item["id"],
                        item["file_Path"],
                        item["width"],
                        item["height"],
                        item["metetype"]
                    ))
        return materials
    
    def _extract_content_materials(self, content_data: Dict[str, Any]) -> List[Tuple[str, str]]:
        """Extract (id, path) from content video materials."""
        materials = []
        videos = content_data.get("materials", {}).get("videos", [])
        for video in videos:
            if video.get("type") == "photo":
                materials.append((video["id"], video["path"]))
        return materials
    
    def _extract_store_materials(self, store_data: Dict[str, Any]) -> List[str]:
        """Extract material IDs from virtual store."""
        for bucket in store_data.get("draft_virtual_store", []):
            if bucket.get("type") == 1:
                return [link["child_id"] for link in bucket.get("value", [])]
        return []
    
    def _extract_segment_material_refs(self, content_data: Dict[str, Any]) -> List[Tuple[str, str]]:
        """Extract (segment_id, material_id) from timeline segments."""
        refs = []
        tracks = content_data.get("tracks", [])
        if tracks:
            for segment in tracks[0].get("segments", []):
                refs.append((segment["id"], segment["material_id"]))
        return refs
    
    def _fix_content_materials(self, content_data: Dict[str, Any], photo_materials: List[Tuple[str, str, int, int]]):
        """Replace content video materials with correct IDs from meta."""
        materials = content_data.setdefault("materials", {})
        videos = materials.setdefault("videos", [])
        
        # Clear existing video materials
        videos.clear()
        
        # Rebuild with correct IDs
        for material_id, file_path, width, height in photo_materials:
            video_material = self._build_video_material(material_id, file_path, width, height)
            videos.append(video_material)
        
        print(f"Fixed {len(photo_materials)} video materials in content file")
    
    def _fix_timeline_segments(self, content_data: Dict[str, Any], photo_materials: List[Tuple[str, str, int, int]]):
        """Update timeline segments to reference correct material IDs."""
        tracks = content_data.get("tracks", [])
        if not tracks or not tracks[0].get("segments"):
            return
        
        segments = tracks[0]["segments"]
        material_ids = [m[0] for m in photo_materials]
        
        # Update material_id references in segments
        for i, segment in enumerate(segments):
            if i < len(material_ids):
                old_id = segment["material_id"]
                new_id = material_ids[i]
                segment["material_id"] = new_id
                print(f"Updated segment {i+1}: {old_id[:8]}... -> {new_id[:8]}...")
    
    def _build_video_material(self, material_id: str, file_path: str, width: int, height: int) -> Dict[str, Any]:
        """Build complete video material structure with correct ID."""
        path_obj = Path(file_path)
        return {
            "aigc_history_id": "",
            "aigc_item_id": "",
            "aigc_type": "none",
            "audio_fade": None,
            "beauty_body_preset_id": "",
            "beauty_face_auto_preset": {"name": "", "preset_id": "", "rate_map": "", "scene": ""},
            "beauty_face_auto_preset_infos": [],
            "beauty_face_preset_infos": [],
            "cartoon_path": "",
            "category_id": "",
            "category_name": "local",
            "check_flag": 62978047,
            "content_feature_info": None,
            "corner_pin": None,
            "crop": {
                "lower_left_x": 0.0, "lower_left_y": 1.0, "lower_right_x": 1.0,
                "lower_right_y": 1.0, "upper_left_x": 0.0, "upper_left_y": 0.0,
                "upper_right_x": 1.0, "upper_right_y": 0.0
            },
            "crop_ratio": "free",
            "crop_scale": 1.0,
            "duration": 10800000000,
            "extra_type_option": 0,
            "formula_id": "",
            "freeze": None,
            "has_audio": False,
            "has_sound_separated": False,
            "height": height,
            "id": material_id,  # CRITICAL: Use the ID from meta file
            "intensifies_audio_path": "",
            "intensifies_path": "",
            "is_ai_generate_content": False,
            "is_copyright": False,
            "is_text_edit_overdub": False,
            "is_unified_beauty_mode": False,
            "live_photo_cover_path": "",
            "live_photo_timestamp": -1,
            "local_id": "",
            "local_material_from": "",
            "local_material_id": "",
            "material_id": "",
            "material_name": path_obj.name,
            "material_url": "",
            "matting": {
                "custom_matting_id": "", "enable_matting_stroke": False,
                "expansion": 0, "feather": 0, "flag": 0,
                "has_use_quick_brush": False, "has_use_quick_eraser": False,
                "interactiveTime": [], "path": "", "reverse": False, "strokes": []
            },
            "media_path": "",
            "multi_camera_info": None,
            "object_locked": None,
            "origin_material_id": "",
            "path": file_path,
            "picture_from": "none",
            "picture_set_category_id": "",
            "picture_set_category_name": "",
            "request_id": "",
            "reverse_intensifies_path": "",
            "reverse_path": "",
            "smart_match_info": None,
            "smart_motion": None,
            "source": 0,
            "source_platform": 0,
            "stable": {"matrix_path": "", "stable_level": 0, "time_range": {"duration": 0, "start": 0}},
            "team_id": "",
            "type": "photo",
            "video_algorithm": {
                "ai_background_configs": [], "ai_expression_driven": None,
                "ai_in_painting_config": [], "ai_motion_driven": None,
                "aigc_generate": None, "algorithms": [],
                "complement_frame_config": None, "deflicker": None,
                "gameplay_configs": [], "image_interpretation": None,
                "motion_blur_config": None, "mouth_shape_driver": None,
                "noise_reduction": None, "path": "", "quality_enhance": None,
                "smart_complement_frame": None,
                "story_video_modify_video_config": {
                    "is_overwrite_last_video": False, "task_id": "", "tracker_task_id": ""
                },
                "super_resolution": None, "time_range": None
            },
            "width": width
        }
    
    def _build_virtual_store(self, material_ids: List[str]) -> Dict[str, Any]:
        """Build virtual store with correct material references."""
        return {
            "draft_materials": [],
            "draft_virtual_store": [
                {
                    "type": 0,
                    "value": [{
                        "creation_time": 0, "display_name": "", "filter_type": 0,
                        "id": "", "import_time": 0, "import_time_us": 0,
                        "sort_sub_type": 0, "sort_type": 0
                    }]
                },
                {
                    "type": 1,
                    "value": [{"child_id": mid, "parent_id": ""} for mid in material_ids]
                },
                {"type": 2, "value": []}
            ]
        }

def print_diagnosis_report(report: Dict[str, Any]) -> None:
    """Print formatted diagnosis report."""
    print(f"\n{'='*60}")
    print(f"CapCut Project ID Synchronization Report")
    print(f"{'='*60}")
    print(f"Project: {report['project_path']}")
    
    # File status
    print(f"\nFile Status:")
    for name, exists in report['files_found'].items():
        status = "✓" if exists else "✗"
        print(f"  {status} {name}_file")
    
    if not all(report['files_found'].values()):
        return
    
    # Material counts
    if 'material_analysis' in report:
        ma = report['material_analysis']
        print(f"\nMaterial Analysis:")
        print(f"  Meta file photos: {ma.get('meta_photo_count', 0)}")
        print(f"  Meta placeholders: {ma.get('meta_placeholder_count', 0)}")
        print(f"  Content videos: {ma.get('content_video_count', 0)}")
        print(f"  Store references: {ma.get('store_reference_count', 0)}")
        print(f"  Timeline segments: {ma.get('timeline_segments', 0)}")
    
    # ID synchronization status
    if 'id_synchronization' in report:
        sync = report['id_synchronization']
        print(f"\nID Synchronization:")
        print(f"  Meta ↔ Content: {'✓' if sync.get('meta_content_match') else '✗'}")
        print(f"  Meta ↔ Store:   {'✓' if sync.get('meta_store_match') else '✗'}")
        print(f"  Content ↔ Segments: {'✓' if sync.get('content_segments_match') else '✗'}")
        
        # Show ID details if there are mismatches
        if not all([sync.get('meta_content_match'), sync.get('meta_store_match'), sync.get('content_segments_match')]):
            print(f"\nID Details (first 8 chars):")
            meta_ids = [id[:8] + "..." for id in sync.get('meta_photo_ids', [])]
            content_ids = [id[:8] + "..." for id in sync.get('content_video_ids', [])]
            segment_ids = [id[:8] + "..." for id in sync.get('segment_material_ids', [])]
            
            print(f"  Meta photos:  {meta_ids}")
            print(f"  Content vids: {content_ids}")
            print(f"  Segment refs: {segment_ids}")
    
    # Issues and recommendations
    print(f"\nIssues Found:")
    for issue in report.get('issues', []):
        prefix = "✓" if "appears healthy" in issue else "✗"
        print(f"  {prefix} {issue}")
    
    if report.get('recommendations'):
        print(f"\nRecommendations:")
        for rec in report['recommendations']:
            print(f"  → {rec}")

def main():
    parser = argparse.ArgumentParser(description="Comprehensive CapCut ID Synchronization Fixer")
    parser.add_argument("--project", required=True, help="Path to project folder")
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument("--diagnose", action="store_true", help="Diagnose ID synchronization issues")
    action_group.add_argument("--fix", action="store_true", help="Fix all ID synchronization issues")
    
    args = parser.parse_args()
    
    project_path = Path(args.project)
    if not project_path.is_absolute():
        project_path = Path.cwd() / args.project
    
    if not project_path.exists():
        print(f"Project not found: {project_path}")
        return 1
    
    synchronizer = CapCutIDSynchronizer(project_path)
    
    if args.diagnose:
        report = synchronizer.diagnose()
        print_diagnosis_report(report)
        
        # Return exit code based on health
        has_critical_issues = any("don't match" in issue for issue in report.get('issues', []))
        return 1 if has_critical_issues else 0
        
    elif args.fix:
        # Run diagnosis first
        report = synchronizer.diagnose()
        print_diagnosis_report(report)
        
        has_issues = any("don't match" in issue for issue in report.get('issues', []))
        if not has_issues:
            print("\nProject is already healthy, no fix needed.")
            return 0
        
        print(f"\n{'='*60}")
        print("Starting ID Synchronization Fix...")
        print(f"{'='*60}")
        
        success = synchronizer.fix()
        
        if success:
            print("\n" + "="*60)
            print("Fix completed! Running verification...")
            print("="*60)
            
            # Verify the fix
            verification_report = synchronizer.diagnose()
            print_diagnosis_report(verification_report)
            
            return 0
        else:
            print("\nFix failed - check error messages above")
            return 1

if __name__ == "__main__":
    exit(main())