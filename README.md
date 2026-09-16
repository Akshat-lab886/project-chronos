# Project Chronos — Autonomous Documentary Video Engine

An enterprise-grade, fully autonomous long-form video engine that transforms a single topic prompt into an 8–15 minute, minimum 1080p60 cinematic documentary video.

**Visual Quality Benchmark:** Matches the aesthetic caliber of Gaurav Thakur (GetSetFly), Johnny Harris, and Vox.

## Quick Start

```bash
# Full pipeline build (generates script, voice, assets, and manifest)
cd backend
python -m app.main build \
    --topic "The Secret Operation that Built India's Nuclear Defense in 1974" \
    --resolution 1080p \
    --fps 60 \
    --out ./workspace/output/master.mp4

# Skip voice synthesis (faster, uses estimated timings)
python -m app.main build --topic "..." --skip-audio

# Generate manifest only (no assets or audio)
python -m app.main build --topic "..." --manifest-only

# Check environment
python -m app.main doctor

# List available visual styles
python -m app.main list-styles

# Run as FastAPI server
python -m app.main serve
```

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    User CLI / API                       │
└──────────┬──────────────────────────────────────────────┘
           ▼
┌─────────────────────────────────────────────────────────┐
│         LangGraph Controller (Agent Orchestration)      │
└──────────┬──────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────┐
│  Research Agent    │  Script Agent    │  Voice Engine   │
│  (web research)    │  (5-act script)  │  (Kokoro-TTS)   │
└──────────┬──────────────────────────────────────────────┘
           │    ┌──────────────────────────────────────────┐
           │    │  Stock Harvester   │  ComfyUI Client   │
           │    │  (Pexels/Pixabay)  │  (AI fallback)    │
           │    └─────────┬───────────────────────────────┘
           ▼              ▼
┌─────────────────────────────────────────────────────────┐
│              Project Manifest (JSON)                    │
│        (Pydantic v2 validated schema)                   │
└──────────┬──────────────────────────────────────────────┘
           ▼
┌─────────────────────────────────────────────────────────┐
│     Remotion Video Engine (React/TypeScript)            │
│  - KenBurnsCanvas   - KineticCaptions  - MapVisualizer  │
│  - GraphicOverlays  - FilmGrade         - ParallaxLayer │
└──────────┬──────────────────────────────────────────────┘
           ▼
┌─────────────────────────────────────────────────────────┐
│     FFmpeg Audio Masterer (EBU R128 + Ducking)          │
│  sidechaincompress, loudnorm=I=-14:LRA=7:TP=-1.0       │
└──────────┬──────────────────────────────────────────────┘
           ▼
┌─────────────────────────────────────────────────────────┐
│              Final Master .MP4 (1080p60)                │
└─────────────────────────────────────────────────────────┘
```

## Directory Structure

```
project-chronos/
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   ├── schemas.py          # Pydantic v2 schema contract
│   │   │   └── config.py           # Settings management
│   │   ├── agents/
│   │   │   ├── research_agent.py   # Topic research (LangGraph)
│   │   │   └── script_agent.py     # 5-act script generation
│   │   ├── engines/
│   │   │   ├── audio_engine.py     # TTS + WhisperX alignment
│   │   │   ├── stock_harvester.py  # Pexels/Pixabay/Archive.org
│   │   │   ├── comfyui_client.py   # AI fallback (FLUX.1/Wan 2.2)
│   │   │   └── sound_master.py     # FFmpeg ducking + loudness
│   │   └── main.py                 # FastAPI + Typer CLI
│   ├── requirements.txt
│   └── Dockerfile
├── remotion-engine/
│   ├── src/
│   │   ├── components/
│   │   │   ├── KenBurnsCanvas.tsx
│   │   │   ├── KineticCaptions.tsx
│   │   │   ├── MapVisualizer.tsx
│   │   │   ├── GraphicOverlays.tsx
│   │   │   ├── FilmGrade.tsx
│   │   │   └── ParallaxLayer.tsx
│   │   ├── compositions/
│   │   │   └── DocumentaryMaster.tsx
│   │   ├── types/
│   │   │   └── schema.ts
│   │   ├── Root.tsx
│   │   ├── index.ts
│   │   └── index.css
│   ├── package.json
│   ├── tsconfig.json
│   └── remotion.config.ts
├── workspace/
│   ├── assets/                     # Generated assets
│   ├── cache/                      # Manifest cache
│   └── output/                     # Final renders
├── .env.example
├── PRD.md
└── TRD.md
```

## Schema Contract

The entire pipeline operates on a `ProjectChronosManifest` JSON object defined in `backend/app/core/schemas.py` (Python Pydantic v2) and mirrored in `remotion-engine/src/types/schema.ts` (TypeScript).

### Key Models

- **ProjectChronosManifest**: Root-level project manifest
- **SceneSpec**: A single scene with visual tags, search queries, and overlay directives
- **CaptionWord**: Word-level timestamp with highlight flag
- **VisualAssetSpec**: Asset metadata (source, resolution, motion, overlay)
- **VoiceoverSpec**: Audio track specification
- **AudioTrackSpec**: Positioned audio track in the master timeline
- **SfxTrigger**: Sound effect trigger at a specific frame

## Narrative Structure

The ScriptAgent decomposes any topic into 5 structured acts:

1. **HOOK (0:00–0:45)**: High-tension cold open with paradoxical question
2. **CONTEXT (0:45–3:00)**: Historical backdrop, key figures, map zoom-ins
3. **CONFLICT (3:00–6:00)**: Rising tensions, escalating challenges
4. **CLIMAX (6:00–9:00)**: Critical revelations, high-intensity moments
5. **OUTRO (9:00–12:00)**: Synthesis, legacy, takeaways

Each scene uses templates calibrated to 145 WPM speaking rate, with scene durations of 3–45 seconds (45s max for 60fps).

## Visual Standards

- **Never a Static Frame**: Every visual uses Ken Burns multi-axis motion, 2.5D parallax cutouts, or film grain/LUT shaders
- **3–7.5s scene cuts** with dynamic retention curves
- **Kinetic typography** with gold/cyan active-word highlight
- **Animated maps, newspaper cutouts, and stat counters** for data visualization
- **Cinematic LUT grading** with film grain and vignette

## Audio Standards

- Center-channel neural voiceover (Kokoro-TTS)
- -18dB sidechain ducking under background music
- Transitional SFX (whooshes, hits, vinyl crackles)
- EBU R128 normalization to -14 LUFS ±1.0
- -1.0 dBFS true peak ceiling

## Fallback Chain

The engine is designed to work without any external services:

| Component | Primary | Fallback 1 | Fallback 2 | Fallback 3 |
|-----------|---------|------------|------------|------------|
| TTS | Kokoro-TTS | Edge-TTS | pyttsx3 | SilentAudioEngine |
| Alignment | WhisperX | faster-whisper | EstimatedAligner | — |
| Stock Assets | Pexels API | Pixabay API | Archive.org | ComfyUI |
| ComfyUI | Local server | — | — | PIL placeholder |

## Environment Setup

```bash
# Copy the example env
cp .env.example .env

# Backend dependencies
cd backend
pip install -r requirements.txt

# Remotion engine dependencies
cd ../remotion-engine
npm install  # or: pnpm install
```

### Required API Keys (optional)

- `PEXELS_API_KEY`: Pexels stock footage API
- `PIXABAY_API_KEY`: Pixabay stock footage API
- `GEMINI_API_KEY` or `OPENAI_API_KEY`: For richer research/script generation
- `HF_TOKEN`: For WhisperX/faster-whisper model downloads

### Optional Services

- Ollama (`OLLAMA_BASE_URL`): Local LLM for research and scripting
- ComfyUI (`COMFYUI_BASE_URL`): Local AI image/video generation
