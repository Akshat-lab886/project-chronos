/**
 * Project Chronos — Unified TypeScript Schema Definitions
 *
 * These interfaces mirror the Pydantic v2 models defined in
 * `backend/app/core/schemas.py`.  Every field name, enum value, and
 * constraint is kept in lock-step so that the Remotion engine receives
 * fully-typed data from the manifest JSON.
 *
 * Generated: mirrors schemas.py v1.0.0
 */

// ─────────────────────────────────────────────────────────────────────────────
// Enums — mirror the Python Enum classes
// ─────────────────────────────────────────────────────────────────────────────

export enum ActType {
  HOOK = "HOOK",
  CONTEXT = "CONTEXT",
  CONFLICT = "CONFLICT",
  CLIMAX = "CLIMAX",
  OUTRO = "OUTRO",
}

export enum VisualSourceType {
  STOCK_VIDEO = "STOCK_VIDEO",
  STOCK_IMAGE = "STOCK_IMAGE",
  AI_GENERATED = "AI_GENERATED",
  MAP_ANIMATION = "MAP_ANIMATION",
  GRAPHIC_OVERLAY = "GRAPHIC_OVERLAY",
}

export enum MotionPreset {
  KEN_BURNS_ZOOM_IN = "KEN_BURNS_ZOOM_IN",
  KEN_BURNS_ZOOM_OUT = "KEN_BURNS_ZOOM_OUT",
  PARALLAX_DRIFT = "PARALLAX_DRIFT",
  STATIC = "STATIC",
}

export enum OverlayType {
  MAP = "MAP",
  NEWSPAPER = "NEWSPAPER",
  STAT_COUNTER = "STAT_COUNTER",
  NONE = "NONE",
}

export enum AudioTrackType {
  VOICEOVER = "VOICEOVER",
  BGM = "BGM",
  SFX = "SFX",
}

// ─────────────────────────────────────────────────────────────────────────────
// Interfaces — mirror the Pydantic BaseModel classes
// ─────────────────────────────────────────────────────────────────────────────

export interface ProjectMetadata {
  title: string;
  topic: string;
  width: number;
  height: number;
  fps: number;
  total_duration_seconds: number;
  total_frames: number;
  aspect_ratio: number;
  created_at: string; // ISO 8601 datetime string
}

export interface VoiceoverSpec {
  audio_path: string;
  duration_seconds: number;
  sample_rate: number;
  voice_id: string;
  word_count: number;
  speaker_wpm: number;
}

export interface CaptionWord {
  word: string;
  start_frame: number;
  end_frame: number;
  is_highlight: boolean;
  confidence: number;
}

export interface OverlaySpec {
  type: OverlayType;
  data: Record<string, unknown>;
}

export interface VisualAssetSpec {
  source_type: VisualSourceType;
  asset_uri: string;
  fallback_prompt: string;
  motion_preset: MotionPreset;
  width: number;
  height: number;
  duration_frames: number;
  overlay_spec: OverlaySpec;
  license_info: string;
  attribution: string;
  match_score: number;
}

export interface SceneSpec {
  scene_id: string;
  act_type: ActType;
  start_frame: number;
  duration_frames: number;
  duration_seconds: number;
  title: string;
  narrative: string;
  visual_tags: string[];
  search_queries: string[];
  visual_asset: VisualAssetSpec;
  voiceover: VoiceoverSpec;
  captions: CaptionWord[];
}

export interface AudioTrackSpec {
  track_id: string;
  type: AudioTrackType;
  file_path: string;
  start_frame: number;
  duration_frames: number;
  volume: number;
  pan: "mono" | "stereo" | "5.1";
  effects: string[];
}

export interface SfxTrigger {
  sfx_id: string;
  frame: number;
  duration_frames: number;
  volume: number;
  asset_uri: string;
}

export interface ProjectChronosManifest {
  project_id: string;
  title: string;
  metadata: ProjectMetadata;
  scenes: SceneSpec[];
  audio_tracks: AudioTrackSpec[];
  sfx_triggers: SfxTrigger[];
  version: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Convenience type helpers
// ─────────────────────────────────────────────────────────────────────────────

/**
 * A scene enriched with absolute timing helpers for Remotion composition.
 */
export interface SceneWithTiming extends SceneSpec {
  /** Absolute end frame = start_frame + duration_frames */
  end_frame: number;
  /** Absolute start time in seconds */
  start_time: number;
  /** Absolute end time in seconds */
  end_time: number;
}

/**
 * Helper to convert a ProjectChronosManifest into a list of scenes
 * with pre-computed timing fields for the Remotion timeline.
 */
export function scenesWithTiming(manifest: ProjectChronosManifest): SceneWithTiming[] {
  const fps = manifest.metadata.fps;
  return manifest.scenes.map((scene) => ({
    ...scene,
    end_frame: scene.start_frame + scene.duration_frames,
    start_time: scene.start_frame / fps,
    end_time: (scene.start_frame + scene.duration_frames) / fps,
  }));
}

export default ProjectChronosManifest;
