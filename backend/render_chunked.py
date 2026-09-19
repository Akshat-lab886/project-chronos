"""Render the F1 documentary in 3 sequential chunks for reliability."""
import subprocess, shutil, json, time
from pathlib import Path
from app.core.config import get_settings
from app.core.schemas import ProjectChronosManifest

settings = get_settings()
project_root = Path(__file__).resolve().parent.parent
remotion_dir = project_root / "remotion-engine"
manifest_path = Path("workspace/cache/chronos-f1.json")

# Load manifest
manifest = ProjectChronosManifest.model_validate_json(manifest_path.read_text())
total_frames = manifest.metadata.total_frames

print(f"Total frames to render: {total_frames}", flush=True)

# Setup: copy workspace assets
src_workspace = settings.workspace_dir
dst_public = remotion_dir / "public"
dst_public.mkdir(parents=True, exist_ok=True)
dst_workspace = dst_public / "workspace"
if dst_workspace.exists():
    shutil.rmtree(dst_workspace)
if src_workspace.exists():
    shutil.copytree(src_workspace, dst_workspace)
shutil.copy(manifest_path, dst_public / "manifest.json")
print(f"Assets copied to {dst_workspace}", flush=True)

# Build props
props_json = manifest.model_dump_json()
props_json = json.dumps({"manifest": json.loads(props_json), "bgmPath": "assets/audio/cinematic_ambient_bgm.mp3"})

# Define 3 chunks with 1-frame overlap for safety
chunk_size = 12540  # ~5.5 minutes per chunk at 60fps
chunks = []
for i, start in enumerate(range(0, total_frames, chunk_size)):
    end = min(start + chunk_size - 1, total_frames - 1)
    chunks.append((start, end, f"part{i+1}"))
print(f"Split into {len(chunks)} chunks: {[(s, e) for s, e, _ in chunks]}", flush=True)

remotion_bin = str(remotion_dir / "node_modules" / ".bin" / "remotion")
part_outputs = []

for start, end, name in chunks:
    output = str(remotion_dir / "workspace" / "output" / f"rendered_{name}.mp4")
    print(f"\n=== Rendering {name}: frames {start}-{end} ({end-start+1} frames) ===", flush=True)
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
        print(f"  {name} complete in {elapsed/60:.1f} min -> {output}", flush=True)
        part_outputs.append(output)
    else:
        print(f"  {name} FAILED after {elapsed/60:.1f} min", flush=True)
        # Print last 1000 chars of stderr
        print(f"  STDERR: {result.stderr[-1000:]}", flush=True)
        print(f"  STDOUT (last): {result.stdout[-500:]}", flush=True)
        # Don't bail — continue with other chunks

# Concatenate all parts
print(f"\n=== Concatenating {len(part_outputs)} parts ===", flush=True)
concat_list = remotion_dir / "workspace" / "output" / "concat_list.txt"
with open(concat_list, "w") as f:
    for p in part_outputs:
        f.write(f"file '{p}'\n")

final_output = "workspace/output/f1_money_full_chunked.mp4"
concat_cmd = [
    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
    "-i", str(concat_list),
    "-c", "copy",
    final_output,
]
result = subprocess.run(concat_cmd, capture_output=True, text=True, timeout=300)
if result.returncode == 0:
    print(f"Concat complete: {final_output}", flush=True)
    import os
    print(f"Size: {os.path.getsize(final_output) / 1024 / 1024:.1f} MB", flush=True)
else:
    print(f"Concat FAILED: {result.stderr[-500:]}", flush=True)
