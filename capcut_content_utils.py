"""
capcut_content_utils.py - IMPROVED VERSION
------------------------------------------
Enhanced with:
1. Proper ID synchronization from meta file
2. Missing essential fields that CapCut requires
3. Better structure matching manual projects
4. Comprehensive material building with all required properties
"""

from __future__ import annotations

import argparse
import json
import uuid
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# ---------- ID Synchronization + Enhanced Material Extraction ---------------

def extract_material_ids_from_meta(meta_path: Path) -> List[Tuple[str, Path, int, int]]:
    """
    Extract material info from draft_meta_info.json with enhanced validation.
    Returns list of (id, path, width, height) tuples for photo materials.
    """
    with meta_path.open("r", encoding="utf-8") as f:
        meta = json.load(f)
    
    materials = []
    draft_materials = meta.get("draft_materials", [])
    
    for bucket in draft_materials:
        if isinstance(bucket, dict) and bucket.get("type") == 0:  # images/photos
            for item in bucket.get("value", []):
                if item.get("metetype") == "photo":  # Skip "none" placeholder
                    file_path = Path(item["file_Path"])
                    # Validate file exists before adding
                    if file_path.exists():
                        materials.append((
                            item["id"],
                            file_path,
                            item["width"],
                            item["height"]
                        ))
                    else:
                        print(f"Warning: Image file not found: {file_path}")
    
    return materials

# ---------- Helpers ----------------------------------------------------------

def _now_ms_like() -> int:
    return int(time.time() * 1_000_000)

def _get_image_size(img_path: Path) -> Optional[Tuple[int, int]]:
    try:
        from PIL import Image
        with Image.open(img_path) as im:
            return im.width, im.height
    except Exception:
        return None

# ---------- Enhanced Structure Building -------------------------------------

def _ensure_materials(content: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Ensure all required material collections exist."""
    mats = content.setdefault("materials", {})
    
    def _ensure_list(key: str) -> List[Dict[str, Any]]:
        v = mats.get(key)
        if not isinstance(v, list):
            v = []
            mats[key] = v
        return v

    # Ensure ALL material types that CapCut expects
    material_types = [
        "videos", "canvases", "placeholder_infos", "sound_channel_mappings",
        "speeds", "material_colors", "vocal_separations", "transitions",
        "ai_translates", "audio_balances", "audio_effects", "audio_fades", 
        "audio_pannings", "audio_pitch_shifts", "audio_track_indexes",
        "audios", "beats", "chromas", "color_curves", "common_mask",
        "digital_human_model_dressing", "digital_humans", "drafts", "effects",
        "flowers", "green_screens", "handwrites", "hsl", "hsl_curves",
        "images", "log_color_wheels", "loudnesses", "manual_beautys",
        "manual_deformations", "material_animations", "multi_language_refs",
        "placeholders", "plugin_effects", "primary_color_wheels", 
        "realtime_denoises", "shapes", "smart_crops", "smart_relights",
        "stickers", "tail_leaders", "text_templates", "texts", "time_marks",
        "video_effects", "video_trackings", "vocal_beautifys"
    ]

    result = {}
    for mat_type in material_types:
        result[mat_type] = _ensure_list(mat_type)
    
    return result

def _ensure_tracks(content: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Ensure track structure matches CapCut's expectations."""
    tracks = content.get("tracks")
    if not isinstance(tracks, list):
        tracks = []
        content["tracks"] = tracks
    
    if not tracks:
        tracks.append({
            "attribute": 0,
            "flag": 0,
            "id": str(uuid.uuid4()),
            "is_default_name": True,
            "name": "",
            "segments": [],
            "type": "video"
        })
    
    # Ensure first track has all required fields
    track = tracks[0]
    track.setdefault("attribute", 0)
    track.setdefault("flag", 0)
    track.setdefault("is_default_name", True)
    track.setdefault("name", "")
    track.setdefault("type", "video")
    
    if "segments" not in track or not isinstance(track["segments"], list):
        track["segments"] = []
    
    return tracks

# ---------- Enhanced Material Builders --------------------------------------

def _build_video_material_with_existing_id(material_id: str, path: Path, width: int, height: int) -> Dict[str, Any]:
    """
    Build complete video material using existing ID with all required fields.
    This matches the exact structure found in working CapCut projects.
    """
    return {
        "aigc_history_id": "",
        "aigc_item_id": "",
        "aigc_type": "none",
        "audio_fade": None,
        "beauty_body_preset_id": "",
        "beauty_face_auto_preset": {
            "name": "",
            "preset_id": "",
            "rate_map": "",
            "scene": ""
        },
        "beauty_face_auto_preset_infos": [],
        "beauty_face_preset_infos": [],
        "cartoon_path": "",
        "category_id": "",
        "category_name": "local",
        "check_flag": 62978047,  # Important: this seems to be a validation flag
        "content_feature_info": None,
        "corner_pin": None,
        "crop": {
            "lower_left_x": 0.0,
            "lower_left_y": 1.0,
            "lower_right_x": 1.0,
            "lower_right_y": 1.0,
            "upper_left_x": 0.0,
            "upper_left_y": 0.0,
            "upper_right_x": 1.0,
            "upper_right_y": 0.0
        },
        "crop_ratio": "free",
        "crop_scale": 1.0,
        "duration": 10800000000,  # Large internal duration, trimmed by segments
        "extra_type_option": 0,
        "formula_id": "",
        "freeze": None,
        "has_audio": False,
        "has_sound_separated": False,
        "height": int(height),
        "id": material_id,  # CRITICAL: Use existing ID from meta
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
        "material_id": "",  # This stays empty in working projects
        "material_name": path.name,
        "material_url": "",
        "matting": {
            "custom_matting_id": "",
            "enable_matting_stroke": False,
            "expansion": 0,
            "feather": 0,
            "flag": 0,
            "has_use_quick_brush": False,
            "has_use_quick_eraser": False,
            "interactiveTime": [],
            "path": "",
            "reverse": False,
            "strokes": []
        },
        "media_path": "",
        "multi_camera_info": None,
        "object_locked": None,
        "origin_material_id": "",
        "path": str(path),
        "picture_from": "none",
        "picture_set_category_id": "",
        "picture_set_category_name": "",
        "request_id": "",
        "reverse_intensifies_path": "",
        "reverse_path": "",
        "smart_match_info": None,
        "smart_motion": None,
        "source": 0,  # Important: source varies in manual projects (0, 5, etc)
        "source_platform": 0,
        "stable": {
            "matrix_path": "",
            "stable_level": 0,
            "time_range": {
                "duration": 0,
                "start": 0
            }
        },
        "team_id": "",
        "type": "photo",  # Critical: CapCut treats images as "photo" type
        "video_algorithm": {
            "ai_background_configs": [],
            "ai_expression_driven": None,
            "ai_in_painting_config": [],
            "ai_motion_driven": None,
            "aigc_generate": None,
            "algorithms": [],
            "complement_frame_config": None,
            "deflicker": None,
            "gameplay_configs": [],
            "image_interpretation": None,
            "motion_blur_config": None,
            "mouth_shape_driver": None,
            "noise_reduction": None,
            "path": "",
            "quality_enhance": None,
            "smart_complement_frame": None,
            "story_video_modify_video_config": {
                "is_overwrite_last_video": False,
                "task_id": "",
                "tracker_task_id": ""
            },
            "super_resolution": None,
            "time_range": None
        },
        "width": int(width)
    }

def _build_enhanced_canvas() -> Dict[str, Any]:
    """Build canvas with complete field structure."""
    return {
        "album_image": "",
        "blur": 0.0,
        "color": "",
        "id": str(uuid.uuid4()),
        "image": "",
        "image_id": "",
        "image_name": "",
        "source_platform": 0,
        "team_id": "",
        "type": "canvas_color"
    }

def _build_enhanced_placeholder_info() -> Dict[str, Any]:
    """Build placeholder_info with complete field structure."""
    return {
        "error_path": "",
        "error_text": "",
        "id": str(uuid.uuid4()),
        "meta_type": "none",
        "res_path": "",
        "res_text": "",
        "type": "placeholder_info"
    }

def _build_enhanced_sound_channel_mapping() -> Dict[str, Any]:
    """Build sound_channel_mapping with complete field structure."""
    return {
        "audio_channel_mapping": 0,
        "id": str(uuid.uuid4()),
        "is_config_open": False,
        "type": ""
    }

def _build_enhanced_speed() -> Dict[str, Any]:
    """Build speed with complete field structure."""
    return {
        "curve_speed": None,
        "id": str(uuid.uuid4()),
        "mode": 0,
        "speed": 1.0,
        "type": "speed"
    }

def _build_enhanced_material_color() -> Dict[str, Any]:
    """Build material_color with complete field structure."""
    return {
        "gradient_angle": 90.0,
        "gradient_colors": [],
        "gradient_percents": [],
        "height": 0.0,
        "id": str(uuid.uuid4()),
        "is_color_clip": False,
        "is_gradient": False,
        "solid_color": "",
        "width": 0.0
    }

def _build_enhanced_vocal_separation() -> Dict[str, Any]:
    """Build vocal_separation with complete field structure."""
    return {
        "choice": 0,
        "enter_from": "",
        "final_algorithm": "",
        "id": str(uuid.uuid4()),
        "production_path": "",
        "removed_sounds": [],
        "time_range": None,
        "type": "vocal_separation"
    }

def _build_enhanced_transition(name: str = "Pull in", duration_us: int = 466_666, is_overlap: bool = False) -> Dict[str, Any]:
    """Build transition with complete field structure."""
    return {
        "id": str(uuid.uuid4()),
        "type": "transition",
        "name": name,
        "duration": int(duration_us),
        "is_overlap": bool(is_overlap),
        "category_name": "remen",
        "platform": "all"
    }

def _build_enhanced_segment(video_material_id: str,
                           start_us: int,
                           duration_us: int,
                           extra_refs: List[str]) -> Dict[str, Any]:
    """
    Build timeline segment with ALL fields that CapCut expects.
    This matches the exact structure from working manual projects.
    """
    return {
        "caption_info": None,
        "cartoon": False,
        "clip": {
            "alpha": 1.0,
            "flip": {
                "horizontal": False,
                "vertical": False
            },
            "rotation": 0.0,
            "scale": {
                "x": 1.0,
                "y": 1.0
            },
            "transform": {
                "x": 0.0,
                "y": 0.0
            }
        },
        "color_correct_alg_result": "",
        "common_keyframes": [],
        "desc": "",
        "digital_human_template_group_id": "",
        "enable_adjust": True,
        "enable_adjust_mask": False,
        "enable_color_correct_adjust": False,
        "enable_color_curves": True,
        "enable_color_match_adjust": False,
        "enable_color_wheels": True,
        "enable_hsl": False,
        "enable_hsl_curves": True,
        "enable_lut": True,
        "enable_smart_color_adjust": False,
        "enable_video_mask": True,
        "extra_material_refs": extra_refs,  # List format, not dict
        "group_id": "",
        "hdr_settings": {
            "intensity": 1.0,
            "mode": 1,
            "nits": 1000
        },
        "id": str(uuid.uuid4()),
        "intensifies_audio": False,
        "is_loop": False,
        "is_placeholder": False,
        "is_tone_modify": False,
        "keyframe_refs": [],
        "last_nonzero_volume": 1.0,
        "lyric_keyframes": None,
        "material_id": video_material_id,  # Reference to existing material
        "raw_segment_id": "",
        "render_index": 0,
        "render_timerange": {
            "duration": 0,
            "start": 0
        },
        "responsive_layout": {
            "enable": False,
            "horizontal_pos_layout": 0,
            "size_layout": 0,
            "target_follow": "",
            "vertical_pos_layout": 0
        },
        "reverse": False,
        "source": "segmentsourcenormal",
        "source_timerange": {
            "duration": int(duration_us),
            "start": 0
        },
        "speed": 1.0,
        "state": 0,
        "target_timerange": {
            "duration": int(duration_us),
            "start": int(start_us)
        },
        "template_id": "",
        "template_scene": "default",
        "track_attribute": 0,
        "track_render_index": 0,
        "uniform_scale": {
            "on": True,
            "value": 1.0
        },
        "visible": True,
        "volume": 1.0
    }

# ---------- Enhanced Top-Level Content Fields -------------------------------

def _ensure_top_level_fields(content: Dict[str, Any]) -> None:
    """Ensure all top-level content fields are present with correct defaults."""
    
    # Canvas configuration
    content.setdefault("canvas_config", {
        "background": None,
        "height": 1080,  # Changed from 1920 to match working projects
        "ratio": "original",
        "width": 1920   # Changed from 1280 to match working projects
    })
    
    content.setdefault("color_space", -1)
    content.setdefault("cover", None)
    content.setdefault("create_time", 0)
    content.setdefault("draft_type", "video")
    content.setdefault("extra_info", None)
    content.setdefault("fps", 30.0)
    content.setdefault("free_render_index_mode_on", False)
    content.setdefault("group_container", None)
    content.setdefault("is_drop_frame_timecode", False)
    content.setdefault("keyframe_graph_list", [])
    
    # Enhanced keyframes structure
    content.setdefault("keyframes", {
        "adjusts": [],
        "audios": [],
        "effects": [],
        "filters": [],
        "handwrites": [],
        "stickers": [],
        "texts": [],
        "videos": []
    })
    
    # Platform info - matches working projects
    content.setdefault("last_modified_platform", {
        "app_id": 359289,
        "app_source": "cc",
        "app_version": "7.2.0",
        "device_id": "bf2dff6abf9745a2497958638b541edf",
        "hard_disk_id": "",
        "mac_address": "cf6bd6f48b98511166f7aecac43f7c8d,4b71d2b3e08bd00e3790b0e27cb88b50",
        "os": "windows",
        "os_version": "10.0.26100"
    })
    
    content.setdefault("lyrics_effects", [])
    content.setdefault("mutable_config", None)
    content.setdefault("name", "")
    content.setdefault("new_version", "145.0.0")
    content.setdefault("path", "")
    content.setdefault("relationships", [])
    content.setdefault("render_index_track_mode_on", True)
    content.setdefault("retouch_cover", None)
    content.setdefault("source", "default")
    content.setdefault("static_cover_image_path", "")
    content.setdefault("time_marks", None)
    content.setdefault("update_time", 0)
    content.setdefault("version", 360000)
    
    # Enhanced config structure
    content.setdefault("config", {
        "adjust_max_index": 1,
        "attachment_info": [],
        "combination_max_index": 1,
        "export_range": None,
        "extract_audio_last_index": 1,
        "lyrics_recognition_id": "",
        "lyrics_sync": True,
        "lyrics_taskinfo": [],
        "maintrack_adsorb": True,
        "material_save_mode": 0,
        "multi_language_current": "none",
        "multi_language_list": [],
        "multi_language_main": "none",
        "multi_language_mode": "none",
        "original_sound_last_index": 1,
        "record_audio_last_index": 1,
        "sticker_max_index": 1,
        "subtitle_keywords_config": None,
        "subtitle_recognition_id": "",
        "subtitle_sync": True,
        "subtitle_taskinfo": [],
        "system_font_list": [],
        "use_float_render": False,
        "video_mute": False,
        "zoom_info_params": None
    })
    
    # Enhanced function assistant info
    content.setdefault("function_assistant_info", {
        "audio_noise_segid_list": [],
        "auto_adjust": False,
        "auto_adjust_fixed": False,
        "auto_adjust_fixed_value": 50.0,
        "auto_adjust_segid_list": [],
        "auto_caption": False,
        "auto_caption_segid_list": [],
        "auto_caption_template_id": "",
        "caption_opt": False,
        "caption_opt_segid_list": [],
        "color_correction": False,
        "color_correction_fixed": False,
        "color_correction_fixed_value": 50.0,
        "color_correction_segid_list": [],
        "deflicker_segid_list": [],
        "enhance_quality": False,
        "enhance_quality_fixed": False,
        "enhance_quality_segid_list": [],
        "enhance_voice_segid_list": [],
        "enhande_voice": False,
        "enhande_voice_fixed": False,
        "eye_correction": False,
        "eye_correction_segid_list": [],
        "fixed_rec_applied": False,
        "fps": {"den": 1, "num": 0},
        "normalize_loudness": False,
        "normalize_loudness_audio_denoise_segid_list": [],
        "normalize_loudness_fixed": False,
        "normalize_loudness_segid_list": [],
        "retouch": False,
        "retouch_fixed": False,
        "retouch_segid_list": [],
        "smart_rec_applied": False,
        "smart_segid_list": [],
        "smooth_slow_motion": False,
        "smooth_slow_motion_fixed": False,
        "video_noise_segid_list": []
    })
    
    content.setdefault("smart_ads_info", {
        "draft_url": "",
        "page_from": "",
        "routine": ""
    })
    
    content.setdefault("uneven_animation_template_info", {
        "composition": "",
        "content": "",
        "order": "",
        "sub_template_info_list": []
    })

# ---------- MAIN API - Enhanced Synchronization -----------------------------

def sync_timeline_from_meta(content_path: Path,
                            meta_path: Path,
                            duration_us: int = 5_000_000,
                            add_transitions: bool = True,
                            transition_name: str = "Pull in",
                            transition_duration_us: int = 466_666,
                            transition_is_overlap: bool = False) -> None:
    """
    ENHANCED FUNCTION: Build timeline with perfect ID synchronization and all required fields.
    """
    content = load_content(content_path)
    
    # Ensure all top-level fields are present
    _ensure_top_level_fields(content)
    
    # Extract material info from meta file
    materials = extract_material_ids_from_meta(meta_path)
    if not materials:
        print("No photo materials found in meta file")
        return
    
    print(f"Processing {len(materials)} materials with synchronized IDs")
    
    mats = _ensure_materials(content)
    tracks = _ensure_tracks(content)
    segments = tracks[0]["segments"]
    
    # Clear existing content to rebuild properly
    segments.clear()
    mats["videos"].clear()
    # Don't clear other materials - we'll append to them
    
    start_us = 0
    
    for idx, (material_id, img_path, width, height) in enumerate(materials):
        print(f"  Processing material {idx+1}: {material_id} -> {img_path.name}")
        
        # Build video material using EXISTING ID from meta
        vid = _build_video_material_with_existing_id(material_id, img_path, width, height)
        mats["videos"].append(vid)
        
        # Build auxiliary materials with enhanced structure
        canvas = _build_enhanced_canvas()
        mats["canvases"].append(canvas)
        
        ph = _build_enhanced_placeholder_info()
        mats["placeholder_infos"].append(ph)
        
        sm = _build_enhanced_sound_channel_mapping()
        mats["sound_channel_mappings"].append(sm)
        
        sp = _build_enhanced_speed()
        mats["speeds"].append(sp)
        
        mc = _build_enhanced_material_color()
        mats["material_colors"].append(mc)
        
        vs = _build_enhanced_vocal_separation()
        mats["vocal_separations"].append(vs)
        
        # Build extra_material_refs as LIST (order matches manual projects)
        extra_refs = [sp["id"], ph["id"], canvas["id"], sm["id"], mc["id"], vs["id"]]
        
        # Add transition if not first segment
        if add_transitions and idx > 0:
            trans = _build_enhanced_transition(transition_name, transition_duration_us, transition_is_overlap)
            mats["transitions"].append(trans)
            # Insert transition ID in previous segment's refs (at position 2)
            if segments:
                prev_refs = segments[-1]["extra_material_refs"]
                if len(prev_refs) >= 2:
                    prev_refs.insert(2, trans["id"])
        
        # Build and append segment with enhanced structure
        seg = _build_enhanced_segment(material_id, start_us=start_us, duration_us=duration_us, extra_refs=extra_refs)
        segments.append(seg)
        start_us += duration_us
    
    # Update timeline duration and modification time
    content["duration"] = start_us
    content["modified_time_us"] = _now_ms_like()
    
    print(f"Timeline built: {len(segments)} segments, total duration: {start_us} microseconds")
    save_content(content, content_path)

# ---------- Legacy Functions ------------------------------------------------

def add_image_to_timeline(content: Dict[str, Any], *args, **kwargs):
    print("WARNING: add_image_to_timeline is deprecated. Use sync_timeline_from_meta for proper ID synchronization.")

def add_folder_to_timeline(content: Dict[str, Any], *args, **kwargs):
    print("WARNING: add_folder_to_timeline is deprecated. Use sync_timeline_from_meta for proper ID synchronization.")

# ---------- I/O -------------------------------------------------------------

def load_content(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_content(content: Dict[str, Any], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(content, f, indent=2, ensure_ascii=False)

# ---------- CLI -------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Enhanced CapCut timeline sync with complete field structure")
    ap.add_argument("--content", required=True, help="Path to draft_content.json")
    ap.add_argument("--meta", required=True, help="Path to draft_meta_info.json")
    ap.add_argument("--duration-us", type=int, default=5_000_000, help="Per-image duration (default 5,000,000)")
    ap.add_argument("--no-transitions", action="store_true", help="Do not add transitions")
    ap.add_argument("--transition-name", default="Pull in", help="Transition name")
    ap.add_argument("--transition-duration-us", type=int, default=466_666, help="Transition duration")
    ap.add_argument("--transition-overlap", action="store_true", help="Mark transition as overlap")
    return ap.parse_args()

def main() -> int:
    args = _parse_args()
    content_path = Path(args.content).resolve()
    meta_path = Path(args.meta).resolve()
    
    if not content_path.exists():
        print(f"[ERROR] Content file not found: {content_path}")
        return 2
    
    if not meta_path.exists():
        print(f"[ERROR] Meta file not found: {meta_path}")
        return 2
    
    try:
        sync_timeline_from_meta(
            content_path,
            meta_path,
            duration_us=args.duration_us,
            add_transitions=(not args.no_transitions),
            transition_name=args.transition_name,
            transition_duration_us=args.transition_duration_us,
            transition_is_overlap=args.transition_overlap
        )
        print(f"[OK] Enhanced timeline sync completed -> {content_path}")
        return 0
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    raise SystemExit(main())