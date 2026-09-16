# Product Requirement Document (PRD)
## Project Name: Project Chronos — Autonomous Documentary Video Engine
**Document Version:** 1.2.0 | **Target Output:** 1080p60 / 4K UHD Broadcast Quality

---

### 1. Executive Summary & Vision
Project Chronos is an autonomous, agentic long-form video engine. It transforms a single premise or topic into an 8–15 minute cinematic documentary video (matching the aesthetic caliber of Gaurav Thakur / GetSetFly, Johnny Harris, and Vox).

The platform handles end-to-end production: investigative multi-source research, multi-act narrative scriptwriting, studio-grade neural voice synthesis, dynamic b-roll harvesting (royalty-free stock first, local AI generative fallback), 2D/3D map animations, kinetic motion graphics, automated word-synced captions, and audio mastering (EBU R128 loudness normalization and sidechain music ducking).

---

### 2. Market & Aesthetic Benchmark: "The Gaurav Thakur Style"
To achieve the target aesthetic, the engine must satisfy these core visual and pacing elements:
1. **Hook & Narrative Retention Structure:** 30-second cold open with high-tension framing, followed by thematic chapters (5–7 acts).
2. **Layered Visual Canvas:** Never show a static image. Every asset must have multi-axis Ken Burns easing, 2.5D parallax cutout depth, or film grain/LUT grading.
3. **Cartographic & Data Visualizations:** Contextual 2D/3D map route animations, newspaper headline cutouts, and dynamic statistics counters whenever numbers or locations are cited.
4. **Kinetic Typography:** Active-word highlighted captions with gold/cyan accents and spring-physics entry transitions.
5. **Multi-Track Audio Engineering:** Voiceover isolated on center channel, dynamic background music ducked automatically during speech, punctuated by tactile sound effects (whooshes, vinyl crackles, camera shutters, bass drops).

---

### 3. User Personas & Core Workflows

#### 3.1. Personas
* **Autonomous Content Creator:** Wants full zero-touch automation from topic prompt to final MP4 upload.
* **Creative Director (HITL Mode):** Wants automated generation with checkpoint reviews (approving script outline, reviewing storyboard thumbnails, tweaking AI fallback prompts before rendering).

#### 3.2. Core User Journey
[User Input: Topic Prompt]
│
▼
[Phase 1: Research & Storyboard Generation] ──► (Optional HITL Approval)
│
▼
[Phase 2: Voice Synthesis & Forced Alignment]
│
▼
[Phase 3: Visual Sourcing & Fallback Generation] ──► (Stock Match or AI Generation)
│
▼
[Phase 4: Programmatic Video Assembly (Remotion)]
│
▼
[Phase 5: Audio Mastering & Headless SSR Render]
│
▼
[Output: 1080p60/4K Master MP4 + Chapters + Metadata]


---

### 4. Functional Specifications

#### 4.1. Module 1: Investigative Research & Multi-Act Script Engine
* **Context Grounding:** The system conducts web research, extracting historical records, timeline markers, geographical coordinates, and statistical data.
* **Narrative Pacing Framework:** Automatically structures content into:
  - `Act 0: The Cold Hook (0:00–0:45)` — High stakes, paradoxical question, fast cuts.
  - `Act 1: The Context & Origin (0:45–3:00)` — Historical backdrop, map zoom-in.
  - `Act 2: The Rising Tension (3:00–6:00)` — The core conflict/mystery, data breakdown.
  - `Act 3: The Climax / Turning Point (6:00–9:00)` — Critical revelations, high-intensity B-roll.
  - `Act 4: The Epilogue & Takeaway (9:00–12:00)` — Synthesis, future implications, call-to-action.
* **Structured Output:** Produces a validated JSON AST (Abstract Syntax Tree) where each scene contains exact visual cues, overlay directives (e.g., `MAP`, `NEWSPAPER_CUTOUT`, `STAT_COUNTER`), and search keywords.

#### 4.2. Module 2: Voiceover & Timestamp Alignment
* **Neural Speech Generation:** Produces high-fidelity, emotion-aware voiceovers.
* **Sub-Millisecond Alignment:** Runs forced-alignment transcription to generate word-level timestamp boundaries (`start_time`, `end_time`, `phoneme_confidence`) required for synchronized video cutting and kinetic subtitles.

#### 4.3. Module 3: Dual-Engine Asset Harvester & Fallback Pipeline
* **Tier 1 (Public Domain & Stock APIs):** Searches Pexels, Pixabay, Wikimedia Commons, and Internet Archive. Filters for resolution $\ge$ 1080p, aspect ratio 16:9, and visual relevance score $\ge 85\%$.
* **Tier 2 (Synthetic Generation Fallback):** If stock assets are missing or relevance score < 85%, triggers ComfyUI to synthesize high-resolution footage (FLUX.1 for photorealistic images + Wan 2.2 / SVD / LTX-Video for motion animation).
* **Tier 3 (Automated Vector & Map Overlays):** If coordinates or statistics are flagged in the scene, generates animated SVG maps or charts instead of standard stock footage.

#### 4.4. Module 4: Programmatic Composition & Motion Graphics
* Rendered entirely via **Remotion (React/TypeScript)** with frame-accurate precision.
* **Component Library Requirements:**
  - `KenBurnsCanvas`: Smooth zoom-in, zoom-out, and continuous drift interpolations.
  - `ParallaxCutout`: Subject extraction (rembg) separated from background with independent velocity motion.
  - `GeoMapAnimator`: Smooth camera pan and zoom across geographic coordinates with glowing route lines and location pins.
  - `NewspaperHighlighter`: Archival document overlay with animated yellow marker highlight effects.
  - `KineticSubtitles`: High-contrast, drop-shadowed captions with dynamic active-word color fill.
  - `DocumentaryEffects`: LUT color grading, subtle film grain, letterboxing (2.35:1 or 16:9), and vignette.

#### 4.5. Module 5: Audio Engineering & Mastering
* **Sound Effect (SFX) Insertion:** Automatically inserts transitional SFX (swoosh, paper slide, riser, impact hit) at scene boundaries and graphic triggers.
* **Sidechain Compression (Ducking):** Dynamic reduction of background music volume by -16dB to -20dB whenever voiceover audio is active.
* **Mastering Compliance:** Final audio normalized to **-14 LUFS ($\pm 1.0$)** with a true peak ceiling of **-1.0 dBFS** (YouTube/Broadcast standard).

---

### 5. Non-Functional Requirements & SLAs
* **Resolution & Framerate:** 1920x1080 @ 60fps baseline; 3840x2160 (4K) configurable.
* **Encoding Standard:** H.264 / HEVC / ProRes 422 HQ; Audio AAC 320kbps 48kHz.
* **Render Throughput:** Maximum 1.5x real-time render latency on dedicated GPU hardware (e.g., 10-minute video renders in $\le$ 15 minutes).
* **Fault Tolerance:** Distributed worker model with step-level checkpointing and retry logic (exponential backoff).
* **Copyright Cleanliness:** All external assets tagged with source URL, license type (CC0, Pexels License, Public Domain), and stored in an audit log.