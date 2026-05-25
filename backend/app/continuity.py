import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

class ContinuityGuard:
    def __init__(self, projects_root: Path):
        self.projects_root = projects_root

    def detect_and_inject_characters(
        self,
        prompt: str,
        characters: List[Dict[str, Any]],
        project_id: str
    ) -> Dict[str, Any]:
        """
        Scans a prompt for character names, automatically injecting description tags,
        style triggers, and compiling reference portraits to achieve visual consistency.
        """
        modified_prompt = prompt
        reference_images: List[str] = []
        applied_characters: List[str] = []

        for char in characters:
            name = char.get("name", "")
            if not name:
                continue
            
            # Case-insensitive word boundary match
            pattern = re.compile(r'\b' + re.escape(name) + r'\b', re.IGNORECASE)
            if pattern.search(prompt):
                applied_characters.append(name)
                
                # Retrieve custom prompt tags (e.g. 'wearing glasses, blonde hair')
                tags = char.get("prompt_tags", "").strip()
                trigger_word = char.get("role_summary", "").strip()
                
                injection_parts = []
                if trigger_word:
                    injection_parts.append(trigger_word)
                if tags:
                    injection_parts.append(tags)
                
                # Append description next to character name
                if injection_parts:
                    joined_tags = ", ".join(injection_parts)
                    modified_prompt = pattern.sub(f"{name} ({joined_tags})", modified_prompt)
                
                # Collect character reference portrait path if present
                portrait = char.get("portrait_image_url")
                if portrait:
                    # Map static asset url back to physical path
                    # e.g., /assets/{project_id}/character-images/...
                    rel_path = portrait.replace(f"/assets/{project_id}/", "")
                    physical_path = self.projects_root / project_id / rel_path
                    if physical_path.exists() and physical_path.is_file():
                        reference_images.append(str(physical_path))

        return {
            "original_prompt": prompt,
            "modified_prompt": modified_prompt,
            "applied_characters": applied_characters,
            "reference_images": reference_images,
            "has_continuity": len(reference_images) > 0
        }
