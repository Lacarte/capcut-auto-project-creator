#!/usr/bin/env python3
"""
CapCut Project Doctor - Complete Diagnostic & Repair
===================================================
This script diagnoses and fixes all ID synchronization issues in CapCut projects.

Usage:
    python capcut_project_doctor.py --project /path/to/project/folder --fix
    python capcut_project_doctor.py --project P1234 --diagnose  # Just check issues
"""

import argparse
import json
import shutil
from pathlib import Path
from typing import Dict, Any, List, Tuple
from datetime import datetime

class CapCutProjectDoctor:
    def __init__(self, project_path: Path):
        self.project_path = project_path.resolve()
        self.meta_path = self.project_path / "draft_meta_info.json"
        self.content_path = self.project_path / "draft_content.json"  
        self.store_path = self.project_path / "draft_virtual_store.json"
        
        self.issues = []
        self.meta_data = None
        self.content_data = None
        self.store_data = None
        
    def load_files(self) -> bool:
        """Load all JSON files and return True if successful."""
        try:
            if self.meta_path.exists():
                with self.meta_path.open('r', encoding='utf-8') as f:
                    self.meta_data = json.load(f)
            else:
                self.issues.append("❌ draft_meta_info.json not found")
                return False
                
            if self.content_path.exists():
                with self.content_path.open('r', encoding='utf-8') as f:
                    self.content_data = json.load(f)
            else:
                self.issues.append("❌ draft_content.json not found")
                return False
                
            if self.store_path.exists():
                with self.store_path.open('r', encoding='utf-8') as f:
                    self.store_data = json.load(f)
            else:
                self.issues.append("❌ draft_virtual_store.json not found")
                return False
                
            return True
        except Exception as e:
            self.issues.append(f"❌ Failed to load files: {e}")
            return False
    
    def extract_meta_materials(self) -> List[Tuple[str, str, int, int]]:
        """Extract (id, path, width, height) from meta file."""
        materials = []
        for bucket in self.meta_data.get("draft_materials", []):
            if bucket.get("type") == 0:  # Image materials
                for item in bucket.get("value", []):
                    if item.get("metetype") == "photo":  # Skip placeholder
                        materials.append((
                            item["id"],
                            item["file_Path"], 
                            item["width"],
                            item["height"]
                        ))
        return materials
    
    def extract_content_material_ids(self) -> List[str]:
        """Extract material IDs from content file video materials."""
        videos = self.content_data.get("materials", {}).get("videos", [])
        return [video["id"] for video in videos if video.get("type") == "photo"]
    
    def extract_store_material_ids(self) -> List[str]:
        """Extract material IDs from virtual store."""
        for bucket in self.store_data.get("draft_virtual_store", []):
            if bucket.get("type") == 1:  # Material links
                return [link["child_id"] for link in bucket.get("value", [])]
        return []
    
    def diagnose(self) -> Dict[str, Any]:
        """Run comprehensive diagnosis and return report."""
        if not self.load_files():
            return {"success": False, "issues": self.issues}
        
        # Extract material IDs from all files
        meta_materials = self.extract_meta_materials()
        content_ids = self.extract_content_material_ids()
        store_ids = self.extract_store_material_ids()
        
        meta_ids = [mat[0] for mat in meta_materials]
        
        report = {
            "success": True,
            "project_path": str(self.project_path),
            "meta_materials_count": len(meta_materials),
            "content_materials_count": len(content_ids), 
            "store_materials_count": len(store_ids),
            "meta_ids": meta_ids,
            "content_ids": content_ids,
            "store_ids": store_ids,
            "issues": [],
            "id_synchronization": {
                "meta_content_match": meta_ids == content_ids,
                "meta_store_match": meta_ids == store_ids,
                "content_store_match": content_ids == store_ids
            }
        }
        
        # Check ID synchronization
        if not report["id_synchronization"]["meta_content_match"]:
            report["issues"].append("❌ Material IDs don't match between meta and content files")
            
        if not report["id_synchronization"]["meta_store_match"]:
            report["issues"].append("❌ Material IDs don't match between meta and store files")
            
        if not report["id_synchronization"]["content_store_match"]:
            report["issues"].append("❌ Material IDs don't match between content and store files")
        
        # Check timeline segments
        tracks = self.content_data.get("tracks", [])
        if tracks:
            segments = tracks[0].get("segments", [])
            segment_material_ids = [seg["material_id"] for seg in segments]
            
            if segment_material_ids != content_ids:
                report["issues"].append("❌ Timeline segments reference wrong material IDs")
            
            report["timeline_segments_count"] = len(segments)
            report["segment_material_ids"] = segment_material_ids
        
        # Check if files exist  
        missing_files = []
        for mat_id, file_path, w, h in meta_materials:
            if not Path(file_path).exists():
                missing_files.append(file_path)
        
        if missing_files:
            report["issues"].append(f"❌ {len(missing_files)} image files are missing")
            report["missing_files"] = missing_files
        
        # Overall health check
        if len(report["issues"]) == 0:
            report["issues"].append("✅ Project appears healthy")
            
        return report
    
    def repair(self) -> bool:
        """Repair all synchronization issues."""
        print("🔧 Starting repair process...")
        
        # Create backups
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.project_path / f"backup_{timestamp}"
        backup_dir.mkdir(exist_ok=True)
        
        for file_path in [self.meta_path, self.content_path, self.store_path]:
            if file_path.exists():
                shutil.copy2(file_path, backup_dir / file_path.name)
        print(f"📦 Created backup in: {backup_dir}")
        
        if not self.load_files():
            return False
        
        # Step 1: Use meta file as the source of truth
        meta_materials = self.extract_meta_materials()
        if not meta_materials:
            print("❌ No photo materials found in meta file")
            return False
        
        print(f"📋 Found {len(meta_materials)} materials in meta file")
        
        # Step 2: Rebuild content file materials and timeline
        self._rebuild_content_materials(meta_materials)
        
        # Step 3: Rebuild virtual store
        self._rebuild_virtual_store()
        
        # Step 4: Save all files
        self._save_files()
        
        print("✅ Repair completed successfully")
        return True
    
    def _rebuild_content_materials(self, meta_materials: List[Tuple[str, str, int, int]]):
        """Rebuild content materials and timeline using meta IDs."""
        import uuid
        
        # Clear existing materials
        materials = self.content_data.setdefault("materials", {})
        materials["videos"] = []
        materials.setdefault("canvases", [])
        materials.setdefault("placeholder_infos", [])
        materials.setdefault("sound_channel_mappings", [])
        materials.setdefault("speeds", [])
        materials.setdefault("material_colors", [])
        materials.setdefault("vocal_separations", [])
        materials.setdefault("transitions", [])
        
        # Clear timeline
        tracks = self.content_data.setdefault("tracks", [])
        if not tracks:
            tracks.append({"id": str(uuid.uuid4()), "type": "video", "segments": []})
        tracks[0]["segments"] = []
        
        duration_us = 5_000_000  # 5 seconds per image
        start_us = 0
        
        for idx, (mat_id, img_path, width, height) in enumerate(meta_materials):
            # Create video material with existing ID
            video_material = self._create_video_material(mat_id, img_path, width, height)
            materials["videos"].append(video_material)
            
            # Create auxiliary materials
            canvas = self._create_canvas()
            materials["canvases"].append(canvas)
            
            placeholder = self._create_placeholder()
            materials["placeholder_infos"].append(placeholder)
            
            sound_map = self._create_sound_mapping()
            materials["sound_channel_mappings"].append(sound_map)
            
            speed = self._create_speed()
            materials["speeds"].append(speed)
            
            color = self._create_material_color()
            materials["material_colors"].append(color)
            
            vocal = self._create_vocal_separation()
            materials["vocal_separations"].append(vocal)
            
            # Create timeline segment
            extra_refs = [speed["id"], placeholder["id"], canvas["id"], 
                         sound_map["id"], color["id"], vocal["id"]]
            
            # Add transition for segments after the first
            if idx > 0:
                transition = self._create_transition()
                materials["transitions"].append(transition)
                # Insert transition in previous segment
                if tracks[0]["segments"]:
                    prev_refs = tracks[0]["segments"][-1]["extra_material_refs"]
                    if len(prev_refs) >= 2:
                        prev_refs.insert(2, transition["id"])
            
            segment = self._create_segment(mat_id, start_us, duration_us, extra_refs)
            tracks[0]["segments"].append(segment)
            start_us += duration_us
        
        # Update timeline duration
        self.content_data["duration"] = start_us
        
    def _rebuild_virtual_store(self):
        """Rebuild virtual store with correct IDs."""
        meta_materials = self.extract_meta_materials()
        all_meta_ids = [item["id"] for bucket in self.meta_data.get("draft_materials", [])
                       if bucket.get("type") == 0 for item in bucket.get("value", [])]
        
        self.store_data = {
            "draft_materials": [],
            "draft_virtual_store": [
                {"type": 0, "value": [{"creation_time": 0, "display_name": "", "filter_type": 0,
                                      "id": "", "import_time": 0, "import_time_us": 0,
                                      "sort_sub_type": 0, "sort_type": 0}]},
                {"type": 1, "value": [{"child_id": mid, "parent_id": ""} for mid in all_meta_ids]},
                {"type": 2, "value": []}
            ]
        }
    
    def _save_files(self):
        """Save all modified files."""
        with self.content_path.open('w', encoding='utf-8') as f:
            json.dump(self.content_data, f, indent=2, ensure_ascii=False)
        
        with self.store_path.open('w', encoding='utf-8') as f:
            json.dump(self.store_data, f, indent=2, ensure_ascii=False)
    
    # Helper methods for creating CapCut structures
    def _create_video_material(self, mat_id: str, path: str, width: int, height: int) -> Dict[str, Any]:
        return {
            "aigc_history_id": "", "aigc_item_id": "", "aigc_type": "none",
            "audio_fade": None, "beauty_body_preset_id": "", 
            "beauty_face_auto_preset": {"name": "", "preset_id": "", "rate_map": "", "scene": ""},
            "beauty_face_auto_preset_infos": [], "beauty_face_preset_infos": [],
            "cartoon_path": "", "category_id": "", "category_name": "local",
            "check_flag": 62978047, "content_feature_info": None, "corner_pin": None,
            "crop": {"lower_left_x": 0.0, "lower_left_y": 1.0, "lower_right_x": 1.0,
                    "lower_right_y": 1.0, "upper_left_x": 0.0, "upper_left_y": 0.0,
                    "upper_right_x": 1.0, "upper_right_y": 0.0},
            "crop_ratio": "free", "crop_scale": 1.0, "duration": 10800000000,
            "extra_type_option": 0, "formula_id": "", "freeze": None,
            "has_audio": False, "has_sound_separated": False, "height": height,
            "id": mat_id, "intensifies_audio_path": "", "intensifies_path": "",
            "is_ai_generate_content": False, "is_copyright": False,
            "is_text_edit_overdub": False, "is_unified_beauty_mode": False,
            "live_photo_cover_path": "", "live_photo_timestamp": -1,
            "local_id": "", "local_material_from": "", "local_material_id": "",
            "material_id": "", "material_name": Path(path).name, "material_url": "",
            "matting": {"custom_matting_id": "", "enable_matting_stroke": False,
                       "expansion": 0, "feather": 0, "flag": 0, "has_use_quick_brush": False,
                       "has_use_quick_eraser": False, "interactiveTime": [], "path": "",
                       "reverse": False, "strokes": []},
            "media_path": "", "multi_camera_info": None, "object_locked": None,
            "origin_material_id": "", "path": path, "picture_from": "none",
            "picture_set_category_id": "", "picture_set_category_name": "",
            "request_id": "", "reverse_intensifies_path": "", "reverse_path": "",
            "smart_match_info": None, "smart_motion": None, "source": 0,
            "source_platform": 0, "stable": {"matrix_path": "", "stable_level": 0,
                                            "time_range": {"duration": 0, "start": 0}},
            "team_id": "", "type": "photo", "video_algorithm": {
                "ai_background_configs": [], "ai_expression_driven": None,
                "ai_in_painting_config": [], "ai_motion_driven": None,
                "aigc_generate": None, "algorithms": [], "complement_frame_config": None,
                "deflicker": None, "gameplay_configs": [], "image_interpretation": None,
                "motion_blur_config": None, "mouth_shape_driver": None,
                "noise_reduction": None, "path": "", "quality_enhance": None,
                "smart_complement_frame": None, "story_video_modify_video_config": {
                    "is_overwrite_last_video": False, "task_id": "", "tracker_task_id": ""},
                "super_resolution": None, "time_range": None},
            "width": width
        }
    
    def _create_canvas(self) -> Dict[str, Any]:
        import uuid
        return {"album_image": "", "blur": 0.0, "color": "", "id": str(uuid.uuid4()),
               "image": "", "image_id": "", "image_name": "", "source_platform": 0,
               "team_id": "", "type": "canvas_color"}
    
    def _create_placeholder(self) -> Dict[str, Any]:
        import uuid
        return {"error_path": "", "error_text": "", "id": str(uuid.uuid4()),
               "meta_type": "none", "res_path": "", "res_text": "", "type": "placeholder_info"}
    
    def _create_sound_mapping(self) -> Dict[str, Any]:
        import uuid
        return {"audio_channel_mapping": 0, "id": str(uuid.uuid4()),
               "is_config_open": False, "type": ""}
    
    def _create_speed(self) -> Dict[str, Any]:
        import uuid
        return {"curve_speed": None, "id": str(uuid.uuid4()), "mode": 0,
               "speed": 1.0, "type": "speed"}
    
    def _create_material_color(self) -> Dict[str, Any]:
        import uuid
        return {"gradient_angle": 90.0, "gradient_colors": [], "gradient_percents": [],
               "height": 0.0, "id": str(uuid.uuid4()), "is_color_clip": False,
               "is_gradient": False, "solid_color": "", "width": 0.0}
    
    def _create_vocal_separation(self) -> Dict[str, Any]:
        import uuid
        return {"choice": 0, "enter_from": "", "final_algorithm": "",
               "id": str(uuid.uuid4()), "production_path": "", "removed_sounds": [],
               "time_range": None, "type": "vocal_separation"}
    
    def _create_transition(self) -> Dict[str, Any]:
        import uuid
        return {"id": str(uuid.uuid4()), "type": "transition", "name": "Pull in",
               "duration": 466666, "is_overlap": False, "category_name": "remen",
               "platform": "all"}
    
    def _create_segment(self, material_id: str, start_us: int, duration_us: int, 
                       extra_refs: List[str]) -> Dict[str, Any]:
        import uuid
        return {
            "caption_info": None, "cartoon": False,
            "clip": {"alpha": 1.0, "flip": {"horizontal": False, "vertical": False},
                    "rotation": 0.0, "scale": {"x": 1.0, "y": 1.0},
                    "transform": {"x": 0.0, "y": 0.0}},
            "color_correct_alg_result": "", "common_keyframes": [], "desc": "",
            "digital_human_template_group_id": "", "enable_adjust": True,
            "enable_adjust_mask": False, "enable_color_correct_adjust": False,
            "enable_color_curves": True, "enable_color_match_adjust": False,
            "enable_color_wheels": True, "enable_hsl": False, "enable_hsl_curves": True,
            "enable_lut": True, "enable_smart_color_adjust": False, "enable_video_mask": True,
            "extra_material_refs": extra_refs, "group_id": "",
            "hdr_settings": {"intensity": 1.0, "mode": 1, "nits": 1000},
            "id": str(uuid.uuid4()), "intensifies_audio": False, "is_loop": False,
            "is_placeholder": False, "is_tone_modify": False, "keyframe_refs": [],
            "last_nonzero_volume": 1.0, "lyric_keyframes": None,
            "material_id": material_id, "raw_segment_id": "", "render_index": 0,
            "render_timerange": {"duration": 0, "start": 0},
            "responsive_layout": {"enable": False, "horizontal_pos_layout": 0,
                                "size_layout": 0, "target_follow": "", "vertical_pos_layout": 0},
            "reverse": False, "source": "segmentsourcenormal",
            "source_timerange": {"duration": duration_us, "start": 0}, "speed": 1.0,
            "state": 0, "target_timerange": {"duration": duration_us, "start": start_us},
            "template_id": "", "template_scene": "default", "track_attribute": 0,
            "track_render_index": 0, "uniform_scale": {"on": True, "value": 1.0},
            "visible": True, "volume": 1.0
        }

def main():
    parser = argparse.ArgumentParser(description="CapCut Project Doctor - Diagnose and repair projects")
    parser.add_argument("--project", required=True, help="Path to project folder")
    parser.add_argument("--diagnose", action="store_true", help="Only diagnose issues (don't repair)")
    parser.add_argument("--fix", action="store_true", help="Repair the project")
    
    args = parser.parse_args()
    
    project_path = Path(args.project)
    if not project_path.is_absolute():
        project_path = Path.cwd() / args.project
    
    if not project_path.exists():
        print(f"❌ Project not found: {project_path}")
        return 1
    
    doctor = CapCutProjectDoctor(project_path)
    
    # Always run diagnosis first
    print("🔍 Running project diagnosis...")
    report = doctor.diagnose()
    
    if not report["success"]:
        print("❌ Failed to diagnose project")
        for issue in report["issues"]:
            print(f"  {issue}")
        return 1
    
    # Print diagnosis report
    print(f"\n📊 Project: {report['project_path']}")
    print(f"📁 Meta materials: {report['meta_materials_count']}")
    print(f"🎬 Content materials: {report['content_materials_count']}")
    print(f"🗃️ Store materials: {report['store_materials_count']}")
    
    if 'timeline_segments_count' in report:
        print(f"📹 Timeline segments: {report['timeline_segments_count']}")
    
    print(f"\n🔗 ID Synchronization:")
    sync = report["id_synchronization"]
    print(f"  Meta ↔ Content: {'✅' if sync['meta_content_match'] else '❌'}")
    print(f"  Meta ↔ Store:   {'✅' if sync['meta_store_match'] else '❌'}")
    print(f"  Content ↔ Store: {'✅' if sync['content_store_match'] else '❌'}")
    
    print(f"\n🎯 Issues found:")
    for issue in report["issues"]:
        print(f"  {issue}")
    
    # Show ID details if there are mismatches
    if not all(sync.values()):
        print(f"\n🔍 ID Details:")
        print(f"  Meta IDs:    {report['meta_ids']}")
        print(f"  Content IDs: {report['content_ids']}")
        print(f"  Store IDs:   {report['store_ids']}")
        
        if 'segment_material_ids' in report:
            print(f"  Segment IDs: {report['segment_material_ids']}")
    
    # Repair if requested
    if args.fix:
        if not all(sync.values()) or len([i for i in report["issues"] if i.startswith("❌")]) > 0:
            success = doctor.repair()
            if success:
                print("\n✅ Project repaired successfully!")
                print("🎬 Try opening it in CapCut now.")
            else:
                print("\n❌ Repair failed")
                return 1
        else:
            print("\n✅ Project is already healthy, no repair needed.")
    elif not args.diagnose:
        print(f"\n💡 To fix these issues, run with --fix flag")
    
    return 0

if __name__ == "__main__":
    exit(main())
