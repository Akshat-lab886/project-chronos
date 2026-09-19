"""F1 documentary v3 render pipeline.

Improvements over v2:
- Tighter timing (no audio gaps)
- Multi-image crossfade (3 images per scene)
- Better caption font (Bebas Neue)
- No padding waste
"""
import json
import subprocess
from pathlib import Path

workspace = Path("/Users/akshatpratap/Test/backend/workspace")
remotion_dir = Path("/Users/akshatprapai/Test/remotion-engine")
remotion_dir = Path("/Users/akshatpratap/Test/remotion-engine")
manifest_path = workspace / "cache" / "chronos-f1-v3.json"
manifest = json.loads(manifest_path.read_text())

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
REMOTION_BIN = remotion_dir / "node_modules" / ".bin" / "remotion"
TOTAL_FRAMES = manifest["metadata"]["total_frames"]
TARGET_DURATION = manifest["metadata"]["total_duration_seconds"]


def step1_build_audio():
    """Build full audio: voiceovers concatenated + BGM mix + EBU R128."""
    print("=" * 60)
    print(f"STEP 1: Audio build (target: {TARGET_DURATION:.1f}s)")
    print("=" * 60)

    voiceovers = []
    for scene in manifest["scenes"]:
        audio_rel = scene["voiceover"]["audio_path"]
        if audio_rel.startswith("workspace/"):
            audio_rel = audio_rel[len("workspace/"):]
        full_path = remotion_dir / "public" / "workspace" / audio_rel
        if full_path.exists():
            voiceovers.append((scene, full_path))
        else:
            print(f"  MISSING: {full_path}")
    print(f"  Found {len(voiceovers)} voiceovers")

    # Pad each voiceover to its scene duration (no audio gaps)
    concat_list = workspace / "output" / "padded_v3_list.txt"
    concat_list.parent.mkdir(parents=True, exist_ok=True)
    for scene, vo in voiceovers:
        target = scene["duration_seconds"]
        dur = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(vo)],
            capture_output=True, text=True
        ).stdout.strip()
        actual = float(dur)
        pad = max(0, target - actual)

        padded = workspace / "output" / f"p3_{scene['scene_id']}.wav"
        if pad > 0.3:
            subprocess.run([
                "ffmpeg", "-y", "-i", str(vo),
                "-af", f"apad=pad_dur={pad}",
                "-c", "pcm_s16le", "-ar", "48000", "-ac", "2",
                str(padded)
            ], capture_output=True, timeout=30)
        else:
            subprocess.run([
                "ffmpeg", "-y", "-i", str(vo),
                "-c", "pcm_s16le", "-ar", "48000", "-ac", "2",
                str(padded)
            ], capture_output=True, timeout=30)
    with open(concat_list, "w") as f:
        for scene, vo in voiceovers:
            padded_path = workspace / "output" / f"p3_{scene['scene_id']}.wav"
            f.write(f"file '{padded_path}'\n")

    intermediate = workspace / "output" / "voiceover_concat_v3.wav"
    print(f"  Concatenating {len(voiceovers)} padded voiceovers...")
    result = subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "pcm_s16le", "-ar", "48000", "-ac", "2",
        str(intermediate)
    ], capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"  CONCAT FAIL: {result.stderr[-500:]}")
        raise SystemExit(1)

    dur = float(subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(intermediate)
    ], capture_output=True, text=True).stdout.strip())
    print(f"  Voiceover concat: {dur:.1f}s (target: {TARGET_DURATION:.1f}s)")

    bgm = remotion_dir / "public" / "workspace" / "assets" / "audio" / "cinematic_ambient_bgm.mp3"
    final_audio = workspace / "output" / "f1_v3_audio.mp4"
    print(f"  Mixing with BGM ({bgm})...")
    result = subprocess.run([
        "ffmpeg", "-y",
        "-i", str(intermediate),
        "-i", str(bgm),
        "-filter_complex",
        f"[1:a]volume=0.20,aloop=loop=-1:size=2e+09[bgm];"
        f"[0:a]volume=1.0[vo];"
        f"[vo][bgm]amix=inputs=2:duration=first:dropout_transition=0[out]",
        "-map", "[out]",
        "-c:a", "aac", "-b:a", "192k",
        "-ar", "48000", "-ac", "2",
        "-t", f"{dur:.1f}",
        str(final_audio)
    ], capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"  MIX FAIL: {result.stderr[-500:]}")
        raise SystemExit(1)
    print(f"  Audio: {final_audio} ({final_audio.stat().st_size/1024/1024:.1f}MB)")

    # EBU R128 normalize
    norm = workspace / "output" / "f1_v3_audio_norm.mp4"
    print(f"  Applying EBU R128 normalization...")
    result = subprocess.run([
        "ffmpeg", "-y", "-i", str(final_audio),
        "-af", "loudnorm=I=-14:LRA=7:TP=-1.0",
        "-c:a", "aac", "-b:a", "192k",
        str(norm)
    ], capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"  NORM FAIL: {result.stderr[-500:]}")
        raise SystemExit(1)
    print(f"  Normalized: {norm} ({norm.stat().st_size/1024/1024:.1f}MB)")
    return norm


def step2_render_chunks():
    """Render video in 2-3 chunks based on total frames."""
    print("\n" + "=" * 60)
    print("STEP 2: Render video in chunks")
    print("=" * 60)

    # Use 10000-frame chunks
    chunk_size = 10000
    chunks = []
    for start in range(0, TOTAL_FRAMES, chunk_size):
        end = min(start + chunk_size - 1, TOTAL_FRAMES - 1)
        chunks.append((start, end))

    print(f"  Total frames: {TOTAL_FRAMES}, chunks: {chunks}")

    props = {"manifest": manifest, "bgmPath": "workspace/assets/audio/cinematic_ambient_bgm.mp3"}
    props_json = json.dumps(props)

    parts = []
    for i, (start, end) in enumerate(chunks):
        n_frames = end - start + 1
        out_part = remotion_dir / "workspace" / "output" / f"rendered_v3_part{i+1}.mp4"
        cmd = [
            "sh", str(REMOTION_BIN), "render",
            "DocumentaryMaster", str(out_part),
            f"--frames={start}-{end}",
            "--quality=high",
            f"--browser-executable={CHROME}",
            "--public-dir=public",
            "--timeout=180000",
            "--concurrency=2",
            f"--props={props_json}",
        ]
        print(f"  v3_part{i+1}: frames {start}-{end} ({n_frames} frames)")
        import time
        t0 = time.time()
        result = subprocess.run(cmd, cwd=str(remotion_dir), capture_output=True, text=True, timeout=2400)
        elapsed = (time.time() - t0) / 60
        if result.returncode == 0:
            print(f"  v3_part{i+1} OK in {elapsed:.1f} min ({out_part.stat().st_size/1024/1024:.0f}MB)")
            parts.append(out_part)
        else:
            print(f"  v3_part{i+1} FAILED")
            print(result.stderr[-1500:])
            raise SystemExit(1)
    return parts


def step3_concat(parts):
    """Concat all parts into one video."""
    print("\n" + "=" * 60)
    print("STEP 3: Concat chunks")
    print("=" * 60)

    concat_list = remotion_dir / "workspace" / "output" / "concat_v3_list.txt"
    with open(concat_list, "w") as f:
        for p in parts:
            f.write(f"file '{p.absolute()}'\n")

    concat_video = workspace / "output" / "f1_v3_video.mp4"
    result = subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list), "-c", "copy", str(concat_video)
    ], capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"  CONCAT FAIL: {result.stderr[-500:]}")
        raise SystemExit(1)
    print(f"  Concat: {concat_video} ({concat_video.stat().st_size/1024/1024:.1f}MB)")
    return concat_video


def step4_mux(video, audio):
    """Mux video + audio into final."""
    print("\n" + "=" * 60)
    print("STEP 4: Mux final video")
    print("=" * 60)

    final = workspace / "output" / "f1_money_FULL_v3.mp4"
    result = subprocess.run([
        "ffmpeg", "-y",
        "-i", str(video), "-i", str(audio),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-map", "0:v:0", "-map", "1:a:0", "-shortest",
        str(final)
    ], capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"  MUX FAIL: {result.stderr[-500:]}")
        raise SystemExit(1)

    dur = float(subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(final)
    ], capture_output=True, text=True).stdout.strip())
    size_mb = final.stat().st_size / 1024 / 1024
    print(f"\n*** FINAL: {final}")
    print(f"    Size: {size_mb:.1f}MB, Duration: {dur:.1f}s")
    return final


if __name__ == "__main__":
    print(f"F1 v3 render: {TOTAL_FRAMES} frames, {TARGET_DURATION:.1f}s")
    audio = step1_build_audio()
    parts = step2_render_chunks()
    video = step3_concat(parts)
    final = step4_mux(video, audio)
    print("\n*** DONE ***")
