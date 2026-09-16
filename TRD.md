Markdown# Technical Requirement Document (TRD)
## Project Name: Project Chronos Architecture & Implementation Specification
**Document Version:** 1.2.0 | **Stack:** Python 3.11+ • TypeScript • Remotion • ComfyUI • FFmpeg

---

### 1. System Architecture & End-to-End Data Flow

                              ┌────────────────────────┐
                              │   User CLI / Web UI    │
                              └───────────┬────────────┘
                                          │ Topic Input
                                          ▼
                             ┌──────────────────────────┐
                             │   LangGraph Controller   │
                             └────────────┬─────────────┘
                                          │
     ┌────────────────────────────────────┼───────────────────────────────────┐
     ▼                                    ▼                                   ▼
┌─────────────────┐                 ┌───────────────────┐               ┌──────────────────┐│ Script & Story- │                 │   Voice Engine    │               │ Asset Harvester  ││  board Planner  │                 │  (Kokoro/F5-TTS)  │               │ (Stock Scraper)  │└────────┬────────┘                 └─────────┬─────────┘               └────────┬─────────┘│ Scene AST                          │ Master WAV                       │ Stock Assets│                                    ▼                                  ││                          ┌───────────────────┐                        ▼│                          │     WhisperX      │               ┌──────────────────┐│                          │ (Forced Alignment)│               │ ComfyUI Fallback ││                          └─────────┬─────────┘               │  (FLUX/Wan 2.2)  ││                                    │ Word Timestamps         └────────┬─────────┘│                                    │                                  │ AI Assets└────────────────────────────────────┼──────────────────────────────────┘▼┌───────────────────────┐│   Project Manifest    ││     (project.json)    │└───────────┬───────────┘│▼┌───────────────────────┐│ Remotion Video Engine ││  (React / TypeScript) │└───────────┬───────────┘│ Headless Render Frame Pipeline▼┌───────────────────────┐│ FFmpeg Audio Masterer ││ (EBU R128 + Ducking)  │└───────────┬───────────┘│▼┌───────────────────────┐│  Final Master .MP4    │└───────────────────────┘
---

### 2. Best-in-Class Open-Source Repositories to Integrate

| Component | Repository & URL | Role in Chronos |
| :--- | :--- | :--- |
| **Video Engine** | `remotion/remotion` | Core deterministic React frame renderer. |
| **Video Pipeline** | `itsjwill/vanta` | Reference AI video engine architecture on Remotion (transitions, audio sync). |
| **Speech Engine** | `hexgrad/kokoro` or `SWivid/F5-TTS` | 82M/SOTA zero-shot voice synthesis engine. |
| **Timestamp Alignment** | `m-bain/whisperX` | Phoneme-level word alignment for exact subtitle syncing. |
| **Asset Generation** | `comfyanonymous/ComfyUI` | Headless API for FLUX.1 image and Wan 2.2 / SVD video generation. |
| **Motion Physics** | `motiondivision/motion` | React animation primitives and layout physics. |
| **Transitions** | `gl-transitions/gl-transitions` | 100+ WebGL shader transitions for Remotion. |
| **Subject Cutout** | `danielgatis/rembg` | Background removal for parallax multi-layer cutouts. |
| **Audio Processing** | `FFmpeg/FFmpeg` | Filtergraph mastering, EBU R128 loudness normalization, and audio ducking. |

---

### 3. Repository Directory Structure

project-chronos/├── backend/│   ├── app/│   │   ├── agents/│   │   │   ├── init.py│   │   │   ├── research_agent.py      # Multi-query grounding & fact extraction│   │   │   ├── script_agent.py        # 5-Act narrative structuring & visual tagging│   │   │   └── supervisor.py          # LangGraph state machine controller│   │   ├── core/│   │   │   ├── config.py              # Environment settings & API keys│   │   │   └── schemas.py             # Pydantic v2 data models│   │   ├── engines/│   │   │   ├── audio_engine.py        # TTS generation + WhisperX forced alignment│   │   │   ├── stock_harvester.py     # Pexels, Pixabay, Wikimedia client│   │   │   ├── comfyui_client.py      # Headless ComfyUI FLUX/Wan 2.2 client│   │   │   ├── map_generator.py       # Static/animated GeoJSON path creator│   │   │   └── sound_master.py        # FFmpeg ducking & loudness filtergraphs│   │   └── main.py                    # FastAPI server & CLI entrypoint│   ├── requirements.txt│   └── Dockerfile├── remotion-engine/│   ├── src/│   │   ├── compositions/│   │   │   └── DocumentaryMaster.tsx  # Main timeline composition│   │   ├── components/│   │   │   ├── KenBurnsCanvas.tsx     # Motion-interpolated image/video layer│   │   │   ├── ParallaxLayer.tsx      # Multi-depth cutout animation│   │   │   ├── MapVisualizer.tsx      # Leaflet / MapLibre path animator│   │   │   ├── KineticCaptions.tsx    # Word-level highlight subtitle system│   │   │   ├── GraphicOverlays.tsx    # Lower thirds, counters, newspaper cutouts│   │   │   └── FilmGrade.tsx          # Vignette, grain shader, letterbox│   │   ├── types/│   │   │   └── schema.ts              # TypeScript mirrors of backend schemas│   │   ├── Root.tsx                   # Remotion registration root│   │   └── index.ts│   ├── package.json│   ├── tsconfig.json│   └── remotion.config.ts├── workspace/                         # Ephemeral runtime data│   ├── assets/│   ├── cache/│   └── output/├── .env.example└── README.md
---

### 4. Unified Data Schema Specification

#### 4.1. Scene Specification Schema (`schemas.py` & `schema.ts`)
```json
{
  "$schema": "[http://json-schema.org/draft-07/schema#](http://json-schema.org/draft-07/schema#)",
  "title": "ProjectChronosManifest",
  "type": "object",
  "required": ["project_id", "title", "metadata", "scenes", "audio_tracks"],
  "properties": {
    "project_id": {"type": "string"},
    "title": {"type": "string"},
    "metadata": {
      "type": "object",
      "properties": {
        "width": {"type": "integer", "default": 1920},
        "height": {"type": "integer", "default": 1080},
        "fps": {"type": "integer", "default": 60},
        "total_frames": {"type": "integer"}
      },
      "required": ["width", "height", "fps", "total_frames"]
    },
    "scenes": {
      "type": "array",
      "items": {
        "type": "object",
        "required": [
          "scene_id", "act_type", "start_frame", "duration_in_frames", 
          "voiceover", "visual_asset", "captions"
        ],
        "properties": {
          "scene_id": {"type": "string"},
          "act_type": {
            "type": "string",
            "enum": ["HOOK", "CONTEXT", "CONFLICT", "CLIMAX", "OUTRO"]
          },
          "start_frame": {"type": "integer"},
          "duration_in_frames": {"type": "integer"},
          "voiceover": {
            "type": "object",
            "required": ["audio_path", "duration_seconds"],
            "properties": {
              "audio_path": {"type": "string"},
              "duration_seconds": {"type": "number"}
            }
          },
          "visual_asset": {
            "type": "object",
            "required": ["source_type", "asset_uri", "motion_preset"],
            "properties": {
              "source_type": {
                "type": "string", 
                "enum": ["STOCK_VIDEO", "STOCK_IMAGE", "AI_GENERATED", "MAP_ANIMATION", "GRAPHIC_OVERLAY"]
              },
              "asset_uri": {"type": "string"},
              "fallback_prompt": {"type": "string"},
              "motion_preset": {
                "type": "string",
                "enum": ["KEN_BURNS_ZOOM_IN", "KEN_BURNS_ZOOM_OUT", "PARALLAX_DRIFT", "STATIC"]
              },
              "overlay_spec": {
                "type": "object",
                "properties": {
                  "type": {"type": "string", "enum": ["MAP", "NEWSPAPER", "STAT_COUNTER", "NONE"]},
                  "data": {"type": "object"}
                }
              }
            }
          },
          "captions": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["word", "start_frame", "end_frame", "is_highlight"],
              "properties": {
                "word": {"type": "string"},
                "start_frame": {"type": "integer"},
                "end_frame": {"type": "integer"},
                "is_highlight": {"type": "boolean"}
              }
            }
          }
        }
      }
    },
    "audio_tracks": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["track_id", "type", "file_path", "start_frame", "volume"],
        "properties": {
          "track_id": {"type": "string"},
          "type": {"type": "string", "enum": ["VOICEOVER", "BGM", "SFX"]},
          "file_path": {"type": "string"},
          "start_frame": {"type": "integer"},
          "duration_frames": {"type": "integer"},
          "volume": {"type": "number", "minimum": 0.0, "maximum": 1.0}
        }
      }
    }
  }
}
5. Detailed Module Implementation SpecsModule 1: Script & Storyboard Planner (script_agent.py)LLM Engine: Gemini 2.5 Flash / DeepSeek R1 via LangGraph with structured JSON validation.Prompt Contract: Must return complete scene specifications with strict timing constraints. Average speaking rate benchmarked at 140–150 words per minute (2.3–2.5 words/second).Scene Segmentation: Every scene must be between 3.0s (180 frames @ 60fps) and 7.5s (450 frames @ 60fps) to ensure documentary retention pacing.Module 2: Audio & Timestamp Engine (audio_engine.py)Synthesis: Uses Kokoro-TTS (local ONNX/PyTorch) generating 24kHz studio-quality mono WAVs.Timestamp Forcing:Pythonimport whisperx

def extract_word_timestamps(audio_path: str, device: str = "cuda") -> list[dict]:
    model = whisperx.load_model("large-v3", device=device, compute_type="float16")
    audio = whisperx.load_audio(audio_path)
    result = model.transcribe(audio, batch_size=16)

    align_model, metadata = whisperx.load_align_model(
        language_code=result["language"], device=device
    )
    aligned_result = whisperx.align(
        result["segments"], align_model, metadata, audio, device=device
    )

    # Extract word objects with exact frame conversions (FPS=60)
    word_segments = []
    for segment in aligned_result["word_segments"]:
        if "start" in segment and "end" in segment:
            word_segments.append({
                "word": segment["word"],
                "start_frame": int(segment["start"] * 60),
                "end_frame": int(segment["end"] * 60),
                "is_highlight": len(segment["word"]) > 6 or segment["word"].isupper()
            })
    return word_segments
Module 3: Dual Asset Sourcing & ComfyUI Fallback (asset_harvester.py)Stock Scraping Logic:Primary: Query Pexels Video API (orientation=landscape, size=large).Secondary: Query Wikimedia Commons / Pixabay API.Validate: Duration $\ge$ Scene Duration, Resolution $\ge 1920 \times 1080$.Generative Fallback (ComfyUI API Integration):If zero stock clips found $\rightarrow$ dispatch headless ComfyUI workflow:CLIPTextEncode: High-detail documentary photography prompt + negative prompt (deformed, text, low quality, cartoon).UNETLoader: FLUX.1-schnell (4 steps, cfg 1.0) $\rightarrow$ Latent Image.VAEDecode $\rightarrow$ 1920x1080 Image.Wan 2.2 / CogVideoX / SVD Node: Generates 81 frames of subtle camera forward motion.Module 4: Remotion Visual Engine (remotion-engine/)Composition Structure (DocumentaryMaster.tsx):TypeScriptimport React from 'react';
import { AbsoluteFill, Sequence, Audio, staticFile } from 'remotion';
import { KenBurnsCanvas } from '../components/KenBurnsCanvas';
import { KineticCaptions } from '../components/KineticCaptions';
import { FilmGrade } from '../components/FilmGrade';
import { ProjectChronosManifest } from '../types/schema';

export const DocumentaryMaster: React.FC<{ manifest: ProjectChronosManifest }> = ({ manifest }) => {
  return (
    <AbsoluteFill '#050505' backgroundColor: style="{{" }}>
      {/* Visual Layer */}
      {manifest.scenes.map((scene) => (
        <Sequence durationInFrames="{scene.duration_in_frames}" from="{scene.start_frame}" key="{scene.scene_id}">
          <KenBurnsCanvas durationInFrames="{scene.duration_in_frames}" motionPreset="{scene.visual_asset.motion_preset}" src="{scene.visual_asset.asset_uri}" type="{scene.visual_asset.source_type}"/>
          <KineticCaptions captions="{scene.captions}" startFrame="{scene.start_frame}"/>
        </Sequence>
      ))}

      {/* Cinematic Master Post-Processing Layer */}
      <FilmGrade filmGrainOpacity="{0.06}" vignetteIntensity="{0.35}"/>

      {/* Master Voiceover Audio */}
      {manifest.scenes.map((scene) => (
        <Sequence durationInFrames="{scene.duration_in_frames}" from="{scene.start_frame}" key="{`audio_${scene.scene_id}`}">
          <Audio src="{staticFile(scene.voiceover.audio_path)}" volume="{1.0}"/>
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
Ken Burns Motion Math (KenBurnsCanvas.tsx):TypeScriptimport { interpolate, useCurrentFrame, Img, Video } from 'remotion';

export const KenBurnsCanvas = ({ src, type, motionPreset, durationInFrames }) => {
  const frame = useCurrentFrame();

  const scale = interpolate(
    frame,
    [0, durationInFrames],
    motionPreset === 'KEN_BURNS_ZOOM_IN' ? [1.0, 1.15] : [1.15, 1.0],
    { extrapolateRight: 'clamp' }
  );

  const translateY = interpolate(
    frame,
    [0, durationInFrames],
    motionPreset === 'KEN_BURNS_ZOOM_IN' ? [0, -20] : [-20, 0],
    { extrapolateRight: 'clamp' }
  );

  const style: React.CSSProperties = {
    width: '100%',
    height: '100%',
    objectFit: 'cover',
    transform: `scale(${scale}) translateY(${translateY}px)`,
  };

  return type === 'STOCK_VIDEO' ? (
    <Video muted src="{src}" style="{style}"/>
  ) : (
    <Img src="{src}" style="{style}"/>
  );
};
Module 5: Audio Mastering & Sidechain Ducking (sound_master.py)Executes an automated FFmpeg filter graph to merge Voiceover (Track 0) and Background Score (Track 1):Bashffmpeg -y \
  -i master_voiceover.wav \
  -i background_music.wav \
  -filter_complex \
  "[1:a]volume=0.45[bg]; \
   [bg][0:a]sidechaincompress=threshold=0.08:ratio=5:attack=15:release=350[ducked_bg]; \
   [ducked_bg][0:a]amix=inputs=2:duration=first:dropout_transition=2[mixed]; \
   [mixed]loudnorm=I=-14:LRA=7:TP=-1.0[master_audio]" \
  -map "[master_audio]" \
  -c:a aac -b:a 320k mastered_soundtrack.m4a
6. Execution Harness CLI InterfaceThe engine is invoked via a unified CLI entry point:Bash# Full automated run from single prompt
python backend/app/main.py build \
  --topic "The Secret Operation that Built India's Nuclear Defense in 1974" \
  --resolution 1080p \
  --fps 60 \
  --enable-ai-fallback \
  --style "gaurav-thakur-documentary" \
  --out ./workspace/output/nuclear_documentary.mp4

---

### Master Instruction Prompt for Your AI Coding Agent

Pass this prompt to your agent (Cursor, Claude Code, OpenCode) to start generating the codebase:

```markdown
You are an expert Principal AI Software Architect. Your goal is to build **Project Chronos**, an enterprise-grade, autonomous long-form video engine based on the PRD.md and TRD.md specifications provided above.

### Initial Development Tasks:
1. **Repository Setup:**
   - Scaffold the directory structure separating `/backend` and `/remotion-engine`.
   - Implement `backend/app/core/schemas.py` using Pydantic v2 and create matching TypeScript types in `remotion-engine/src/types/schema.ts`.
2. **Script & Storyboard Agent:**
   - Build `backend/app/agents/script_agent.py` utilizing LangGraph to generate validated multi-act narrative scene ASTs.
3. **Audio & Forced Alignment:**
   - Build `backend/app/engines/audio_engine.py` integrating Kokoro-TTS (or Edge-TTS fallback) and WhisperX for word-level timestamps.
4. **Stock Harvester & Fallback Client:**
   - Build `backend/app/engines/stock_harvester.py` (Pexels/Pixabay API adapters) and `backend/app/engines/comfyui_client.py` for headless image/video generation.
5. **Remotion Composition:**
   - Implement `KenBurnsCanvas.tsx`, `KineticCaptions.tsx`, `FilmGrade.tsx`, and `DocumentaryMaster.tsx`.
6. **FFmpeg Mastering:**
   - Implement `backend/app/engines/sound_master.py` with sidechain ducking and EBU R128 loudness normalization.

Begin step 1 now: create the repository directory layout and implement the core schemas.