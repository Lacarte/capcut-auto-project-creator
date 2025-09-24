#!/usr/bin/env python3
"""
capcut_transitions_utils.py
---------------------------
Modular utility for managing CapCut transitions between timeline segments.

Features:
- Add/remove transitions between existing segments
- Support for different transition types
- Proper integration with CapCut's material system
- Transition timing and overlap configuration

Usage:
    python capcut_transitions_utils.py --content draft_content.json --add-transitions
    python capcut_transitions_utils.py --content draft_content.json --transition-type "Fade" --duration 1000000
"""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional

# ---------- Transition Templates --------------------------------------------

TRANSITION_TEMPLATES = {
    "Pull in": {
        "name": "Pull in",
        "category_name": "remen",
        "duration": 466666,
        "is_overlap": False
    },
    "Fade": {
        "name": "Fade",
        "category_name": "basic",
        "duration": 500000,
        "is_overlap": True
    },
    "Fast Swipe": {
        "name": "Fast Swipe", 
        "category_id": "25822",
        "category_name": "remen",
        "duration": 2000000,
        "effect_id": "7544051798751874365",
        "is_ai_transition": False,
        "is_overlap": True,
        "path": "C:/Users/Admin/AppData/Local/CapCut/User Data/Cache/effect/7544051798751874365/cab6bed97517d61260dd35c3fdf2a65b",
        "platform": "all",
        "request_id": "202509242236399D261FBDFFCEFDBB1E37",
        "resource_id": "7544051798751874365",
        "source_platform": 1,
        "task_id": "",
        "third_resource_id": "0",
        "video_path": ""
    },
    "Zoom": {
        "name": "Zoom",
        "category_name": "basic",
        "duration": 800000,
        "is_overlap": True
    },
    "Slide": {
        "name": "Slide", 
        "category_name": "basic",
        "duration": 600000,
        "is_overlap": False
    }
}

# ---------- Transition Building ---------------------------------------------

def _create_transition(transition_type: str = "Pull in", 
                      duration_us: Optional[int] = None,
                      is_overlap: Optional[bool] = None) -> Dict[str, Any]:
    """
    Create a transition material based on type template.
    """
    template = TRANSITION_TEMPLATES.get(transition_type, TRANSITION_TEMPLATES["Pull in"])
    
    # Override template values if provided
    if duration_us is not None:
        template = template.copy()
        template["duration"] = duration_us
    if is_overlap is not None:
        template = template.copy()
        template["is_overlap"] = is_overlap
    
    transition = {
        "id": str(uuid.uuid4()),
        "type": "transition",
        **template
    }
    
    return transition

def _find_transition_insert_position(extra_refs: List[str]) -> int:
    """
    Find the correct position to insert transition ID in extra_material_refs.
    Based on observed pattern: [speed, placeholder, transition, canvas, animation, sound, color, vocal]
    """
    # Insert transition as 3rd element (index 2) if we have enough refs
    if len(extra_refs) >= 2:
        return 2
    else:
        return len(extra_refs)

# ---------- Main Transition Functions --------------------------------------

def add_transitions_to_content(content_path: Path,
                              transition_type: str = "Pull in",
                              duration_us: int = 466666,
                              is_overlap: bool = False,
                              skip_first: bool = True) -> bool:
    """
    Add transitions between all segments in the timeline.
    
    Args:
        content_path: Path to draft_content.json
        transition_type: Type of transition to use
        duration_us: Duration of transition in microseconds
        is_overlap: Whether transition should overlap segments
        skip_first: Don't add transition before first segment
    
    Returns:
        True if successful, False otherwise
    """
    try:
        with content_path.open('r', encoding='utf-8') as f:
            content = json.load(f)
        
        # Get materials and tracks
        materials = content.setdefault("materials", {})
        transitions = materials.setdefault("transitions", [])
        tracks = content.get("tracks", [])
        
        if not tracks or not tracks[0].get("segments"):
            print("No segments found in timeline")
            return False
        
        segments = tracks[0]["segments"]
        if len(segments) < 2:
            print("Need at least 2 segments to add transitions")
            return False
        
        # Clear existing transitions
        transitions.clear()
        
        # Remove existing transition references from segments
        for segment in segments:
            extra_refs = segment.get("extra_material_refs", [])
            # Remove any existing transition IDs (they would be UUIDs in the list)
            segment["extra_material_refs"] = [ref for ref in extra_refs 
                                            if not _looks_like_transition_id(ref, materials)]
        
        # Add new transitions
        added_transitions = 0
        start_index = 1 if skip_first else 0
        
        for i in range(start_index, len(segments)):
            # Create transition
            transition = _create_transition(transition_type, duration_us, is_overlap)
            transitions.append(transition)
            
            # Get previous segment (the one that will have the transition)
            prev_segment = segments[i-1] if i > 0 else segments[i]
            extra_refs = prev_segment.get("extra_material_refs", [])
            
            # Insert transition ID at correct position
            insert_pos = _find_transition_insert_position(extra_refs)
            extra_refs.insert(insert_pos, transition["id"])
            
            added_transitions += 1
        
        # Save updated content
        with content_path.open('w', encoding='utf-8') as f:
            json.dump(content, f, indent=2, ensure_ascii=False)
        
        print(f"Added {added_transitions} transitions of type '{transition_type}'")
        return True
        
    except Exception as e:
        print(f"Error adding transitions: {e}")
        return False

def remove_all_transitions(content_path: Path) -> bool:
    """
    Remove all transitions from the timeline.
    """
    try:
        with content_path.open('r', encoding='utf-8') as f:
            content = json.load(f)
        
        # Clear transitions from materials
        materials = content.setdefault("materials", {})
        transitions = materials.setdefault("transitions", [])
        transition_ids = {t["id"] for t in transitions}
        transitions.clear()
        
        # Remove transition references from segments
        tracks = content.get("tracks", [])
        if tracks and tracks[0].get("segments"):
            for segment in tracks[0]["segments"]:
                extra_refs = segment.get("extra_material_refs", [])
                segment["extra_material_refs"] = [ref for ref in extra_refs 
                                                if ref not in transition_ids]
        
        with content_path.open('w', encoding='utf-8') as f:
            json.dump(content, f, indent=2, ensure_ascii=False)
        
        print("Removed all transitions from timeline")
        return True
        
    except Exception as e:
        print(f"Error removing transitions: {e}")
        return False

def list_available_transitions() -> None:
    """List all available transition types."""
    print("Available transition types:")
    for name, template in TRANSITION_TEMPLATES.items():
        duration_sec = template["duration"] / 1_000_000
        overlap = "Yes" if template.get("is_overlap", False) else "No"
        print(f"  • {name:<12} - {duration_sec:.2f}s - Overlap: {overlap}")

def analyze_current_transitions(content_path: Path) -> Dict[str, Any]:
    """
    Analyze current transitions in the project.
    """
    try:
        with content_path.open('r', encoding='utf-8') as f:
            content = json.load(f)
        
        materials = content.get("materials", {})
        transitions = materials.get("transitions", [])
        tracks = content.get("tracks", [])
        
        analysis = {
            "total_transitions": len(transitions),
            "transition_types": {},
            "segments_with_transitions": 0,
            "segments_total": 0
        }
        
        # Analyze transition types
        for transition in transitions:
            t_name = transition.get("name", "Unknown")
            if t_name not in analysis["transition_types"]:
                analysis["transition_types"][t_name] = 0
            analysis["transition_types"][t_name] += 1
        
        # Analyze segment usage
        if tracks and tracks[0].get("segments"):
            segments = tracks[0]["segments"]
            analysis["segments_total"] = len(segments)
            
            transition_ids = {t["id"] for t in transitions}
            for segment in segments:
                extra_refs = segment.get("extra_material_refs", [])
                if any(ref in transition_ids for ref in extra_refs):
                    analysis["segments_with_transitions"] += 1
        
        return analysis
        
    except Exception as e:
        print(f"Error analyzing transitions: {e}")
        return {}

def _looks_like_transition_id(ref_id: str, materials: Dict[str, Any]) -> bool:
    """
    Check if a reference ID belongs to a transition.
    """
    transitions = materials.get("transitions", [])
    transition_ids = {t["id"] for t in transitions}
    return ref_id in transition_ids

# ---------- I/O Functions --------------------------------------------------

def load_content(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_content(content: Dict[str, Any], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(content, f, indent=2, ensure_ascii=False)

# ---------- CLI Interface --------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CapCut Transitions Utility")
    parser.add_argument("--content", required=True, help="Path to draft_content.json")
    
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument("--add-transitions", action="store_true", 
                             help="Add transitions between segments")
    action_group.add_argument("--remove-transitions", action="store_true",
                             help="Remove all transitions")
    action_group.add_argument("--list-types", action="store_true",
                             help="List available transition types")
    action_group.add_argument("--analyze", action="store_true",
                             help="Analyze current transitions")
    
    parser.add_argument("--transition-type", default="Pull in",
                       help="Type of transition to add (default: Pull in)")
    parser.add_argument("--duration", type=int, default=466666,
                       help="Transition duration in microseconds (default: 466666)")
    parser.add_argument("--overlap", action="store_true",
                       help="Make transition overlapping")
    parser.add_argument("--include-first", action="store_true",
                       help="Add transition before first segment too")
    
    return parser.parse_args()

def main() -> int:
    args = _parse_args()
    
    if args.list_types:
        list_available_transitions()
        return 0
    
    content_path = Path(args.content)
    if not content_path.exists():
        print(f"Content file not found: {content_path}")
        return 1
    
    try:
        if args.add_transitions:
            success = add_transitions_to_content(
                content_path,
                transition_type=args.transition_type,
                duration_us=args.duration,
                is_overlap=args.overlap,
                skip_first=not args.include_first
            )
            return 0 if success else 1
            
        elif args.remove_transitions:
            success = remove_all_transitions(content_path)
            return 0 if success else 1
            
        elif args.analyze:
            analysis = analyze_current_transitions(content_path)
            if analysis:
                print("\nTransition Analysis:")
                print(f"Total transitions: {analysis['total_transitions']}")
                print(f"Segments with transitions: {analysis['segments_with_transitions']}/{analysis['segments_total']}")
                if analysis['transition_types']:
                    print("Transition types:")
                    for t_type, count in analysis['transition_types'].items():
                        print(f"  • {t_type}: {count}")
                else:
                    print("No transitions found")
            return 0
            
    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
