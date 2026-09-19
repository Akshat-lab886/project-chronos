"""Complete F1 documentary pipeline: content + TTS + assets + render."""
import json
from pathlib import Path

from app.agents.f1_content import build_f1_manifest
from app.core.config import get_settings
from app.core.schemas import ProjectChronosManifest

settings = get_settings()
project_root = Path("/Users/akshatpratap/Test")
backend_dir = project_root / "backend"
workspace_dir = backend_dir / "workspace"
output_dir = workspace_dir / "output"
asset_dir = workspace_dir / "assets"
remotion_dir = project_root / "remotion-engine"

# Step 1: Generate F1 manifest
print("=" * 60)
print("STEP 1: Generate F1 documentary manifest")
print("=" * 60)

topic = "How F1 Teams Make Money: The Billion Dollar Business"
manifest = build_f1_manifest(topic, "f1-doc-v2", 1920, 1080, 60)
print(f"  Scenes: {len(manifest.scenes)}")
print(f"  Total: {manifest.metadata.total_duration_seconds:.0f}s ({manifest.metadata.total_duration_seconds/60:.2f} min)")
print(f"  Frames: {manifest.metadata.total_frames}")

# Save manifest
manifest_path = workspace_dir / "cache" / "chronos-f1-v2.json"
manifest_path.parent.mkdir(parents=True, exist_ok=True)
manifest_path.write_text(manifest.model_dump_json(indent=2))
print(f"  Saved: {manifest_path}")

# Step 2: Generate TTS for each scene
print("\n" + "=" * 60)
print("STEP 2: Generate TTS voiceover for each scene")
print("=" * 60)

from app.engines.edge_tts_cli import synthesize_cli

tts_dir = asset_dir / "voiceovers"
tts_dir.mkdir(parents=True, exist_ok=True)

def gen_tts_sync():
    for i, scene in enumerate(manifest.scenes):
        out_path = tts_dir / f"{scene.scene_id}.mp3"
        if out_path.exists() and out_path.stat().st_size > 1000:
            print(f"  [{i+1}/15] SKIP (exists) {scene.scene_id}")
            scene.voiceover.audio_path = str(out_path.relative_to(workspace_dir))
            continue
        try:
            result = synthesize_cli(
                text=scene.narrative,
                output_path=str(out_path.absolute()),
                voice_id="en-US-GuyNeural",
            )
            scene.voiceover.audio_path = str(out_path.relative_to(workspace_dir))
            print(f"  [{i+1}/15] {scene.scene_id}: {result['duration_seconds']:.1f}s -> {out_path.name}")
        except Exception as e:
            print(f"  [{i+1}/15] {scene.scene_id}: FAILED {e}")
            silent_path = out_path.with_suffix(".wav")
            import subprocess
            subprocess.run([
                "ffmpeg", "-y", "-f", "lavfi", "-i",
                f"anullsrc=r=24000:cl=mono", "-t", str(scene.duration_seconds),
                str(silent_path)
            ], capture_output=True, check=False)
            scene.voiceover.audio_path = str(silent_path.relative_to(workspace_dir))

gen_tts_sync()

# Update manifest with TTS paths
manifest_path.write_text(manifest.model_dump_json(indent=2))
print(f"  Manifest updated with TTS paths")

# Step 3: Harvest F1 visual assets
print("\n" + "=" * 60)
print("STEP 3: Harvest F1 visual assets (Wikimedia v2)")
print("=" * 60)

from app.engines.wikimedia_v2 import search_and_download

img_dir = asset_dir / "images"
img_dir.mkdir(parents=True, exist_ok=True)

def harvest_sync():
    for i, scene in enumerate(manifest.scenes):
        out_path = img_dir / f"{scene.scene_id}.jpg"
        if out_path.exists() and out_path.stat().st_size > 5000:
            print(f"  [{i+1}/15] SKIP (exists) {scene.scene_id}")
            scene.visual_asset.asset_uri = str(out_path.relative_to(workspace_dir))
            continue
        # Try each query in order
        success = False
        for q in scene.search_queries:
            print(f"  [{i+1}/15] {scene.scene_id}: trying '{q}'...", end=" ", flush=True)
            if search_and_download(q, str(out_path), width=1280):
                size = out_path.stat().st_size / 1024
                print(f"OK ({size:.0f}KB)")
                scene.visual_asset.asset_uri = str(out_path.relative_to(workspace_dir))
                success = True
                break
            else:
                print("FAIL")
        if not success:
            print(f"  [{i+1}/15] {scene.scene_id}: ALL QUERIES FAILED")

harvest_sync()

# Update manifest
manifest_path.write_text(manifest.model_dump_json(indent=2))
print(f"  Manifest updated with image paths")

# Step 4: Align captions using faster-whisper
print("\n" + "=" * 60)
print("STEP 4: Align captions (faster-whisper)")
print("=" * 60)

# Try whisperx first, then faster-whisper
aligner = None
try:
    aligner = WhisperXAligner()
    if not aligner._available:
        aligner = None
except Exception as e:
    print(f"  WhisperX not available: {e}")
if aligner is None:
    try:
        from app.engines.audio_engine import FasterWhisperAligner
        aligner = FasterWhisperAligner(model_size="tiny")
    except Exception as e:
        print(f"  No aligner available: {e}")
        aligner = None

print(f"  Aligner: {type(aligner).__name__ if aligner else 'NONE'}")
print(f"  Aligner available: {aligner._available if aligner else 'N/A'}")
for i, scene in enumerate(manifest.scenes):
    if not aligner:
        # No aligner - generate proportional captions
        words = scene.narrative.split()
        n_words = len(words)
        if n_words == 0:
            continue
        start_frame = scene.start_frame
        end_frame = scene.start_frame + scene.duration_frames
        per_word = (end_frame - start_frame) / n_words
        scene.captions = [
            {"word": w, "start_frame": int(start_frame + j * per_word),
             "end_frame": int(start_frame + (j + 1) * per_word)}
            for j, w in enumerate(words)
        ]
        print(f"  [{i+1}/15] {scene.scene_id}: {n_words} words (proportional)")
        continue
    if not scene.voiceover.audio_path:
        continue
    audio_full = workspace_dir / scene.voiceover.audio_path
    if not audio_full.exists():
        print(f"  [{i+1}/15] {scene.scene_id}: audio missing, skip")
        continue
    try:
        aligned = aligner.align(
            audio_path=str(audio_full),
            text=scene.narrative,
        )
        # Handle AlignmentResult (has .captions) or list
        if hasattr(aligned, "captions"):
            words = aligned.captions
        elif isinstance(aligned, list):
            words = aligned
        else:
            words = []
        # Shift word start_frame/end_frame by scene.start_frame
        shifted = []
        for w in words:
            if hasattr(w, "start_frame"):
                w.start_frame = (w.start_frame or 0) + scene.start_frame
                w.end_frame = (w.end_frame or 0) + scene.start_frame
                shifted.append(w)
            else:
                # Dict format
                shifted.append({
                    "word": w.get("word", ""),
                    "start_frame": w.get("start_frame", 0) + scene.start_frame,
                    "end_frame": w.get("end_frame", 0) + scene.start_frame,
                })
        scene.captions = shifted
        print(f"  [{i+1}/15] {scene.scene_id}: {len(shifted)} words aligned")
    except Exception as e:
        print(f"  [{i+1}/15] {scene.scene_id}: align FAILED {e}")

manifest_path.write_text(manifest.model_dump_json(indent=2))
print(f"  Manifest updated with captions")

# Summary
print("\n" + "=" * 60)
print("MANIFEST READY FOR RENDER")
print("=" * 60)
print(f"Path: {manifest_path}")
print(f"Scenes: {len(manifest.scenes)}")
print(f"Duration: {manifest.metadata.total_duration_seconds:.0f}s")
print(f"Frames: {manifest.metadata.total_frames}")
print(f"Images: {sum(1 for s in manifest.scenes if s.visual_asset.asset_uri)}/{len(manifest.scenes)}")
print(f"Audio: {sum(1 for s in manifest.scenes if s.voiceover.audio_path)}/{len(manifest.scenes)}")
print(f"Captions: {sum(len(s.captions) for s in manifest.scenes)} words total")
