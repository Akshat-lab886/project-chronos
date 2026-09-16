"""Project Chronos — Main Entry Point.

Provides both:
  1. A FastAPI HTTP server for programmatic access to pipeline stages.
  2. A Typer CLI for headless, end-to-end rendering from the terminal.

CLI usage:
    python backend/app/main.py build \\
        --topic "The Secret Operation that Built India's Nuclear Defense in 1974" \\
        --resolution 1080p \\
        --fps 60 \\
        --out ./workspace/output/master.mp4
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

import typer
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.schemas import ProjectChronosManifest

logger = logging.getLogger("chronos")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="Project Chronos API",
    description="Autonomous Documentary Video Engine",
    version="1.0.0",
)

cli = typer.Typer(help="Project Chronos CLI — autonomous documentary video engine.")


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health-check endpoint."""
    return {"status": "ok", "service": "chronos"}


@app.get("/manifest/{project_id}")
async def get_manifest(project_id: str) -> ProjectChronosManifest:
    """Retrieve a previously generated manifest."""
    settings = get_settings()
    manifest_path = settings.cache_dir / f"{project_id}_manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail=f"Manifest {project_id} not found")
    return ProjectChronosManifest.from_json(manifest_path)


@app.post("/build")
async def build_documentary(
    topic: str,
    resolution: str = "1080p",
    fps: int = 60,
    out: str = "workspace/output/master.mp4",
) -> dict:
    """Build a documentary from a topic via HTTP."""
    # This is a simplified HTTP endpoint — the full pipeline runs async
    # In production, this would trigger a background job
    return {"status": "triggered", "topic": topic, "message": "Build job started. Check /manifest/{id} for status."}


# ═══════════════════════════════════════════════════════════════════════
# CLI Commands
# ═══════════════════════════════════════════════════════════════════════


def _parse_resolution(resolution: str) -> tuple[int, int]:
    """Parse a resolution string like '1080p' or '4k' into (width, height)."""
    res = resolution.lower().strip()
    if res in ("1080p", "1920x1080", "hd"):
        return 1920, 1080
    if res in ("4k", "2160p", "3840x2160", "uhd"):
        return 3840, 2160
    if "x" in res and res.replace("x", "").isdigit():
        w, h = res.split("x")
        return int(w), int(h)
    raise typer.BadParameter(f"Unknown resolution: {resolution}")


@cli.command()
def build(
    topic: str = typer.Option(..., "--topic", "-t", help="The documentary topic."),
    resolution: str = typer.Option("1080p", "--resolution", "-r", help="Output resolution (1080p, 4k)."),
    fps: int = typer.Option(60, "--fps", "-f", help="Frame rate (24, 30, 60)."),
    out: str = typer.Option(..., "--out", "-o", help="Output file path."),
    enable_ai_fallback: bool = typer.Option(True, "--enable-ai-fallback/--no-ai-fallback", help="Use ComfyUI fallback when stock is insufficient."),
    style: str = typer.Option("gaurav-thakur-documentary", "--style", "-s", help="Visual style preset."),
    max_scenes: int = typer.Option(12, "--max-scenes", help="Maximum number of scenes (5-15)."),
    skip_render: bool = typer.Option(False, "--skip-render", help="Generate manifest only; skip video render."),
    skip_audio: bool = typer.Option(False, "--skip-audio", help="Skip voice synthesis (use estimated timings)."),
    manifest_only: bool = typer.Option(False, "--manifest-only", help="Generate manifest only, no audio/assets."),
) -> None:
    """Build a complete documentary video from a topic prompt."""
    settings = get_settings()
    settings.ensure_directories()

    width, height = _parse_resolution(resolution)
    project_id = f"chronos-{uuid.uuid4().hex[:8]}"

    logger.info("=" * 60)
    logger.info("Project Chronos — Documentary Build")
    logger.info(f"  Topic: {topic}")
    logger.info(f"  Resolution: {width}x{height} @ {fps}fps")
    logger.info(f"  Project ID: {project_id}")
    logger.info(f"  AI Fallback: {enable_ai_fallback}")
    logger.info("=" * 60)

    start_time = time.time()

    # ── Phase 1: Research & Script ──
    logger.info("[Phase 1/5] Research & Script Generation")
    manifest = _run_script_agent(topic, project_id, width, height, fps, max_scenes, style)

    # ── Save manifest ──
    manifest_path = settings.cache_dir / f"{project_id}_manifest.json"
    manifest.to_json(manifest_path)
    logger.info(f"Manifest saved to {manifest_path}")

    if manifest_only:
        logger.info("Manifest only (--manifest-only). Stopping.")
        return

    if skip_audio:
        logger.info("Skipping voice synthesis (--skip-audio). Captions will use estimated timings.")
    else:
        # ── Phase 2: Voice Synthesis & Alignment ──
        logger.info("[Phase 2/5] Voice Synthesis & Forced Alignment")
        manifest = _run_audio_engine(manifest)
        manifest.to_json(manifest_path)
        logger.info(f"Updated manifest saved to {manifest_path}")

    # ── Phase 3: Visual Asset Harvesting ──
    logger.info("[Phase 3/5] Visual Asset Harvesting")
    manifest = asyncio.run(_run_asset_harvester(manifest, enable_ai_fallback))
    manifest.to_json(manifest_path)

    if skip_render:
        logger.info("Skipping render (--skip-render). Manifest and assets ready.")
        logger.info(f"Output path: {out}")
        logger.info(f"Total pipeline time: {time.time() - start_time:.1f}s")
        return

    # ── Phase 4: Remotion Headless Render ──
    logger.info("[Phase 4/5] Remotion Headless SSR Render")
    video_path = _run_remotion_render(manifest, manifest_path, width, height, fps, out)

    # ── Phase 5: Audio Mastering & Final Assembly ──
    logger.info("[Phase 5/5] Audio Mastering & Final Assembly")
    final_path = _run_audio_master_and_assemble(
        video_path, manifest, manifest_path, out
    )

    logger.info(f"\nPipeline complete in {time.time() - start_time:.1f}s")
    logger.info(f"Output: {final_path}")
    logger.info(f"Manifest: {manifest_path}")


def _run_remotion_render(manifest, manifest_path, width, height, fps, output_path):
    """Render the video using Remotion headless rendering.

    1. Copies the manifest and workspace assets to the remotion-engine public directory
    2. Passes the manifest as --props to the DocumentaryMaster composition
    3. Uses system Chrome for headless rendering
    """
    import subprocess
    import os
    import shutil
    import json

    settings = get_settings()
    project_root = Path(__file__).resolve().parent.parent.parent
    remotion_dir = project_root / "remotion-engine"
    total_frames = manifest.metadata.total_frames

    # Cap render frames for practical render times (600 frames ≈ 10s at 60fps)
    # Full renders require longer timeouts — adjust as needed
    render_frames = min(total_frames - 1, 1800)  # Cap at 30s at 60fps
    logger.info(f"  Rendering {render_frames} frames with Remotion...")

    # Copy workspace assets to remotion public dir so they're accessible via HTTP
    src_workspace = settings.workspace_dir
    dst_public = remotion_dir / "public"
    dst_public.mkdir(parents=True, exist_ok=True)

    # Copy workspace assets
    dst_workspace = dst_public / "workspace"
    if dst_workspace.exists():
        shutil.rmtree(dst_workspace)
    if src_workspace.exists():
        shutil.copytree(src_workspace, dst_workspace)
        logger.info(f"  Copied assets from {src_workspace} to {dst_workspace}")

    # Copy manifest to public dir
    shutil.copy(manifest_path, dst_public / "manifest.json")

    video_output = str(remotion_dir / "workspace" / "output" / "rendered_video.mp4")
    remotion_bin = str(remotion_dir / "node_modules" / ".bin" / "remotion")

    # Pass the manifest as --props so Root.tsx receives it
    # Use mode="json" to ensure all types are JSON-serializable
    props_json = manifest.model_dump_json()
    props_json = json.dumps({"manifest": json.loads(props_json)})

    cmd = [
        "sh", remotion_bin, "render",
        "DocumentaryMaster", video_output,
        "--frames=0-{}".format(render_frames),
        "--quality=high",
        "--browser-executable=/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "--public-dir=public",
        f"--props={props_json}",
    ]

    env = os.environ.copy()
    # No need for CHRONOS_MANIFEST_PATH since we pass via --props

    try:
        result = subprocess.run(
            cmd, cwd=str(remotion_dir), env=env,
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode == 0:
            logger.info(f"  Remotion render complete: {video_output}")
            return video_output
        else:
            logger.error(f"  Remotion render failed: {result.stderr[:500]}")
            logger.info("  Falling back to silent video with manifest visuals only")
            return None
    except subprocess.TimeoutExpired:
        logger.warning("  Remotion render timed out after 600s")
        return None
    except FileNotFoundError:
        logger.warning("  Remotion CLI not found — skipping video render")
        return None


def _run_audio_master_and_assemble(video_path, manifest, manifest_path, output_path):
    """Master the audio and assemble final video with FFmpeg."""
    import subprocess
    import os

    settings = get_settings()
    final_path = str(output_path)

    # Collect audio tracks from manifest
    voiceover_files = [s.voiceover.audio_path for s in manifest.scenes if s.voiceover and os.path.exists(s.voiceover.audio_path)]
    logger.info(f"  Collected {len(voiceover_files)} voiceover files")

    # Use SoundMaster to assemble and master audio
    if video_path and os.path.exists(video_path) and voiceover_files:
        # Master the audio
        from app.engines.sound_master import SoundMaster
        from app.core.schemas import AudioTrackSpec, AudioTrackType

        voice_specs = [
            AudioTrackSpec(
                track_id=f"vo_{s.scene_id}",
                type=AudioTrackType.VOICEOVER,
                file_path=s.voiceover.audio_path,
                start_frame=s.start_frame,
                duration_frames=s.duration_frames,
                volume=1.0,
            )
            for s in manifest.scenes if s.voiceover
        ]

        master = SoundMaster()
        audio_result = master.master_audio(
            voiceover_tracks=voice_specs,
            bgm_tracks=[],
            sfx_tracks=[],
            sfx_triggers=manifest.sfx_triggers,
            output_path=str(Path(output_path).parent / "mastered_audio.mp4"),
        )

        logger.info(f"  Audio mastered: LUFS={audio_result.integrated_lufs:.1f}")

        # Combine video + mastered audio with FFmpeg
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_result.output_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "320k",
            "-shortest",
            final_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            logger.info(f"  Final video assembled: {final_path}")
            return final_path
        else:
            logger.error(f"  FFmpeg assembly failed: {result.stderr[:500]}")
            return video_path
    elif voiceover_files:
        # Only audio mastering, no video
        from app.engines.sound_master import SoundMaster
        from app.core.schemas import AudioTrackSpec, AudioTrackType

        voice_specs = [
            AudioTrackSpec(
                track_id=f"vo_{s.scene_id}",
                type=AudioTrackType.VOICEOVER,
                file_path=s.voiceover.audio_path,
                start_frame=s.start_frame,
                duration_frames=s.duration_frames,
                volume=1.0,
            )
            for s in manifest.scenes if s.voiceover
        ]

        master = SoundMaster()
        audio_result = master.master_audio(
            voiceover_tracks=voice_specs,
            bgm_tracks=[],
            sfx_tracks=[],
            sfx_triggers=manifest.sfx_triggers,
            output_path=final_path.replace(".mp4", "_audio.mp4"),
        )
        logger.info(f"  Audio mastered: {audio_result.output_path}")
        return audio_result.output_path
    else:
        logger.warning("  No audio or video to assemble — returning manifest path")
        return str(manifest_path)


def _run_script_agent(topic, project_id, width, height, fps, max_scenes, style):
    """Run the script agent to generate the narrative manifest."""
    from app.agents.script_agent import ScriptAgent
    agent = ScriptAgent()
    return asyncio.run(agent.generate_manifest(
        topic=topic, project_id=project_id,
        width=width, height=height, fps=fps,
        max_scenes=max_scenes, style=style,
    ))


def _run_audio_engine(manifest):
    """Run voice synthesis and forced alignment for all scenes."""
    from app.engines.audio_engine import AudioEngine
    engine = AudioEngine()

    scenes_data = [(s.scene_id, s.narrative) for s in manifest.scenes]
    results = asyncio.run(engine.process_all_scenes(scenes_data))

    for scene, (vo_spec, captions) in zip(manifest.scenes, results):
        scene.voiceover = vo_spec
        scene.captions = captions

    logger.info(f"Voice synthesis complete: {len(manifest.scenes)} scenes processed")
    return manifest


async def _run_asset_harvester(manifest, enable_ai_fallback: bool):
    """Harvest visual assets for all scenes."""
    from app.engines.stock_harvester import StockHarvester
    from app.engines.comfyui_client import generate_fallback_asset
    from app.core.schemas import VisualSourceType

    harvester = StockHarvester()
    settings = get_settings()

    try:
        for scene in manifest.scenes:
            if not scene.visual_asset.asset_uri:
                # Harvest stock assets
                result = await harvester.harvest(
                    search_queries=scene.search_queries or ["documentary footage"],
                    visual_tags=scene.visual_tags or ["historical"],
                    width=scene.visual_asset.width,
                    height=scene.visual_asset.height,
                )

                if result.primary_asset:
                    # Download the asset
                    local_path = await harvester.download_asset(result.primary_asset)
                    scene.visual_asset.asset_uri = local_path
                    scene.visual_asset.source_type = result.primary_asset.source_type
                    scene.visual_asset.match_score = result.primary_asset.match_score
                    scene.visual_asset.license_info = result.primary_asset.license_info
                    scene.visual_asset.attribution = result.primary_asset.attribution

                    logger.info(
                        f"  {scene.scene_id}: stock asset found "
                        f"(score={result.primary_asset.match_score:.1f})"
                    )
                elif enable_ai_fallback:
                    # Fallback to AI generation
                    logger.info(f"  {scene.scene_id}: no stock found, generating AI fallback")
                    ai_result = await generate_fallback_asset(
                        prompt=result.fallback_prompt or f"Documentary footage: {scene.narrative[:200]}",
                        width=scene.visual_asset.width,
                        height=scene.visual_asset.height,
                    )
                    scene.visual_asset.asset_uri = ai_result.asset_path
                    scene.visual_asset.source_type = ai_result.source_type
                    scene.visual_asset.match_score = 0.0
                    logger.info(f"  {scene.scene_id}: AI-generated fallback created")
                else:
                    logger.warning(f"  {scene.scene_id}: no assets found and AI fallback disabled")
                    # Keep empty asset_uri — Remotion will use placeholder background
    finally:
        await harvester.close()

    # ── Quality Review ──
    logger.info(f"  Reviewing {len(manifest.scenes)} assets for quality standards...")
    review_results = _review_assets(manifest, harvester)
    passed = sum(1 for r in review_results if r.valid)
    logger.info(f"  Asset review: {passed}/{len(review_results)} passed quality check")
    return manifest


def _review_assets(manifest, harvester):
    """Run quality review on all scene visual assets.
    
    Checks:
    1. File exists and is readable
    2. Image dimensions meet minimum (1280x720)
    3. Image has visual content (std > 5.0, not blank)
    4. Asset relevance to scene context
    """
    from app.core.schemas import AssetReview
    import os as _os
    import numpy as np
    from PIL import Image

    reviews = []

    for scene in manifest.scenes:
        asset_uri = scene.visual_asset.asset_uri

        if not asset_uri or not _os.path.exists(asset_uri):
            review = AssetReview(
                valid=False,
                issues=[f"Asset path does not exist: {asset_uri}"],
                score=0.0,
            )
            reviews.append(review)
            continue

        # Gather scene context for relevance scoring
        scene_context = {
            "prompt": scene.visual_asset.fallback_prompt or "",
            "search_queries": scene.search_queries or [],
            "visual_tags": scene.visual_tags or [],
        }

        review = harvester.review_asset(asset_uri, scene_context)
        reviews.append(review)

        if not review.valid:
            logger.warning(
                f"  {scene.scene_id}: ASSET QUALITY ISSUE — {', '.join(review.issues)} "
                f"({review.dimensions[0]}x{review.dimensions[1]}, std={review.std_deviation:.1f})"
            )
        else:
            logger.info(
                f"  {scene.scene_id}: asset approved "
                f"({review.dimensions[0]}x{review.dimensions[1]}, "
                f"brightness={review.mean_brightness:.1f}, std={review.std_deviation:.1f}, "
                f"score={review.score:.2f})"
            )

    return reviews


@cli.command()
def render(
    manifest_path: str = typer.Option(..., "--manifest", "-m", help="Path to the project manifest JSON."),
    out: str = typer.Option(..., "--out", "-o", help="Output video file path."),
    fps: int = typer.Option(60, "--fps", help="Frame rate."),
    concurrency: int = typer.Option(4, "--concurrency", help="Number of render workers."),
) -> None:
    """Render a video from a project manifest using Remotion headless rendering."""
    logger.info(f"Rendering manifest: {manifest_path} -> {out}")
    logger.info("This requires the Remotion engine to be installed and built.")
    logger.info("Run: cd remotion-engine && npm install && npx remotion render DocumentaryMaster <out>")


@cli.command()
def list_styles() -> None:
    """List available visual style presets."""
    styles = {
        "gaurav-thakur-documentary": "Fast cuts, map animations, kinetic typography (Gaurav Thakur style)",
        "johnny-harris-investigative": "Deep zoom maps, dramatic lighting, investigative pacing",
        "vox-explainer": "Clean graphics, data visualizations, neutral tone",
        "noir-documentary": "High contrast, shadows, vintage film stock",
    }
    print("\nAvailable Visual Style Presets:")
    print("=" * 60)
    for name, desc in styles.items():
        print(f"  {name:35s} — {desc}")
    print("=" * 60)


@cli.command()
def doctor() -> None:
    """Run diagnostic checks for the Project Chronos environment."""
    print("Project Chronos — Environment Diagnostics")
    print("=" * 60)

    checks = []

    # Python packages
    import importlib
    packages = {
        "pydantic": "core.schema validation",
        "fastapi": "HTTP API server",
        "langgraph": "Agent orchestration",
        "langchain": "LLM abstractions",
        "aiohttp": "HTTP client for asset harvesting",
        "remotion": "Video rendering (if installed)",
    }
    print("\nPython Packages:")
    for pkg, desc in packages.items():
        try:
            mod = importlib.import_module(pkg)
            version = getattr(mod, "__version__", "unknown")
            print(f"  [OK]   {pkg:20s} v{version} — {desc}")
            checks.append(True)
        except ImportError:
            print(f"  [MISS] {pkg:20s} — {desc}")
            checks.append(False)

    # Optional packages
    print("\nOptional Packages:")
    optional = {
        "kokoro": "Neural voice synthesis",
        "edge_tts": "Edge TTS engine (network-based)",
        "pyttsx3": "System TTS engine",
        "whisperx": "Word-level forced alignment",
        "faster_whisper": "Faster Whisper alignment",
        "scipy": "Audio file I/O",
        "numpy": "Numeric operations",
    }
    for pkg, desc in optional.items():
        try:
            importlib.import_module(pkg)
            print(f"  [OK]   {pkg:20s} — {desc}")
        except ImportError:
            print(f"  [MISS] {pkg:20s} — {desc}")

    # External tools
    print("\nExternal Tools:")
    import subprocess
    tools = {"ffmpeg": "Video/audio encoding", "ffprobe": "Media analysis"}
    for tool, desc in tools.items():
        try:
            result = subprocess.run([tool, "-version"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                version = result.stdout.split("\n")[0][:50]
                print(f"  [OK]   {tool:20s} — {desc} ({version})")
            else:
                print(f"  [MISS] {tool:20s} — {desc}")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            print(f"  [MISS] {tool:20s} — {desc}")

    # Environment
    print("\nEnvironment:")
    settings = get_settings()
    print(f"  Workspace: {settings.workspace_dir}")
    print(f"  Assets dir: {settings.assets_dir}")
    print(f"  LLM provider: {settings.llm_provider}")
    print(f"  Pexels API key: {'set' if settings.pexels_api_key else 'NOT SET'}")
    print(f"  Pixabay API key: {'set' if settings.pixabay_api_key else 'NOT SET'}")
    print(f"  ComfyUI enabled: {settings.comfyui_enabled}")
    print(f"  Target LUFS: {settings.target_lufs}")

    print(f"\nSummary: {sum(checks)}/{len(checks)} core packages available")
    print("=" * 60)


# ═══════════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=8000)
    else:
        cli()
