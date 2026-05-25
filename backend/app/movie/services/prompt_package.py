from __future__ import annotations


def determine_prompt_package_status(project: dict) -> str:
    scenes = project.get("scenes", [])
    if project.get("workflow_version", 2) < 2:
        return "needs_upgrade"
    if not scenes:
        return "needs_scenes"
    if any(not scene.get("first_image_prompt_text", "").strip() for scene in scenes):
        return "needs_scene_image_prompts"
    if any(not scene.get("sequences") for scene in scenes):
        return "needs_sequences"
    if any(
        not sequence.get("wan_prompt_text", "").strip()
        for scene in scenes
        for sequence in scene.get("sequences", [])
    ):
        return "needs_wan_prompts"
    return "ready"


def build_prompt_package(project: dict) -> dict:
    return {
        "project_id": project["id"],
        "name": project["name"],
        "genre": project["genre"],
        "tone": project["tone"],
        "target_duration_s": project["target_duration_s"],
        "style_anchor_text": project.get("style_anchor_text", ""),
        "prompt_package_status": determine_prompt_package_status(project),
        "scenes": [
            {
                "scene_id": scene["id"],
                "order": scene["order"],
                "title": scene["title"],
                "target_duration_s": scene["target_duration_s"],
                "narrative_text": scene["narrative_text"],
                "first_image_prompt_text": scene["first_image_prompt_text"],
                "first_image_asset": scene.get("first_image_asset"),
                "sequences": [
                    {
                        "sequence_id": sequence["id"],
                        "order": sequence["order"],
                        "absolute_order": sequence["absolute_order"],
                        "title": sequence["title"],
                        "target_duration_s": sequence["target_duration_s"],
                        "narrative_text": sequence["narrative_text"],
                        "camera_direction": sequence["camera_direction"],
                        "action_direction": sequence["action_direction"],
                        "wan_prompt_text": sequence["wan_prompt_text"],
                        "uploaded_video_asset": sequence.get("uploaded_video_asset"),
                    }
                    for sequence in scene.get("sequences", [])
                ],
            }
            for scene in project.get("scenes", [])
        ],
        "created_at": project["created_at"],
        "updated_at": project["updated_at"],
    }


def render_prompt_package_markdown(package: dict) -> str:
    lines = [
        f"# {package['name']}",
        "",
        "## Project",
        f"- Genre: {package['genre']}",
        f"- Tone: {package['tone']}",
        f"- Target duration: {package['target_duration_s']} seconds",
        f"- Prompt package status: {package['prompt_package_status']}",
        "",
        "## Style Anchor",
        package.get("style_anchor_text", "") or "_Not generated yet._",
        "",
        "## Scenes",
    ]

    for scene in package.get("scenes", []):
        lines.extend(
            [
                "",
                f"### Scene {scene['order']:02d} - {scene['title']}",
                f"- Duration: {scene['target_duration_s']} seconds",
                f"- Narrative beat: {scene['narrative_text']}",
                "",
                "First image prompt:",
                scene.get("first_image_prompt_text", "") or "_Not generated yet._",
            ]
        )
        if scene.get("first_image_asset") is not None:
            lines.extend(
                [
                    "",
                    f"First image asset: {scene['first_image_asset']['original_filename']}",
                ]
            )
        lines.extend(["", "Sequences:"])
        for sequence in scene.get("sequences", []):
            lines.extend(
                [
                    "",
                    f"- Seq {sequence['order']:02d} ({sequence['target_duration_s']}s): {sequence['title']}",
                    f"  Beat: {sequence['narrative_text']}",
                    f"  Camera: {sequence['camera_direction'] or '_Not set_'}",
                    f"  Action: {sequence['action_direction'] or '_Not set_'}",
                    "  Wan 2.2 prompt:",
                    f"  {sequence.get('wan_prompt_text', '') or '_Not generated yet._'}",
                ]
            )
            if sequence.get("uploaded_video_asset") is not None:
                lines.append(f"  Uploaded video: {sequence['uploaded_video_asset']['original_filename']}")

    lines.extend(
        [
            "",
            "## Postproduction Recommendations",
            "- DaVinci Resolve for editorial, conform, audio polish, and finishing once the rough cut is assembled.",
            "- Adobe Premiere Pro if your team already edits there and wants broad plugin support.",
            "- OpenTimelineIO as the future interchange layer to add when we want editor handoff beyond a flat rough-cut export.",
        ]
    )
    return "\n".join(lines).strip() + "\n"
