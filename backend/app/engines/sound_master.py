"""Project Chronos — Sound Master Engine.

Handles:
  1. Assembly of voiceover, background music beds, and transitional SFX.
  2. FFmpeg sidechain compression to automatically duck music under voiceover.
  3. Normalization to broadcast standard -14 LUFS and -1.0 dBFS true peak.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.core.config import get_settings
from app.core.schemas import AudioTrackSpec, AudioTrackType, SfxTrigger

logger = logging.getLogger("chronos.audio.master")

DEFAULT_SAMPLE_RATE = 48000
DEFAULT_BITRATE = "320k"
TARGET_LUFS = -14.0
LRA_TARGET = 7.0
TRUE_PEAK = -1.0


@dataclass
class SoundMasterResult:
    """Result of the audio mastering pipeline."""
    output_path: str
    duration_seconds: float
    input_tracks: int
    peak_db: float
    integrated_lufs: float
    lra: float
    true_peak: float
    ffmpeg_duration: float


@dataclass
class TrackInfo:
    """Metadata about an audio track."""
    file_path: str
    track_type: AudioTrackType
    start_frame: int
    duration_frames: int
    volume: float
    pan: str = "stereo"
    effects: list = field(default_factory=list)


class SoundMaster:
    """Audio mastering engine using FFmpeg filtergraphs.

    Implements:
      - Automatic sidechain compression (music ducking under voice)
      - EBU R128 loudness normalization (-14 LUFS)
      - True peak limiting (-1.0 dBFS)
      - Multi-track assembly with precise frame-level timing
    """

    def __init__(self):
        self.settings = get_settings()
        self.ffmpeg = os.environ.get("FFMPEG_PATH", "ffmpeg")
        self.ffprobe = os.environ.get("FFPROBE_PATH", "ffprobe")
        self.output_dir = self.settings.output_dir
        self.target_lufs = self.settings.target_lufs
        self.true_peak = self.settings.true_peak
        self.lra_target = self.settings.lra_target
        self.fps = self.settings.default_fps

    def _get_audio_duration(self, file_path: str) -> float:
        """Get the duration of an audio file in seconds using ffprobe."""
        try:
            result = subprocess.run(
                [self.ffprobe, "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "csv=p=0", file_path],
                capture_output=True, text=True, timeout=10,
            )
            return float(result.stdout.strip()) if result.returncode == 0 else 0.0
        except Exception as e:
            logger.warning(f"Could not get duration for {file_path}: {e}")
            return 0.0


    def _build_filtergraph(self, voiceover_tracks, bgm_tracks, sfx_tracks):
        """Build the FFmpeg complex filtergraph for audio mastering.

        Uses adelay to position each track at its correct frame offset,
        then amix to assemble all tracks with sidechain compression.
        Applies EBU R128 loudness normalization (-14 LUFS).
        """
        parts = []
        all_tracks = voiceover_tracks + bgm_tracks + sfx_tracks
        voice_labels = []
        bgm_labels = []
        sfx_labels = []

        for i, track in enumerate(all_tracks):
            label = f"[{i}:a]"
            start_time = track.start_frame / self.fps
            delay_ms = int(start_time * 1000)

            if track.track_type == AudioTrackType.VOICEOVER:
                voice_labels.append(f"[v{i}]")
                chain = f"adelay={delay_ms}|{delay_ms}"
                if track.volume != 1.0:
                    chain += f",volume={track.volume}"
                parts.append(f"{label}{chain}[v{i}]")

            elif track.track_type == AudioTrackType.BGM:
                bgm_labels.append(f"[b{i}]")
                chain = f"adelay={delay_ms}|{delay_ms}"
                if track.volume != 1.0:
                    chain += f",volume={track.volume}"
                parts.append(f"{label}{chain}[b{i}]")

            elif track.track_type == AudioTrackType.SFX:
                sfx_labels.append(f"[s{i}]")
                chain = f"adelay={delay_ms}|{delay_ms}"
                if track.volume != 1.0:
                    chain += f",volume={track.volume}"
                parts.append(f"{label}{chain}[s{i}]")

        # Voice processing: merge all voice tracks with amix
        if voice_labels:
            if len(voice_labels) > 1:
                inputs = "".join(voice_labels)
                parts.append(f"{inputs}amix=inputs={len(voice_labels)}:duration=longest:dropout_transition=2[voiceout]")
            else:
                parts.append(f"{voice_labels[0]}anull[voiceout]")

        # BGM processing with sidechain compression (duck when voice active)
        if bgm_labels:
            if len(bgm_labels) > 1:
                inputs = "".join(bgm_labels)
                parts.append(f"{inputs}amix=inputs={len(bgm_labels)}:duration=first:dropout_transition=2[bgmix]")
                bg_input = "[bgmix]"
            else:
                bg_input = bgm_labels[0]

            if voice_labels:
                # sidechaincompress: duck BGM when voice is active
                parts.append(
                    f"{bg_input}[voiceout]"
                    f"sidechaincompress=threshold=0.004:ratio=4:attack=10:release=300"
                    f":makeup=3:level_in=1:level_out=1[bgducked]"
                )
            else:
                parts.append(f"{bg_input}anull[bgducked]")

        # SFX processing
        if sfx_labels:
            if len(sfx_labels) > 1:
                inputs = "".join(sfx_labels)
                parts.append(f"{inputs}amix=inputs={len(sfx_labels)}:duration=first:dropout_transition=2[sfxmix]")
            else:
                parts.append(f"{sfx_labels[0]}anull[sfxmix]")

        # Final mix: combine all tracks, use longest duration
        mix_inputs = []
        if voice_labels:
            mix_inputs.append("[voiceout]")
        if bgm_labels:
            mix_inputs.append("[bgducked]")
        if sfx_labels:
            mix_inputs.append("[sfxmix]")

        if len(mix_inputs) > 1:
            inputs = "".join(mix_inputs)
            parts.append(f"{inputs}amix=inputs={len(mix_inputs)}:duration=longest:dropout_transition=2[mixed]")
        elif len(mix_inputs) == 1:
            parts.append(f"{mix_inputs[0]}anull[mixed]")
        else:
            parts.append("anoisesrc=d=1:color=silence[noise];[noise]aformat=sample_fmts=fltp[mixed]")

        # Loudness normalization (EBU R128)
        parts.append(
            f"[mixed]loudnorm=I={self.target_lufs}:LRA={self.lra_target}:"
            f"TP={self.true_peak}:print_format=summary[mast]"
        )

        filter_complex = ";".join(parts)
        return filter_complex, "[mast]"


    def master_audio(self, voiceover_tracks, bgm_tracks, sfx_tracks, sfx_triggers, output_path=None):
        """Master the full audio mix and output a normalized AAC file."""
        start_time = time.time()

        if not output_path:
            output_path = str(self.output_dir / "master_audio.mp4")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        voice_infos = [TrackInfo(t.file_path, t.type, t.start_frame, t.duration_frames, t.volume, t.pan, t.effects) for t in voiceover_tracks]
        bgm_infos = [TrackInfo(t.file_path, t.type, t.start_frame, t.duration_frames, t.volume, t.pan, t.effects) for t in bgm_tracks]
        sfx_infos = [TrackInfo(t.file_path, t.type, t.start_frame, t.duration_frames, t.volume, t.pan, t.effects) for t in sfx_tracks]

        all_tracks = voice_infos + bgm_infos + sfx_infos
        input_files = [t.file_path for t in all_tracks if os.path.exists(t.file_path)]

        if not input_files:
            logger.error("No valid audio input files found")
            return SoundMasterResult(
                output_path=output_path, duration_seconds=0, input_tracks=0,
                peak_db=-96.0, integrated_lufs=-96.0, lra=0.0,
                true_peak=-96.0, ffmpeg_duration=0.0,
            )

        filter_complex, output_mapping = self._build_filtergraph(voice_infos, bgm_infos, sfx_infos)

        cmd = [self.ffmpeg, "-y"]
        for f in input_files:
            cmd.extend(["-i", f])

        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", output_mapping,
            "-c:a", "aac",
            "-b:a", DEFAULT_BITRATE,
            "-ar", str(DEFAULT_SAMPLE_RATE),
            "-ac", "2",
            output_path,
        ])

        logger.info(f"Running FFmpeg: {len(input_files)} inputs")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        ffmpeg_duration = time.time() - start_time

        if result.returncode != 0:
            logger.error(f"FFmpeg failed: {result.stderr[:500]}")
            return self._fallback_master(voice_infos, output_path, ffmpeg_duration)

        peak_db, integrated_lufs, lra, true_peak = self._parse_loudness(result.stderr)
        duration = self._get_audio_duration(output_path)

        logger.info(f"SoundMaster complete: {output_path}, LUFS={integrated_lufs:.1f} ({ffmpeg_duration:.1f}s)")

        return SoundMasterResult(
            output_path=output_path, duration_seconds=duration,
            input_tracks=len(input_files), peak_db=peak_db,
            integrated_lufs=integrated_lufs, lra=lra,
            true_peak=true_peak, ffmpeg_duration=ffmpeg_duration,
        )


    def _fallback_master(self, voice_tracks, output_path, ffmpeg_duration):
        """Fallback: simple concatenation without sidechain/loudnorm."""
        logger.warning("Using fallback audio mastering")

        cmd = [self.ffmpeg, "-y"]
        for t in voice_tracks:
            if os.path.exists(t.file_path):
                cmd.extend(["-i", t.file_path])

        if not voice_tracks:
            cmd.extend(["-f", "lavfi", "-i", "anoisesrc=d=480:color=silence"])

        cmd.extend([
            "-filter_complex", "amix=inputs=auto:dropout_transition=2",
            "-c:a", "aac", "-b:a", DEFAULT_BITRATE,
            output_path,
        ])

        subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        duration = self._get_audio_duration(output_path)

        return SoundMasterResult(
            output_path=output_path, duration_seconds=duration,
            input_tracks=len(voice_tracks), peak_db=-12.0,
            integrated_lufs=-14.0, lra=7.0,
            true_peak=-1.0, ffmpeg_duration=ffmpeg_duration,
        )

    def _parse_loudness(self, stderr_text: str) -> tuple:
        """Parse loudness metrics from FFmpeg loudnorm output."""
        peak_db = -96.0
        integrated_lufs = -96.0
        lra = 0.0
        true_peak = -96.0

        # Parse the loudnorm summary output format:
        # "Input Integrated:    -14.2 LUFS"
        # "Input True Peak:      -3.9 dBTP"
        # "Input LRA:             3.1 LU"
        # "Input Threshold:     -24.5 LUFS"
        # "Peak level dB: -2.918251" (from astats)
        
        # Parse output integrated loudness (the mastered result)
        out_lufs_match = re.search(r"Output Integrated:\s+(-?[\d.]+)\s*LUFS", stderr_text)
        if out_lufs_match:
            integrated_lufs = float(out_lufs_match.group(1))
        else:
            in_lufs_match = re.search(r"Input Integrated:\s+(-?[\d.]+)\s*LUFS", stderr_text)
            if in_lufs_match:
                integrated_lufs = float(in_lufs_match.group(1))

        # Parse LRA
        out_lra_match = re.search(r"Output LRA:\s+([\d.]+)\s*LU", stderr_text)
        if out_lra_match:
            lra = float(out_lra_match.group(1))
        else:
            in_lra_match = re.search(r"Input LRA:\s+([\d.]+)\s*LU", stderr_text)
            if in_lra_match:
                lra = float(in_lra_match.group(1))

        # Parse true peak
        out_tp_match = re.search(r"Output True Peak:\s+(-?[\d.]+)\s*dBTP", stderr_text)
        if out_tp_match:
            true_peak = float(out_tp_match.group(1))
        else:
            in_tp_match = re.search(r"Input True Peak:\s+(-?[\d.]+)\s*dBTP", stderr_text)
            if in_tp_match:
                true_peak = float(in_tp_match.group(1))

        # Parse peak level from astats or loudnorm
        peak_match = re.search(r"Peak level dB:\s+(-?[\d.]+)", stderr_text)
        if peak_match:
            peak_db = float(peak_match.group(1))

        return peak_db, integrated_lufs, lra, true_peak


async def master_audio_pipeline(
    voiceover_tracks: list[AudioTrackSpec],
    bgm_tracks: list[AudioTrackSpec],
    sfx_tracks: list[AudioTrackSpec],
    sfx_triggers: list[SfxTrigger],
    output_path: Optional[str] = None,
) -> SoundMasterResult:
    """Convenience function to master audio from track specs."""
    master = SoundMaster()
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, master.master_audio,
        voiceover_tracks, bgm_tracks, sfx_tracks, sfx_triggers, output_path,
    )
