import time, asyncio, logging, sys
from pathlib import Path
from app.main import (
    _run_script_agent, _run_audio_engine, _run_asset_harvester,
    _run_remotion_render, _run_audio_master_and_assemble
)

logging.basicConfig(level=logging.INFO, format='%(message)s')

topic = "The Chernobyl Nuclear Disaster: How Human Error Caused the Worst Nuclear Accident in History"
width, height, fps = 1920, 1080, 60
max_scenes = 15
start = time.time()

try:
    # Phase 1
    print(f"[Phase 1/5] Script Generation", flush=True)
    manifest = _run_script_agent(topic, f"chronos-final-{int(time.time())}", width, height, fps, max_scenes, "gaurav-thakur-documentary")
    manifest_path = Path(f"workspace/cache/chronos-final.json")
    manifest.to_json(manifest_path)

    # Phase 2
    print(f"[Phase 2/5] Voice Synthesis", flush=True)
    manifest = _run_audio_engine(manifest)
    manifest.to_json(manifest_path)

    # Phase 3
    print(f"[Phase 3/5] Asset Harvesting", flush=True)
    manifest = asyncio.run(_run_asset_harvester(manifest, True))
    manifest.to_json(manifest_path)

    # Phase 4 - render 1800 frames
    print(f"[Phase 4/5] Render", flush=True)
    video_path = _run_remotion_render(manifest, manifest_path, width, height, fps, "workspace/output/chernobyl_final.mp4")
    if not video_path:
        print("Render failed!", flush=True)
        sys.exit(1)

    # Phase 5
    print(f"[Phase 5/5] Audio Mastering", flush=True)
    final_path = _run_audio_master_and_assemble(video_path, manifest, manifest_path, "workspace/output/chernobyl_final.mp4")

    print(f"\nCOMPLETE in {time.time()-start:.1f}s", flush=True)
    print(f"Output: {final_path}", flush=True)

except Exception as e:
    print(f"ERROR: {e}", flush=True)
    import traceback; traceback.print_exc()
    sys.exit(1)
finally:
    # Save manifest regardless
    try:
        manifest.to_json(manifest_path)
        print("Manifest saved", flush=True)
    except:
        pass
