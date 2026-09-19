"""Render F1 v2 documentary: re-master audio + render video in 3 chunks."""
import subprocess, shutil, json, time
from pathlib import Path

workspace = Path("/Users/akshatpratap/Test/backend/workspace")
remotion_dir = Path("/Users/akshatpratap/Test/remotion-engine")
manifest_path = workspace / "cache" / "chronos-f1-v2.json"

manifest = json.loads(manifest_path.read_text())
total_frames = manifest["metadata"]["total_frames"]
print(f"Total frames: {total_frames} ({total_frames/60:.0f}s = {total_frames/60/60:.2f} min)")

# Step 1: Build full audio track from voiceovers + BGM
print("\n=== Building full audio track ===")

# Get the target video duration from manifest
target_duration = manifest["metadata"]["total_duration_seconds"]
print(f"Target duration: {target_duration:.1f}s")

voiceovers = []
for scene in manifest["scenes"]:
    audio_path = scene["voiceover"]["audio_path"]
    full_path = remotion_dir / "public" / audio_path
    if full_path.exists():
        voiceovers.append(full_path)
print(f"Voiceovers: {len(voiceovers)}")

# Concat voiceovers with PADs to match scene durations
# This ensures each voiceover fills its full scene duration
concat_list = workspace / "output" / "voiceover_concat_v2.txt"
concat_list.parent.mkdir(parents=True, exist_ok=True)

# Build a concat list with proper gaps between scenes
# Use ffmpeg's concat demuxer with -itsoffset? No, simpler: pad each scene's audio to duration
# Then concat the padded versions
padded_audios = []
for i, (scene, vo) in enumerate(zip(manifest["scenes"], voiceovers)):
    target = scene["duration_seconds"]
    # Get actual voiceover duration
    dur_res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(vo)],
        capture_output=True, text=True
    )
    actual = float(dur_res.stdout.strip())
    pad_needed = max(0, target - actual)
    
    padded = workspace / "output" / f"padded_{scene['scene_id']}.wav"
    if pad_needed > 0.5:
        # Pad with silence
        subprocess.run([
            "ffmpeg", "-y", "-i", str(vo),
            "-af", f"apad=pad_dur={pad_needed}",
            "-c", "pcm_s16le", "-ar", "48000", "-ac", "2",
            str(padded)
        ], capture_output=True, timeout=30)
    else:
        # No padding needed
        subprocess.run([
            "ffmpeg", "-y", "-i", str(vo),
            "-c", "pcm_s16le", "-ar", "48000", "-ac", "2",
            str(padded)
        ], capture_output=True, timeout=30)
    padded_audios.append(padded)

# Now concat the padded audios (they're all uniform: 48000Hz, 2 channels, pcm_s16le)
concat_padded_list = workspace / "output" / "padded_concat_list.txt"
with open(concat_padded_list, "w") as f:
    for pa in padded_audios:
        f.write(f"file '{pa.absolute()}'\n")

intermediate_vo = workspace / "output" / "voiceover_concat_v2.wav"
print(f"Concatenating {len(padded_audios)} padded voiceovers...")
result = subprocess.run(
    ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_padded_list),
     "-c", "pcm_s16le", "-ar", "48000", "-ac", "2", str(intermediate_vo)],
    capture_output=True, text=True, timeout=120,
)
if result.returncode != 0:
    print(f"FAIL: {result.stderr[-500:]}")
    raise SystemExit(1)

dur_res = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
     "-of", "default=noprint_wrappers=1:nokey=1", str(intermediate_vo)],
    capture_output=True, text=True
)
voiceover_duration = float(dur_res.stdout.strip())
print(f"Voiceover concat duration: {voiceover_duration:.1f}s (target: {target_duration:.1f}s)")

# Mix with BGM
bgm = remotion_dir / "public" / "workspace" / "assets" / "audio" / "cinematic_ambient_bgm.mp3"
final_audio = workspace / "output" / "f1_money_v2_audio.mp4"
print(f"Mixing with BGM (path={bgm}, exists={bgm.exists()})...")
mix_cmd = [
    "ffmpeg", "-y",
    "-i", str(intermediate_vo),
    "-i", str(bgm),
    "-filter_complex",
    f"[1:a]volume=0.25,aloop=loop=-1:size=2e+09[bgm];"
    f"[0:a]volume=1.0[vo];"
    f"[vo][bgm]amix=inputs=2:duration=first:dropout_transition=0[out]",
    "-map", "[out]",
    "-c:a", "aac", "-b:a", "192k",
    "-ar", "48000", "-ac", "2",
    "-t", f"{voiceover_duration:.1f}",
    final_audio
]
result = subprocess.run(mix_cmd, capture_output=True, text=True, timeout=120)
if result.returncode != 0:
    print(f"FAIL: {result.stderr[-500:]}")
    raise SystemExit(1)
print(f"Audio: {final_audio} ({final_audio.stat().st_size/1024/1024:.1f}MB, {voiceover_duration:.0f}s)")

# Apply loudness normalization
normalized = workspace / "output" / "f1_money_v2_audio_norm.mp4"
print(f"Applying EBU R128 normalization...")
subprocess.run([
    "ffmpeg", "-y", "-i", str(final_audio),
    "-af", "loudnorm=I=-14:LRA=7:TP=-1.0",
    "-c:a", "aac", "-b:a", "192k",
    str(normalized)
], capture_output=True, timeout=120)
print(f"Normalized: {normalized.stat().st_size/1024/1024:.1f}MB")

# Step 2: Render video in 3 chunks
print("\n=== Rendering video in 3 chunks ===")
props = {"manifest": manifest, "bgmPath": "workspace/assets/audio/cinematic_ambient_bgm.mp3"}
props_json = json.dumps(props)

chunk_size = 12000
chunks = []
for i, start in enumerate(range(0, total_frames, chunk_size)):
    end = min(start + chunk_size - 1, total_frames - 1)
    chunks.append((start, end, f"v2_part{i+1}"))
print(f"Chunks: {[(s, e) for s, e, _ in chunks]}")

remotion_bin = str(remotion_dir / "node_modules" / ".bin" / "remotion")
part_outputs = []

for start, end, name in chunks:
    output = str(remotion_dir / "workspace" / "output" / f"rendered_{name}.mp4")
    print(f"\n--- {name}: frames {start}-{end} ({end-start+1} frames) ---")
    cmd = [
        "sh", remotion_bin, "render",
        "DocumentaryMaster", output,
        f"--frames={start}-{end}",
        "--quality=high",
        "--browser-executable=/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "--public-dir=public",
        "--timeout=180000",
        "--concurrency=2",
        f"--props={props_json}",
    ]
    t0 = time.time()
    result = subprocess.run(cmd, cwd=str(remotion_dir), capture_output=True, text=True, timeout=7200)
    elapsed = time.time() - t0
    if result.returncode == 0:
        print(f"  {name} OK in {elapsed/60:.1f} min")
        part_outputs.append(output)
    else:
        print(f"  {name} FAILED after {elapsed/60:.1f} min")
        print(f"  STDERR: {result.stderr[-1000:]}")

# Step 3: Concatenate chunks
print("\n=== Concatenating chunks ===")
concat_list = remotion_dir / "workspace" / "output" / "concat_list_v2.txt"
with open(concat_list, "w") as f:
    for p in part_outputs:
        f.write(f"file '{p}'\n")

concat_video = workspace / "output" / "f1_money_v2_video.mp4"
result = subprocess.run([
    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
    "-i", str(concat_list),
    "-c", "copy",
    str(concat_video)
], capture_output=True, text=True, timeout=300)
if result.returncode != 0:
    print(f"FAIL: {result.stderr[-500:]}")
print(f"Concat: {concat_video.stat().st_size/1024/1024:.1f}MB")

# Step 4: Mux with audio
print("\n=== Muxing video + audio ===")
final_output = workspace / "output" / "f1_money_FULL_v2.mp4"
result = subprocess.run([
    "ffmpeg", "-y",
    "-i", str(concat_video),
    "-i", str(normalized),
    "-c:v", "copy",
    "-c:a", "aac", "-b:a", "192k",
    "-map", "0:v:0", "-map", "1:a:0",
    "-shortest",
    str(final_output)
], capture_output=True, text=True, timeout=300)
if result.returncode == 0:
    print(f"\n*** FINAL: {final_output}")
    print(f"    Size: {final_output.stat().st_size/1024/1024:.1f}MB")
    # Get duration
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(final_output)],
        capture_output=True, text=True
    )
    print(f"    Duration: {float(dur.stdout.strip()):.1f}s")
else:
    print(f"FAIL: {result.stderr[-500:]}")
