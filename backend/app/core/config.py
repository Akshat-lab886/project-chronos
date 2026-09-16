"""Centralized configuration for Project Chronos.

All settings are sourced from environment variables with sensible
defaults so the engine can boot without a fully populated .env file.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Paths ──
    workspace_dir: Path = Path("./workspace")
    assets_dir: Path = Path("./workspace/assets")
    cache_dir: Path = Path("./workspace/cache")
    output_dir: Path = Path("./workspace/output")

    # ── LLM / Orchestration ──
    llm_provider: str = "ollama"
    gemini_api_key: str = ""
    openai_api_key: str = ""
    deepseek_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # ── External APIs ──
    pexels_api_key: str = ""
    pixabay_api_key: str = ""

    # ── Audio ──
    tts_model: str = "kokoro"
    tts_voice: str = "default"
    whisper_model_size: str = "tiny"
    whisper_device: str = "cpu"
    default_fps: int = 60

    # ── ComfyUI ──
    comfyui_base_url: str = "http://127.0.0.1:8188"
    comfyui_enabled: bool = False

    # ── FFmpeg ──
    ffmpeg_threads: int = 4

    # ── Render ──
    target_lufs: float = -14.0
    true_peak: float = -1.0
    lra_target: float = 7.0

    def ensure_directories(self) -> None:
        for d in (self.workspace_dir, self.assets_dir, self.cache_dir, self.output_dir):
            d.mkdir(parents=True, exist_ok=True)

        # Set HuggingFace cache to workspace-writable path
        hf_cache = self.workspace_dir / "models" / "hf_cache"
        hf_cache.mkdir(parents=True, exist_ok=True)
        import os
        os.environ.setdefault("HF_HOME", str(hf_cache))
        os.environ.setdefault("TRANSFORMERS_CACHE", str(hf_cache))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
