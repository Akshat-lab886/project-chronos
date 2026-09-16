"""Project Chronos — Unified Pydantic v2 Schema Contract.

This module defines the complete data model tree that flows through every
stage of the video engine: from script generation -> voice synthesis &
alignment -> asset harvesting -> Remotion composition -> audio mastering.

Every field uses strict Pydantic v2 validation so that malformed data is
rejected at the boundary rather than crashing a downstream stage.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════


class ActType(str, Enum):
    """The five-act narrative structure mandated by the PRD."""

    HOOK = "HOOK"
    CONTEXT = "CONTEXT"
    CONFLICT = "CONFLICT"
    CLIMAX = "CLIMAX"
    OUTRO = "OUTRO"


class VisualSourceType(str, Enum):
    """Where a visual asset originated."""

    STOCK_VIDEO = "STOCK_VIDEO"
    STOCK_IMAGE = "STOCK_IMAGE"
    AI_GENERATED = "AI_GENERATED"
    MAP_ANIMATION = "MAP_ANIMATION"
    GRAPHIC_OVERLAY = "GRAPHIC_OVERLAY"


class MotionPreset(str, Enum):
    """Animation applied to a visual asset."""

    KEN_BURNS_ZOOM_IN = "KEN_BURNS_ZOOM_IN"
    KEN_BURNS_ZOOM_OUT = "KEN_BURNS_ZOOM_OUT"
    PARALLAX_DRIFT = "PARALLAX_DRIFT"
    STATIC = "STATIC"


class OverlayType(str, Enum):
    """Graphic overlay directive on top of a scene."""

    MAP = "MAP"
    NEWSPAPER = "NEWSPAPER"
    STAT_COUNTER = "STAT_COUNTER"
    NONE = "NONE"


class AudioTrackType(str, Enum):
    """Type of an audio track in the master audio timeline."""

    VOICEOVER = "VOICEOVER"
    BGM = "BGM"
    SFX = "SFX"


# ════════════════════════════════════════════════════════════════════════
# Nested Models
# ════════════════════════════════════════════════════════════════════════


class ProjectMetadata(BaseModel):
    """High-level video metadata."""

    model_config = ConfigDict(extra="forbid")

    title: str
    topic: str
    width: int = Field(ge=1280, default=1920)
    height: int = Field(ge=720, default=1080)
    fps: int = Field(ge=24, default=60)
    total_duration_seconds: float = Field(ge=480.0, default=600.0)
    total_frames: int = 0
    aspect_ratio: float = 16 / 9
    created_at: datetime = Field(default_factory=datetime.now)

    @field_validator("total_frames", mode="before")
    @classmethod
    def compute_total_frames(cls, v: Any, info) -> Any:
        """Derive total_frames from duration if not provided."""
        if v and v > 0:
            return v
        fps = info.data.get("fps", 60)
        duration = info.data.get("total_duration_seconds", 600.0)
        return int(duration * fps)

    @model_validator(mode="after")
    def validate_aspect_ratio(self) -> "ProjectMetadata":
        """Ensure width/height ratio matches the recorded aspect_ratio."""
        computed = self.width / self.height
        if abs(computed - self.aspect_ratio) > 0.02:
            self.aspect_ratio = computed
        return self


class VoiceoverSpec(BaseModel):
    """Per-scene voiceover specification."""

    model_config = ConfigDict(extra="forbid")

    audio_path: str
    duration_seconds: float = Field(ge=0.0)
    sample_rate: int = Field(ge=8000, default=24000)
    voice_id: str = "default"
    word_count: int = Field(ge=0, default=0)
    speaker_wpm: float = 145.0


class CaptionWord(BaseModel):
    """A single word-level caption with frame-accurate timing."""

    model_config = ConfigDict(extra="forbid")

    word: str
    start_frame: int = Field(ge=0)
    end_frame: int = Field(ge=0)
    is_highlight: bool = False
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)

    @model_validator(mode="after")
    def validate_frame_order(self) -> "CaptionWord":
        """Ensure start_frame <= end_frame."""
        if self.start_frame > self.end_frame:
            raise ValueError(
                f"start_frame ({self.start_frame}) must be <= "
                f"end_frame ({self.end_frame}) for word '{self.word}'"
            )
        return self


class OverlaySpec(BaseModel):
    """Overlay directive for maps, newspaper cutouts, or stat counters."""

    model_config = ConfigDict(extra="forbid")

    type: OverlayType = OverlayType.NONE
    data: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_overlay_data(self) -> "OverlaySpec":
        """Ensure the data dict has required keys for non-NONE overlays."""
        if self.type == OverlayType.MAP:
            required = {"coordinates"}
            missing = required - set(self.data.keys())
            if missing:
                raise ValueError(f"MAP overlay missing keys: {missing}")
        elif self.type == OverlayType.NEWSPAPER:
            required = {"headline", "source"}
            missing = required - set(self.data.keys())
            if missing:
                raise ValueError(f"NEWSPAPER overlay missing keys: {missing}")
        elif self.type == OverlayType.STAT_COUNTER:
            required = {"label", "start_value", "end_value"}
            missing = required - set(self.data.keys())
            if missing:
                raise ValueError(f"STAT_COUNTER overlay missing keys: {missing}")
        return self


class AssetReview(BaseModel):
    """Quality review result for a visual asset."""

    valid: bool
    issues: list[str] = Field(default_factory=list)
    score: float = Field(ge=0.0, le=1.0, default=0.0)
    dimensions: tuple[int, int] = (0, 0)
    mean_brightness: float = 0.0
    std_deviation: float = 0.0


class VisualAssetSpec(BaseModel):
    """Specification for a single visual asset within a scene."""

    model_config = ConfigDict(extra="forbid")

    source_type: VisualSourceType
    asset_uri: str
    fallback_prompt: str = ""
    motion_preset: MotionPreset = MotionPreset.KEN_BURNS_ZOOM_IN
    width: int = 1920
    height: int = 1080
    duration_frames: int = 0
    overlay_spec: OverlaySpec = Field(
        default_factory=lambda: OverlaySpec(type=OverlayType.NONE)
    )
    license_info: str = ""
    attribution: str = ""
    match_score: float = Field(ge=0.0, le=100.0, default=0.0)


class SceneSpec(BaseModel):
    """A single scene in the documentary timeline."""

    model_config = ConfigDict(extra="forbid")

    scene_id: str
    act_type: ActType
    start_frame: int = Field(ge=0)
    duration_frames: int = Field(ge=180, le=2700)  # 3.0s to 45.0s @ 60fps
    duration_seconds: float = 0.0
    title: str = ""
    narrative: str = ""
    visual_tags: list[str] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    visual_asset: VisualAssetSpec
    voiceover: VoiceoverSpec
    captions: list[CaptionWord] = Field(default_factory=list)

    @model_validator(mode="after")
    def compute_duration(self) -> "SceneSpec":
        """Derive duration_seconds from duration_frames and default fps."""
        self.duration_seconds = round(self.duration_frames / 60.0, 3)
        return self

    @model_validator(mode="after")
    def validate_captions_within_scene(self) -> "SceneSpec":
        """Ensure all caption words fall within the scene's frame span."""
        for cap in self.captions:
            if cap.end_frame > self.duration_frames:
                cap.end_frame = self.duration_frames
        return self


class AudioTrackSpec(BaseModel):
    """A single audio track in the master audio timeline."""

    model_config = ConfigDict(extra="forbid")

    track_id: str
    type: AudioTrackType
    file_path: str
    start_frame: int = Field(ge=0)
    duration_frames: int = Field(ge=0)
    volume: float = Field(ge=0.0, le=1.0, default=1.0)
    pan: str = "stereo"
    effects: list[str] = Field(default_factory=list)


class SfxTrigger(BaseModel):
    """A sound-effect trigger at a specific frame boundary."""

    model_config = ConfigDict(extra="forbid")

    sfx_id: str
    frame: int = Field(ge=0)
    duration_frames: int = 90
    volume: float = Field(ge=0.0, le=1.0, default=0.7)
    asset_uri: str = ""


class ProjectChronosManifest(BaseModel):
    """Root-level project manifest — the single source of truth.

    The entire LangGraph -> Remotion pipeline operates on an instance of
    this model serialised to JSON.
    """

    model_config = ConfigDict(extra="forbid")

    project_id: str
    title: str
    metadata: ProjectMetadata
    scenes: list[SceneSpec] = Field(min_length=5, max_length=15)
    audio_tracks: list[AudioTrackSpec] = Field(default_factory=list)
    sfx_triggers: list[SfxTrigger] = Field(default_factory=list)
    version: str = "1.0.0"

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, v: str) -> str:
        """Ensure project_id is a safe identifier."""
        if not v or not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("project_id must be alphanumeric with dashes/underscores only")
        return v

    @model_validator(mode="after")
    def validate_scene_continuity(self) -> "ProjectChronosManifest":
        """Ensure scenes are contiguous."""
        for i in range(len(self.scenes) - 1):
            scene = self.scenes[i]
            next_scene = self.scenes[i + 1]
            expected_start = scene.start_frame + scene.duration_frames
            if next_scene.start_frame != expected_start:
                raise ValueError(
                    f"Scene {scene.scene_id} ends at frame {expected_start} "
                    f"but scene {next_scene.scene_id} starts at "
                    f"{next_scene.start_frame}"
                )
        return self

    @model_validator(mode="after")
    def validate_act_sequence(self) -> "ProjectChronosManifest":
        """Ensure acts appear in canonical order."""
        expected_sequence = [
            ActType.HOOK, ActType.CONTEXT, ActType.CONFLICT,
            ActType.CLIMAX, ActType.OUTRO,
        ]
        actual = [s.act_type for s in self.scenes]
        for expected_act in expected_sequence:
            if expected_act not in actual:
                raise ValueError(f"Missing required act: {expected_act}")
        indices = {act: actual.index(act) for act in expected_sequence}
        for i in range(len(expected_sequence) - 1):
            if indices[expected_sequence[i]] > indices[expected_sequence[i + 1]]:
                raise ValueError(
                    f"Acts out of order: {expected_sequence[i]} appears "
                    f"after {expected_sequence[i + 1]}"
                )
        return self

    @model_validator(mode="after")
    def validate_total_frames(self) -> "ProjectChronosManifest":
        """Ensure metadata.total_frames covers the last scene."""
        if self.scenes:
            last_scene = self.scenes[-1]
            total = last_scene.start_frame + last_scene.duration_frames
            if total > self.metadata.total_frames:
                self.metadata.total_frames = total
        return self

    def to_json(self, path: str | Path) -> None:
        """Serialise the manifest to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2, exclude_none=True))

    @classmethod
    def from_json(cls, path: str | Path) -> "ProjectChronosManifest":
        """Deserialise a manifest from a JSON file."""
        path = Path(path)
        return cls.model_validate_json(path.read_text())
