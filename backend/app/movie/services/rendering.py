from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..config import Settings


class AssemblyService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def export_project(
        self,
        *,
        project: dict,
        assembly_sequences: list[dict],
        output_path: Path,
        job_id: str,
    ) -> dict:
        if not assembly_sequences:
            raise RuntimeError("No uploaded sequence videos are available for assembly export.")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        project_root = output_path.parent.parent
        tmp_dir = project_root / "tmp" / f"assembly-{job_id}"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        normalized_paths = []
        for sequence in assembly_sequences:
            asset = sequence.get("approved_video_asset") or sequence.get("uploaded_video_asset")
            if asset is None:
                continue
            source_path = project_root / asset["relative_path"]
            if not source_path.exists():
                raise RuntimeError(f"Uploaded video is missing for sequence {sequence['absolute_order']}.")
            normalized_path = tmp_dir / f"sequence-{sequence['absolute_order']:03d}.mp4"
            self._normalize_clip(
                source_path=source_path,
                output_path=normalized_path,
                width=project["output_width"],
                height=project["output_height"],
                fps=project["output_fps"],
                trim_in_ms=int(sequence.get("trim_in_ms", 0) or 0),
                trim_out_ms=int(sequence.get("trim_out_ms", 0) or 0),
            )
            normalized_paths.append(normalized_path)

        if not normalized_paths:
            raise RuntimeError("No uploaded sequence videos are available for assembly export.")

        concat_file = tmp_dir / "concat.txt"
        concat_file.write_text(
            "\n".join(f"file '{path.as_posix()}'" for path in normalized_paths),
            encoding="utf-8",
        )

        command = [
            self.settings.ffmpeg_binary,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        self._run_ffmpeg(command, "FFmpeg assembly export failed.")
        return {
            "relative_path": output_path.name,
            "duration_s": self._probe_duration(output_path),
        }

    def _normalize_clip(
        self,
        *,
        source_path: Path,
        output_path: Path,
        width: int,
        height: int,
        fps: int,
        trim_in_ms: int,
        trim_out_ms: int,
    ) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        trim_in_s = max(0.0, trim_in_ms / 1000)
        trim_out_s = max(0.0, trim_out_ms / 1000)
        filter_chain = (
            f"fps={fps},"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
            "format=yuv420p"
        )
        command = [self.settings.ffmpeg_binary, "-y"]
        if trim_in_s > 0:
            command.extend(["-ss", f"{trim_in_s:.3f}"])
        command.extend(["-i", str(source_path)])
        if trim_out_s > trim_in_s:
            command.extend(["-to", f"{trim_out_s:.3f}"])
        command.extend(
            [
                "-vf",
                filter_chain,
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(output_path),
            ]
        )
        self._run_ffmpeg(command, f"Failed to normalize sequence {source_path.name}.")

    def _run_ffmpeg(self, command: list[str], error_message: str) -> None:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or error_message)

    def _probe_duration(self, output_path: Path) -> float:
        ffprobe = shutil.which("ffprobe")
        if ffprobe is None:
            return 0.0
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            return round(float(result.stdout.strip()), 2)
        except Exception:
            return 0.0
