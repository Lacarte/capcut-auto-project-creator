#!/usr/bin/env python3
"""
Template Cleaner for CapCut Auto Project Creator

This script removes all asset-specific references from template JSON files,
creating clean baseline templates that can be populated with any new assets.
"""

import json
import shutil
from pathlib import Path
from typing import Dict, Any
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)


def create_clean_draft_content() -> Dict[str, Any]:
    """Create a clean draft_content.json template with no asset references."""
    return {
        "canvas_config": {
            "background": None,
            "height": 1920,
            "ratio": "original",
            "width": 1280
        },
        "color_space": 0,
        "config": {
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
            "video_mute": True,
            "zoom_info_params": None
        },
        "cover": None,
        "create_time": 0,
        "draft_type": "video",
        "duration": 0,  # Will be set by pipeline
        "extra_info": None,
        "fps": 30.0,
        "free_render_index_mode_on": False,
        "function_assistant_info": {
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
        },
        "group_container": None,
        "id": "00000000-0000-0000-0000-000000000000",  # Will be regenerated
        "is_drop_frame_timecode": False,
        "keyframe_graph_list": [],
        "keyframes": {
            "adjusts": [],
            "audios": [],
            "effects": [],
            "filters": [],
            "handwrites": [],
            "stickers": [],
            "texts": [],
            "videos": []
        },
        "last_modified_platform": {
            "app_id": 359289,
            "app_source": "cc",
            "app_version": "7.2.0",
            "device_id": "auto-generated-device-id",
            "hard_disk_id": "",
            "mac_address": "auto-generated-mac",
            "os": "windows",
            "os_version": "10.0.26100"
        },
        "lyrics_effects": [],
        "materials": {
            # These arrays will be populated by the pipeline
            "videos": [],
            "audios": [],
            "transitions": [],
            "speeds": [],
            "placeholder_infos": [],
            "sound_channel_mappings": [],
            "ai_translates": [],
            "audio_balances": [],
            "audio_effects": [],
            "audio_fades": [],
            "audio_pannings": [],
            "audio_pitch_shifts": [],
            "audio_track_indexes": [],
            "beats": [],
            "canvases": [],
            "chromas": [],
            "color_curves": [],
            "common_mask": [],
            "digital_human_model_dressing": [],
            "digital_humans": [],
            "drafts": [],
            "effects": [],
            "flowers": [],
            "green_screens": [],
            "handwrites": [],
            "hsl": [],
            "hsl_curves": [],
            "images": [],
            "log_color_wheels": [],
            "loudnesses": [],
            "manual_beautys": [],
            "manual_deformations": [],
            "material_animations": [],
            "material_colors": [],
            "multi_language_refs": [],
            "plugin_effects": [],
            "primary_color_wheels": [],
            "realtime_denoises": [],
            "shapes": [],
            "smart_crops": [],
            "smart_relights": [],
            "stickers": [],
            "tail_leaders": [],
            "text_templates": [],
            "texts": [],
            "time_marks": [],
            "video_effects": [],
            "video_trackings": [],
            "vocal_beautifys": [],
            "vocal_separations": []
        },
        "mutable_config": None,
        "name": "",  # Will be set by pipeline
        "new_version": "145.0.0",
        "path": "",  # Will be set by pipeline
        "platform": {
            "app_id": 359289,
            "app_source": "cc",
            "app_version": "7.2.0",
            "device_id": "auto-generated-device-id",
            "hard_disk_id": "",
            "mac_address": "auto-generated-mac",
            "os": "windows",
            "os_version": "10.0.26100"
        },
        "relationships": [],
        "render_index_track_mode_on": True,
        "retouch_cover": None,
        "smart_ads_info": {
            "draft_url": "",
            "page_from": "",
            "routine": ""
        },
        "source": "default",
        "static_cover_image_path": "",
        "time_marks": None,
        "tracks": [],  # Will be populated by pipeline
        "uneven_animation_template_info": {
            "composition": "",
            "content": "",
            "order": "",
            "sub_template_info_list": []
        },
        "update_time": 0,
        "version": 360000
    }


def create_clean_draft_meta_info() -> Dict[str, Any]:
    """Create a clean draft_meta_info.json template with no asset references."""
    return {
        "cloud_draft_cover": True,
        "cloud_draft_sync": True,
        "cloud_package_completed_time": "",
        "draft_cloud_capcut_purchase_info": "",
        "draft_cloud_last_action_download": False,
        "draft_cloud_package_type": "",
        "draft_cloud_purchase_info": "",
        "draft_cloud_template_id": "",
        "draft_cloud_tutorial_info": "",
        "draft_cloud_videocut_purchase_info": "",
        "draft_cover": "draft_cover.jpg",
        "draft_deeplink_url": "",
        "draft_enterprise_info": {
            "draft_enterprise_extra": "",
            "draft_enterprise_id": "",
            "draft_enterprise_name": "",
            "enterprise_material": []
        },
        "draft_fold_path": "./template-project",  # Will be updated by pipeline
        "draft_id": "00000000-0000-0000-0000-000000000000",  # Will be regenerated
        "draft_is_ae_produce": False,
        "draft_is_ai_packaging_used": False,
        "draft_is_ai_shorts": False,
        "draft_is_ai_translate": False,
        "draft_is_article_video_draft": False,
        "draft_is_cloud_temp_draft": False,
        "draft_is_from_deeplink": "false",
        "draft_is_invisible": False,
        "draft_is_web_article_video": False,
        "draft_materials": [
            # Required buckets - will be populated by pipeline
            {"type": 0, "value": []},  # Imported media
            {"type": 1, "value": []},
            {"type": 2, "value": []},
            {"type": 3, "value": []},
            {"type": 6, "value": []},
            {"type": 7, "value": []},
            {"type": 8, "value": []}
        ],
        "draft_materials_copied_info": [],
        "draft_name": "template-project",  # Will be updated by pipeline
        "draft_need_rename_folder": False,
        "draft_new_version": "",
        "draft_removable_storage_device": "",
        "draft_root_path": "",  # Will be set by pipeline
        "draft_segment_extra_info": [],
        "draft_timeline_materials_size_": 0,  # Will be calculated by pipeline
        "draft_type": "",
        "draft_web_article_video_enter_from": "",
        "tm_draft_cloud_completed": "",
        "tm_draft_cloud_entry_id": -1,
        "tm_draft_cloud_modified": 0,
        "tm_draft_cloud_parent_entry_id": -1,
        "tm_draft_cloud_space_id": -1,
        "tm_draft_cloud_user_id": -1,
        "tm_draft_create": 0,  # Will be set by pipeline
        "tm_draft_modified": 0,  # Will be set by pipeline
        "tm_draft_removed": 0,
        "tm_duration": 0  # Will be set by pipeline
    }


def create_clean_draft_virtual_store() -> Dict[str, Any]:
    """Create a clean draft_virtual_store.json template with no asset references."""
    return {
        "draft_materials": [],
        "draft_virtual_store": [
            {
                "type": 0,
                "value": [
                    {
                        "creation_time": 0,
                        "display_name": "",
                        "filter_type": 0,
                        "id": "",
                        "import_time": 0,
                        "import_time_us": 0,
                        "sort_sub_type": 0,
                        "sort_type": 0
                    }
                ]
            },
            {
                "type": 1,
                "value": []  # Child references - will be populated by pipeline
            },
            {
                "type": 2,
                "value": []
            }
        ]
    }


def create_clean_key_value() -> Dict[str, Any]:
    """Create an empty key_value.json template."""
    return {}


def backup_template_dir(template_dir: Path) -> None:
    """Create a backup of the current template directory."""
    backup_dir = template_dir.parent / f"{template_dir.name}_backup"
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    shutil.copytree(template_dir, backup_dir)
    log.info(f"Backed up template directory to: {backup_dir}")


def clean_templates(template_dir: Path) -> None:
    """Clean all template JSON files, removing asset-specific references."""
    template_dir = Path(template_dir)
    
    if not template_dir.exists():
        log.error(f"Template directory not found: {template_dir}")
        return
    
    # Create backup
    backup_template_dir(template_dir)
    
    # Clean each template file
    templates = {
        "draft_content.json": create_clean_draft_content(),
        "draft_meta_info.json": create_clean_draft_meta_info(),
        "draft_virtual_store.json": create_clean_draft_virtual_store(),
        "key_value.json": create_clean_key_value()
    }
    
    for filename, clean_data in templates.items():
        file_path = template_dir / filename
        
        # Write clean template
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(clean_data, f, indent=2, ensure_ascii=False)
        
        log.info(f"Cleaned template: {filename}")
    
    log.info("✓ All template files cleaned successfully")
    log.info("✓ Old templates backed up")
    log.info("✓ Ready for fresh asset generation")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Clean CapCut template JSON files")
    parser.add_argument(
        "--template-dir", 
        default="./template-config",
        help="Path to template directory (default: ./template-config)"
    )
    
    args = parser.parse_args()
    
    log.info("Starting CapCut template cleaning process...")
    clean_templates(Path(args.template_dir))


if __name__ == "__main__":
    main()