"""Reliable CLI-based EdgeTTS wrapper - bypasses aiohttp DNS issues."""
import subprocess
import json
import wave
from pathlib import Path
from typing import Optional


def _get_mp3_duration(path: str) -> float:
    """Get MP3 duration using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def _mp3_to_wav(mp3_path: str, wav_path: str, sample_rate: int = 24000) -> None:
    """Convert MP3 to WAV."""
    subprocess.run([
        "ffmpeg", "-y", "-i", mp3_path,
        "-acodec", "pcm_s16le", "-ar", str(sample_rate), "-ac", "1",
        wav_path,
    ], capture_output=True, timeout=30)


def synthesize_cli(
    text: str,
    output_path: str,
    voice_id: str = "en-US-GuyNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz",
    volume: str = "+0%",
) -> dict:
    """Synthesize text using edge-tts CLI.

    Returns dict with: output_path, duration_seconds, sample_rate, word_count
    """
    output_path = str(Path(output_path).resolve())
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Edge-tts CLI: --write-media writes mp3 directly
    mp3_temp = output_path
    if not mp3_temp.endswith(".mp3"):
        mp3_temp = output_path.rsplit(".", 1)[0] + ".mp3"

    cmd = [
        "edge-tts",
        "--voice", voice_id,
        "--text", text,
        "--rate", rate,
        "--pitch", pitch,
        "--volume", volume,
        "--write-media", mp3_temp,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"edge-tts CLI failed: {result.stderr.strip()}")

    # If we wanted WAV, convert
    if output_path.endswith(".wav"):
        _mp3_to_wav(mp3_temp, output_path)
        try:
            Path(mp3_temp).unlink()
        except OSError:
            pass

    duration = _get_mp3_duration(output_path if output_path.endswith(".mp3") else mp3_temp)
    word_count = len(text.split())

    return {
        "output_path": output_path,
        "duration_seconds": duration,
        "word_count": word_count,
    }
