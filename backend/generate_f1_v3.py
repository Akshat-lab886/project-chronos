"""F1 documentary v3 pipeline: multi-image crossfade, real video attempts, tighter timing.

Improvements over v2:
- 3 images per scene (crossfaded mid-scene)
- Tries to find F1 video clips for motion
- Scene duration = actual voiceover length + 0.5s (no padding waste)
- Better F1 query coverage
- New visual_asset.secondary_images list for crossfade
"""
import json
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

from app.agents.f1_content import build_f1_manifest
from app.engines.multi_harvester import harvest_multi_assets
from app.engines.edge_tts_cli import synthesize_cli
from app.engines.audio_engine import FasterWhisperAligner
from app.core.schemas import ProjectChronosManifest

workspace = Path("/Users/akshatpratap/Test/backend/workspace")
remotion_public = Path("/Users/akshatpratap/Test/remotion-engine/public")
asset_dir = workspace / "assets"
img_dir = asset_dir / "images"
img_dir.mkdir(parents=True, exist_ok=True)
vo_dir = asset_dir / "voiceovers"
vo_dir.mkdir(parents=True, exist_ok=True)
cache_dir = workspace / "cache"
cache_dir.mkdir(parents=True, exist_ok=True)
manifest_path = cache_dir / "chronos-f1-v3.json"


def step1_manifest():
    """Generate the F1 content manifest with tighter timing."""
    print("=" * 60)
    print("STEP 1: Generate F1 documentary v3 manifest")
    print("=" * 60)

    manifest = build_f1_manifest("How F1 Teams Make Money", "f1-doc-v3", 1920, 1080, 60)
    print(f"Initial: {len(manifest.scenes)} scenes, {manifest.metadata.total_duration_seconds:.0f}s")

    # We'll set start_frame later, after we know actual voiceover durations
    return manifest


def step2_tts(manifest) -> dict:
    """Generate TTS voiceovers and measure actual durations."""
    print("\n" + "=" * 60)
    print("STEP 2: Generate TTS voiceovers")
    print("=" * 60)

    actual_durations = {}
    for i, scene in enumerate(manifest.scenes):
        out_path = vo_dir / f"{scene.scene_id}.mp3"
        if out_path.exists() and out_path.stat().st_size > 1000:
            # Re-measure to be safe
            dur = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(out_path)],
                capture_output=True, text=True
            )
            actual_durations[scene.scene_id] = float(dur.stdout.strip())
            # Set audio_path
            scene.voiceover.audio_path = f"assets/voiceovers/{out_path.name}"
            scene.voiceover.duration_seconds = actual_durations[scene.scene_id]
            print(f"  [{i+1}/15] SKIP {scene.scene_id} ({actual_durations[scene.scene_id]:.1f}s)")
            continue
        try:
            result = synthesize_cli(
                text=scene.narrative,
                output_path=str(out_path.absolute()),
                voice_id="en-US-GuyNeural",
            )
            actual_durations[scene.scene_id] = result["duration_seconds"]
            # Set audio_path
            scene.voiceover.audio_path = f"assets/voiceovers/{out_path.name}"
            scene.voiceover.duration_seconds = result["duration_seconds"]
            print(f"  [{i+1}/15] {scene.scene_id}: {result['duration_seconds']:.1f}s")
        except Exception as e:
            print(f"  [{i+1}/15] {scene.scene_id}: FAILED {e}")
            actual_durations[scene.scene_id] = scene.duration_seconds

    return actual_durations


def step3_set_durations(manifest, actual_durations):
    """Set scene durations = voiceover + 0.3s breathing room, no padding waste."""
    print("\n=== Adjusting scene durations to voiceover length ===")
    cum = 0
    for scene in manifest.scenes:
        actual = actual_durations.get(scene.scene_id, scene.duration_seconds)
        # Add 0.3s for breathing room, round up to 0.5s grid
        new_dur = actual + 0.3
        # Round up to nearest 0.5s for clean frame counts
        new_dur = round(new_dur * 2) / 2
        new_frames = int(new_dur * 60)  # fps=60
        scene.start_frame = cum
        scene.duration_seconds = new_dur
        scene.duration_frames = new_frames
        cum += new_frames
        print(f"  {scene.scene_id}: {actual:.1f}s -> {new_dur:.1f}s ({new_frames} frames)")

    # Update metadata
    manifest.metadata.total_duration_seconds = cum / 60
    manifest.metadata.total_frames = cum
    print(f"\nTotal: {manifest.metadata.total_duration_seconds:.1f}s, {cum} frames")


def step4_harvest_multi(manifest):
    """Harvest 3 images per scene + try video for some."""
    print("\n" + "=" * 60)
    print("STEP 4: Harvest multi-asset images (3 per scene)")
    print("=" * 60)

    # Try to grab videos for 5 key scenes (pick the most action-heavy)
    video_scenes = {
        "scene_00_hook",    # Formula 1 race car
        "scene_02_hook",    # Four Streams
        "scene_09_conflict",# Race Fees
        "scene_11_climax",  # Pit Stops
        "scene_14_outro",   # Future
    }

    for i, scene in enumerate(manifest.scenes):
        # Always harvest fresh 3 images for v3
        queries = scene.search_queries
        # If we already have 3 images, use them; otherwise harvest more
        existing = sorted([p for p in img_dir.glob(f"{scene.scene_id}_*.jpg")])
        if len(existing) >= 2:
            # Reuse existing
            primary = img_dir / f"{scene.scene_id}_1.jpg"
            scene.visual_asset.asset_uri = f"workspace/assets/images/{primary.name}"
            scene.visual_asset.secondary_assets = [
                f"workspace/assets/images/{p.name}" for p in existing[1:]
            ]
            print(f"  [{i+1}/15] {scene.scene_id}: reuse {len(existing)} images")
            continue

        result = harvest_multi_assets(
            scene_id=scene.scene_id,
            queries=queries,
            asset_dir=img_dir,
            num_images=3,
            try_video=(scene.scene_id in video_scenes),
        )
        if result["images"]:
            primary_path = img_dir / f"{scene.scene_id}_1.jpg"
            if not primary_path.exists() and result["images"]:
                # Fall back to whatever first
                primary_path = img_dir / result["images"][0]
            scene.visual_asset.asset_uri = f"workspace/assets/images/{primary_path.name}"
            # Build secondary list
            scene.visual_asset.secondary_assets = [
                f"workspace/assets/images/{img_dir / img_name}"
                for img_name in result["images"][1:]
            ]
            print(f"  [{i+1}/15] {scene.scene_id}: {len(result['images'])} images, video={'Y' if result['video'] else 'N'}")
        else:
            print(f"  [{i+1}/15] {scene.scene_id}: FAILED to harvest")


def step5_align(manifest):
    """Re-align word-level captions for each scene."""
    print("\n" + "=" * 60)
    print("STEP 5: Align word-level captions")
    print("=" * 60)

    aligner = FasterWhisperAligner(model_size="tiny")
    print(f"  Aligner available: {aligner._available}")

    if not aligner._available:
        # Fall back to proportional
        for i, scene in enumerate(manifest.scenes):
            words = scene.narrative.split()
            n = len(words)
            if n == 0:
                continue
            per_word = scene.duration_frames / n
            scene.captions = [
                {"word": w, "start_frame": int(scene.start_frame + j * per_word),
                 "end_frame": int(scene.start_frame + (j + 1) * per_word)}
                for j, w in enumerate(words)
            ]
            print(f"  [{i+1}/15] {scene.scene_id}: {n} words (proportional)")
        return

    for i, scene in enumerate(manifest.scenes):
        audio_rel = scene.voiceover.audio_path
        # Strip leading workspace/ if present
        if audio_rel.startswith("workspace/"):
            audio_rel = audio_rel[len("workspace/"):]
        audio_path = workspace / audio_rel
        if not audio_path.exists():
            print(f"  [{i+1}/15] {scene.scene_id}: audio not found at {audio_path}")
            continue
        try:
            aligned = aligner.align(
                audio_path=str(audio_path),
                text=scene.narrative,
            )
            words = aligned.captions if hasattr(aligned, "captions") else aligned
            shifted = []
            for w in words:
                if hasattr(w, "start_frame"):
                    w.start_frame = (w.start_frame or 0) + scene.start_frame
                    w.end_frame = (w.end_frame or 0) + scene.start_frame
                    shifted.append(w)
                else:
                    shifted.append({
                        "word": w.get("word", ""),
                        "start_frame": w.get("start_frame", 0) + scene.start_frame,
                        "end_frame": w.get("end_frame", 0) + scene.start_frame,
                    })
            scene.captions = shifted
            print(f"  [{i+1}/15] {scene.scene_id}: {len(shifted)} words aligned")
        except Exception as e:
            print(f"  [{i+1}/15] {scene.scene_id}: align FAILED {e}")


def step6_save(manifest):
    """Save the final manifest."""
    print("\n" + "=" * 60)
    print("STEP 6: Save manifest")
    print("=" * 60)

    # Build serializable dict
    final_data = {
        "project_id": manifest.project_id,
        "title": manifest.title,
        "metadata": {
            "title": manifest.metadata.title,
            "topic": "How F1 Teams Make Money",
            "width": 1920,
            "height": 1080,
            "fps": 60,
            "total_duration_seconds": manifest.metadata.total_duration_seconds,
            "total_frames": manifest.metadata.total_frames,
            "aspect_ratio": 16/9,
            "created_at": datetime.now().isoformat(),
        },
        "scenes": [s.model_dump() for s in manifest.scenes],
        "audio_tracks": [],
        "sfx_triggers": [],
        "version": "3.0.0",
    }
    manifest_path.write_text(json.dumps(final_data, indent=2))
    print(f"Saved: {manifest_path}")
    print(f"  Scenes: {len(final_data['scenes'])}")
    print(f"  Frames: {final_data['metadata']['total_frames']}")
    print(f"  Duration: {final_data['metadata']['total_duration_seconds']:.1f}s")
    print(f"  Images: {sum(1 for s in final_data['scenes'] if s['visual_asset']['asset_uri'])}/15")

    # Copy to remotion
    shutil.copy(manifest_path, remotion_public / "manifest.json")
    # Sync assets
    if (remotion_public / "workspace" / "assets").exists():
        shutil.rmtree(remotion_public / "workspace" / "assets")
    shutil.copytree(asset_dir, remotion_public / "workspace" / "assets")
    print("Manifest + assets copied to remotion public dir")


if __name__ == "__main__":
    manifest = step1_manifest()
    actual_durations = step2_tts(manifest)
    step3_set_durations(manifest, actual_durations)
    step4_harvest_multi(manifest)
    step5_align(manifest)
    step6_save(manifest)
    print("\n" + "=" * 60)
    print("F1 v3 MANIFEST READY")
    print("=" * 60)
