"""Project Chronos - Film Studio & Sound Design Engine.

Implements:
  1. Master Film Grade Shader (letterbox bars, vignette, animated grain)
  2. Procedural Diegetic Foley & Sound Design
  3. Cognitive Retention Script Architecture (pacing rules per scene type)

This module generates post-processing directives that are consumed by
the Remotion composition layer and the audio mastering pipeline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.core.schemas import SceneSpec, ActType, OverlayType
from app.core.config import get_settings

logger = logging.getLogger("chronos.film.studio")

# ── Constants ──
TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080

# Cinematic aspect ratios
ASPECT_235 = (2.35, 1.0)
ASPECT_239 = (2.39, 1.0)
ASPECT_169 = (16, 9)
ASPECT_43 = (4, 3)


@dataclass
class FilmGradeSpec:
    """Post-processing directives for a scene."""
    lut: str = "teal-orange"
    vignetteStrength: float = 0.45
    grainIntensity: float = 0.07
    letterboxRatio: str = "2.35:1"
    colorTemperature: str = "neutral"
    contrast: float = 1.1
    saturation: float = 1.05


@dataclass
class SoundDesignSpec:
    """Sound design directives for a scene."""
    bgm_bed: str = "atmospheric_ambient"
    diegetic_sfx: list[dict] = field(default_factory=list)
    audio_timeline: list[dict] = field(default_factory=list)


@dataclass
class PacingProfile:
    """Cognitive retention pacing rules for a scene type."""
    cut_interval_seconds: float = 4.0
    visual_element: str = "Standard pan/zoom"
    audio_rule: str = "Ambient bed with subtle dynamics"
    tension_curve: str = "linear"  # linear, rising, falling, peak
    motion_intensity: str = "moderate"  # subtle, moderate, intense


class CognitiveRetentionArchitect:
    """Implements the cognitive retention script architecture.

    Maps each scene type to specific pacing rules, visual elements,
    and audio triggers to maximize viewer retention.
    """

    PACING_TABLE: dict[ActType, PacingProfile] = {
        ActType.HOOK: PacingProfile(
            cut_interval_seconds=2.0,
            visual_element="Fast montage, high-contrast text flash",
            audio_rule="Tension riser, sudden silence before beat drop",
            tension_curve="rising",
            motion_intensity="intense",
        ),
        ActType.CONTEXT: PacingProfile(
            cut_interval_seconds=5.0,
            visual_element="3D Map zoom, archival photo parallax, 2.5D depth",
            audio_rule="Atmospheric ambient bed, low rumble",
            tension_curve="linear",
            motion_intensity="moderate",
        ),
        ActType.CONFLICT: PacingProfile(
            cut_interval_seconds=3.0,
            visual_element="Split screens, dynamic data counters, kinetic text",
            audio_rule="Rhythmic kick, sidechain ducking",
            tension_curve="rising",
            motion_intensity="intense",
        ),
        ActType.CLIMAX: PacingProfile(
            cut_interval_seconds=2.5,
            visual_element="Full-motion AI video, macro zoom-ins, 2.5D parallax",
            audio_rule="Heavy orchestral swell, frequent whoosh hits",
            tension_curve="peak",
            motion_intensity="intense",
        ),
        ActType.OUTRO: PacingProfile(
            cut_interval_seconds=4.0,
            visual_element="Slow fade montage, legacy footage, stat recap",
            audio_rule="Orchestral resolution, gentle fade",
            tension_curve="falling",
            motion_intensity="subtle",
        ),
    }

    def get_pacing_profile(self, act_type: ActType) -> PacingProfile:
        """Get the optimal pacing profile for a given act type."""
        return self.PACING_TABLE.get(act_type, PacingProfile())


class MasterFilmGradeEngine:
    """Generates master film grade shaders and post-processing effects.

    Produces a TypeScript component (MasterFilmGrade.tsx) that applies:
      1. 2.35:1 letterbox bars
      2. Radial vignette for focus
      3. Animated film grain texture
    """

    def __init__(self):
        self.settings = get_settings()
        self.output_dir = Path("workspace/assets/film_grade")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_film_grade_component(self, scene_id: str) -> dict:
        """Generate film grade directives for a scene.

        Returns a FilmGradeSpec with parameters consumed by Remotion.
        """
        settings = self.settings

        # Adjust grading based on act type
        # (scene act_type available via SceneSpec)
        spec = FilmGradeSpec(
            lut="teal-orange",
            vignetteStrength=0.45,
            grainIntensity=0.07,
            letterboxRatio="2.35:1",
            colorTemperature="neutral",
            contrast=1.1,
            saturation=1.05,
        )

        # Save the spec as JSON for Remotion to consume
        import json
        grade_path = self.output_dir / f"{scene_id}_grade.json"
        with open(grade_path, 'w') as f:
            json.dump({
                "lut": spec.lut,
                "vignetteStrength": spec.vignetteStrength,
                "grainIntensity": spec.grainIntensity,
                "letterboxRatio": spec.letterboxRatio,
                "colorTemperature": spec.colorTemperature,
                "contrast": spec.contrast,
                "saturation": spec.saturation,
            }, f, indent=2)

        return {"path": str(grade_path), "spec": spec}


class DiegeticFoleyEngine:
    """Procedural sound design engine.

    Generates diegetic SFX based on:
      1. Location/setting triggers (desert wind, lab hum, archive hiss)
      2. Action triggers (map zoom, date change, stat counter)

    All SFX are generated as silent audio placeholders when actual
    sound files are unavailable, with deterministic timestamps
    for the Remotion composition to consume.
    """

    # Location-based ambient SFX mapping
    LOCATION_AMBIENCE: dict[str, dict] = {
        "laboratory": {
            "bed": "low_hum_electrical",
            "layered_sfx": ["electrical_hum_40hz", "ventilation_whir"],
        },
        "archive": {
            "bed": "vinyl_tape_hiss",
            "layered_sfx": ["paper_rustle", "typewriter_keys"],
        },
        "desert": {
            "bed": "wind_howling",
            "layered_sfx": ["sand_drift", "distant_howl"],
        },
        "facility": {
            "bed": "industrial_ambient",
            "layered_sfx": ["machinery_hum", "metal_creak"],
        },
        "control_room": {
            "bed": "computer_fans",
            "layered_sfx": ["keyboard_clicks", "monitor_beep"],
        },
        "underground": {
            "bed": "dripping_water_echo",
            "layered_sfx": ["concrete_drip", "low_frequency_rumble"],
        },
    }

    # Action trigger SFX mapping
    ACTION_SFX: dict[str, str] = {
        "map_zoom": "sub_bass_boom_40hz",
        "date_change": "film_projector_click",
        "stat_counter": "ratchet_tick_fast",
        "transition": "whoosh_whoosh_soft",
        "reveal": "paper_unfold_newspaper",
        "explosion": "distant_explosion_thump",
        "alert": "radio_static_burst",
        "door": "metal_door_heavy_open",
    }

    def __init__(self):
        self.settings = get_settings()
        self.output_dir = Path("workspace/assets/sfx")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_scene_sfx(self, scene: SceneSpec) -> list[dict]:
        """Generate SFX triggers for a scene based on its metadata.

        Args:
            scene: SceneSpec with visual tags, overlay type, and narrative.

        Returns:
            List of SFX trigger dicts: {frame, sfx_name, type, volume}
        """
        triggers: list[dict] = []
        fps = self.settings.default_fps

        # Extract location keywords from visual tags
        location_keywords = scene.visual_tags or []

        # Map overlay triggers
        if scene.visual_asset.overlay_spec.type == OverlayType.MAP:
            triggers.append({
                "frame": scene.start_frame,
                "sfx_name": self.ACTION_SFX["map_zoom"],
                "type": "diegetic",
                "volume": 0.5,
                "description": "Sub-bass boom on map zoom-in",
            })

        # Newspaper overlay triggers
        if scene.visual_asset.overlay_spec.type == OverlayType.NEWSPAPER:
            triggers.append({
                "frame": scene.start_frame + 60,
                "sfx_name": self.ACTION_SFX["reveal"],
                "type": "diegetic",
                "volume": 0.4,
                "description": "Paper unfold on document reveal",
            })

        # Stat counter triggers
        if scene.visual_asset.overlay_spec.type == OverlayType.STAT_COUNTER:
            # Tick at regular intervals during the scene
            scene_duration = scene.duration_frames
            tick_interval = max(fps * 2, 30)  # Every 2 seconds minimum
            for t in range(scene.start_frame + 30, scene.start_frame + scene_duration, tick_interval):
                triggers.append({
                    "frame": t,
                    "sfx_name": self.ACTION_SFX["stat_counter"],
                    "type": "diegetic",
                    "volume": 0.25,
                    "description": "Ratchet tick for stat counter",
                })

        # Location-based ambient bed
        sfx_bed = "atmospheric_ambient"
        for keyword in location_keywords:
            keyword_lower = keyword.lower()
            for location, props in self.LOCATION_AMBIENCE.items():
                if location in keyword_lower or keyword_lower in location:
                    sfx_bed = props["bed"]
                    break

        # Add ambient bed trigger at scene start
        triggers.append({
            "frame": scene.start_frame,
            "sfx_name": sfx_bed,
            "type": "ambient",
            "volume": 0.3,
            "description": f"Ambient bed: {sfx_bed}",
        })

        # Add transition SFX at scene end
        triggers.append({
            "frame": scene.start_frame + scene.duration_frames - 30,
            "sfx_name": self.ACTION_SFX["transition"],
            "type": "transition",
            "volume": 0.35,
            "description": "Scene transition whoosh",
        })

        logger.info(f"Generated {len(triggers)} SFX triggers for {scene.scene_id}")
        return triggers

    def generate_bgm_suggestion(self, act_type: ActType) -> dict:
        """Suggest BGM style based on act type for the audio mastering pipeline."""
        bgm_map = {
            ActType.HOOK: {"tempo": "fast", "mood": "tense", "genre": "electronic_suspense"},
            ActType.CONTEXT: {"tempo": "slow", "mood": "reflective", "genre": "orchestral_ambient"},
            ActType.CONFLICT: {"tempo": "medium", "mood": "urgent", "genre": "hybrid_thriller"},
            ActType.CLIMAX: {"tempo": "fast", "mood": "intense", "genre": "full_orchestra"},
            ActType.OUTRO: {"tempo": "slow", "mood": "resolved", "genre": "piano_minimal"},
        }
        return bgm_map.get(act_type, {"tempo": "medium", "mood": "neutral", "genre": "neutral"})
