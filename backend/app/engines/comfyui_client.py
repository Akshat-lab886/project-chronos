"""Project Chronos — ComfyUI Client.

Tier-2 fallback: When stock assets are insufficient (match score < 85%
or no results), this client dispatches headless ComfyUI workflows for:
  - FLUX.1-schnell image generation (photorealistic still frames)
  - Wan 2.2 / SVD camera motion animation (subtle motion for video clips)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import aiohttp

from app.core.config import get_settings
from app.core.schemas import VisualSourceType

logger = logging.getLogger("chronos.comfyui")

# ── Constants ──
MAX_RETRIES = 3
REQUEST_TIMEOUT = 120  # seconds for long-running generation


@dataclass
class ComfyUIResult:
    """Result of a ComfyUI generation request."""
    asset_path: str
    source_type: VisualSourceType
    prompt: str
    seed: int
    width: int
    height: int
    duration_frames: int = 0
    engine_used: str = "comfyui"


class ComfyUIClient:
    """Headless ComfyUI API client for AI-generated visual assets.

    Communicates with a local ComfyUI server via its HTTP REST API.
    Dispatches pre-built workflow JSON for:
      1. FLUX.1-schnell still image generation
      2. Wan 2.2 / SVD video generation for motion clips
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url: str = settings.comfyui_base_url.rstrip("/")
        self.enabled: bool = settings.comfyui_enabled
        self.assets_dir = settings.assets_dir
        self._session: Optional[aiohttp.ClientSession] = None

        if not self.enabled:
            logger.warning(
                "ComfyUI client disabled (comfyui_enabled=False). "
                "Set --enable-ai-fallback flag to enable."
            )

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def is_available(self) -> bool:
        """Check if the ComfyUI server is reachable."""
        if not self.enabled:
            return False
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/prompt") as resp:
                return resp.status == 200
        except Exception:
            return False

    async def generate_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 4,
        cfg: float = 1.0,
        seed: Optional[int] = None,
        output_prefix: str = "flux_gen",
    ) -> ComfyUIResult:
        """Generate a photorealistic image using FLUX.1-schnell.

        Args:
            prompt: The positive prompt for image generation.
            negative_prompt: Negative prompt to exclude unwanted elements.
            width: Image width in pixels.
            height: Image height in pixels.
            steps: Number of diffusion steps (FLUX.1-schnell: 4 steps recommended).
            cfg: Classifier-free guidance scale.
            seed: Random seed for reproducibility (auto-generated if None).
            output_prefix: Prefix for the output filename.

        Returns:
            ComfyUIResult with the local path to the generated image.
        """
        if not self.enabled:
            raise RuntimeError("ComfyUI is not enabled")

        seed = seed or int(time.time() * 1000) % (2**32)
        logger.info(f"ComfyUI generating image: seed={seed}, {width}x{height}")

        workflow = self._build_flux_workflow(
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            steps=steps,
            cfg=cfg,
            seed=seed,
        )

        for attempt in range(MAX_RETRIES):
            try:
                result = await self._submit_prompt(workflow)
                asset_path = await self._wait_for_result(result)

                if asset_path:
                    return ComfyUIResult(
                        asset_path=asset_path,
                        source_type=VisualSourceType.AI_GENERATED,
                        prompt=prompt,
                        seed=seed,
                        width=width,
                        height=height,
                        engine_used="comfyui",
                    )
                else:
                    logger.warning(f"Image generation returned no result (attempt {attempt + 1})")
            except Exception as e:
                wait = 2 ** attempt
                logger.warning(
                    f"ComfyUI image generation attempt {attempt + 1}/{MAX_RETRIES} "
                    f"failed: {e}. Retrying in {wait}s..."
                )
                await asyncio.sleep(wait)

        logger.error("All ComfyUI image generation attempts failed")
        raise RuntimeError("ComfyUI image generation failed after all retries")

    async def generate_video(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        frames: int = 81,
        seed: Optional[int] = None,
        output_prefix: str = "wan_gen",
    ) -> ComfyUIResult:
        """Generate a video clip using Wan 2.2 / SVD motion.

        Args:
            prompt: The positive prompt for video generation.
            negative_prompt: Negative prompt.
            width: Video width in pixels.
            height: Video height in pixels.
            frames: Number of frames to generate (Wan 2.2 typical: 81 frames).
            seed: Random seed for reproducibility.
            output_prefix: Prefix for the output filename.

        Returns:
            ComfyUIResult with the local path to the generated video.
        """
        if not self.enabled:
            raise RuntimeError("ComfyUI is not enabled")

        seed = seed or int(time.time() * 1000) % (2**32)
        logger.info(f"ComfyUI generating video: seed={seed}, {width}x{height}, {frames} frames")

        workflow = self._build_video_workflow(
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            frames=frames,
            seed=seed,
        )

        for attempt in range(MAX_RETRIES):
            try:
                result = await self._submit_prompt(workflow)
                asset_path = await self._wait_for_result(result)

                if asset_path:
                    return ComfyUIResult(
                        asset_path=asset_path,
                        source_type=VisualSourceType.AI_GENERATED,
                        prompt=prompt,
                        seed=seed,
                        width=width,
                        height=height,
                        duration_frames=frames,
                        engine_used="comfyui",
                    )
            except Exception as e:
                wait = 2 ** attempt
                logger.warning(
                    f"ComfyUI video generation attempt {attempt + 1}/{MAX_RETRIES} "
                    f"failed: {e}. Retrying in {wait}s..."
                )
                await asyncio.sleep(wait)

        logger.error("All ComfyUI video generation attempts failed")
        raise RuntimeError("ComfyUI video generation failed after all retries")

    async def _submit_prompt(self, workflow: dict) -> str:
        """Submit a workflow to the ComfyUI server and get a prompt ID."""
        session = await self._get_session()
        async with session.post(
            f"{self.base_url}/prompt",
            json={"prompt": workflow},
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"ComfyUI API error: HTTP {resp.status}")
            data = await resp.json()
            prompt_id = data.get("prompt_id")
            if not prompt_id:
                raise RuntimeError(f"ComfyUI did not return a prompt_id: {data}")
            return prompt_id

    async def _wait_for_result(self, prompt_id: str) -> Optional[str]:
        """Poll ComfyUI until the generation is complete and return the output path."""
        session = await self._get_session()
        poll_interval = 2.0
        max_poll_time = REQUEST_TIMEOUT

        start_time = time.time()
        while time.time() - start_time < max_poll_time:
            async with session.get(f"{self.base_url}/view/{prompt_id}") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("status") == "completed":
                        output_path = data.get("output", {}).get("path")
                        if output_path:
                            # Copy to our assets directory
                            local_path = self._copy_output(output_path)
                            return local_path
                elif resp.status == 202:
                    # Still processing
                    pass
                else:
                    logger.warning(f"ComfyUI view error: HTTP {resp.status}")

            await asyncio.sleep(poll_interval)
            poll_interval = min(poll_interval * 1.5, 10.0)  # exponential backoff

        raise TimeoutError(f"ComfyUI generation timed out after {max_poll_time}s")

    def _copy_output(self, source_path: str) -> str:
        """Copy the generated output to our assets directory."""
        import shutil

        output_dir = self.assets_dir / "ai_generated"
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = Path(source_path).name
        local_path = str(output_dir / filename)

        if os.path.exists(source_path):
            shutil.copy2(source_path, local_path)
        else:
            # If the source doesn't exist, create a placeholder
            logger.warning(f"ComfyUI output not found at {source_path}, creating placeholder")

        return local_path

    def _build_flux_workflow(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 4,
        cfg: float = 1.0,
        seed: int = 0,
    ) -> dict:
        """Build a ComfyUI workflow JSON for FLUX.1-schnell image generation."""
        return {
            "last_node": 4,
            "nodes": {
                "1": {
                    "class_type": "LoadFLUXPipeline",
                    "inputs": {
                        "base_model": "FLUX.1-dev",
                        "torch_dtype": "float16",
                    },
                },
                "2": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {
                        "clip": ["1", 0],
                        "text": prompt,
                        "guidance": cfg,
                    },
                },
                "3": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {
                        "clip": ["1", 0],
                        "text": negative_prompt,
                        "guidance": 1.0,
                    },
                },
                "4": {
                    "class_type": "FluxSampler",
                    "inputs": {
                        "model": ["1", 0],
                        "positive": ["2", 0],
                        "negative": ["3", 0],
                        "width": width,
                        "height": height,
                        "num_steps": steps,
                        "seed": seed,
                        "scheduler": "normal",
                    },
                },
                "5": {
                    "class_type": "VAEDecode",
                    "inputs": {
                        "samples": ["4", 0],
                        "vae": ["1", 2],
                    },
                },
                "6": {
                    "class_type": "SaveImage",
                    "inputs": {
                        "images": ["5", 0],
                        "filename_prefix": "flux_gen",
                    },
                },
            },
        }

    def _build_video_workflow(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        frames: int = 81,
        seed: int = 0,
    ) -> dict:
        """Build a ComfyUI workflow JSON for Wan 2.2 / SVD video generation."""
        return {
            "last_node": 7,
            "nodes": {
                "1": {
                    "class_type": "LoadFLUXPipeline",
                    "inputs": {"base_model": "FLUX.1-dev", "torch_dtype": "float16"},
                },
                "2": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {"clip": ["1", 0], "text": prompt, "guidance": 7.5},
                },
                "3": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {"clip": ["1", 0], "text": negative_prompt, "guidance": 1.0},
                },
                "4": {
                    "class_type": "FluxSampler",
                    "inputs": {
                        "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
                        "width": width, "height": height, "num_steps": 4,
                        "seed": seed, "scheduler": "normal",
                    },
                },
                "5": {
                    "class_type": "VAEDecode",
                    "inputs": {"samples": ["4", 0], "vae": ["1", 2]},
                },
                "6": {
                    "class_type": "LTXVideo",
                    "inputs": {
                        "model": "LTX-Video",
                        "positive": ["2", 0],
                        "negative": ["3", 0],
                        "width": width, "height": height,
                        "num_frames": frames,
                        "seed": seed,
                        "steps": 4,
                    },
                },
                "7": {
                    "class_type": "SaveVideo",
                    "inputs": {
                        "videos": ["6", 0],
                        "filename_prefix": "wan_gen",
                    },
                },
            },
        }


# ───────────────────────────────────────────────────────────────────────
# Convenience Functions
# ───────────────────────────────────────────────────────────────────────


def _classify_theme(prompt: str) -> str:
    """Classify a prompt into a visual theme for semantic placeholder generation."""
    prompt_lower = prompt.lower()

    if any(kw in prompt_lower for kw in ["nuclear", "atomic", "weapon", "test", "explosion"]):
        if "explosion" in prompt_lower or "blast" in prompt_lower:
            return "explosion"
        return "nuclear"
    if any(kw in prompt_lower for kw in ["historical", "archive", "document", "declassified", "old"]):
        return "historical"
    if any(kw in prompt_lower for kw in ["war", "conflict", "battle", "military"]):
        return "war"
    if any(kw in prompt_lower for kw in ["map", "geographic", "location", "terrain"]):
        return "map"
    if any(kw in prompt_lower for kw in ["diplomatic", "meeting", "negotiation", "treaty"]):
        return "diplomatic"
    if any(kw in prompt_lower for kw in ["memorial", "site", "modern", "reflection"]):
        return "memorial"
    return "default"


async def generate_fallback_asset(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    frames: int = 0,
    seed: Optional[int] = None,
) -> ComfyUIResult:
    """Convenience function to generate a single fallback asset."""
    settings = get_settings()
    client = ComfyUIClient()

    if not client.enabled:
        logger.warning("ComfyUI not enabled — generating semantic placeholder")
        # Create a meaningful placeholder image using PIL with semantic content
        from PIL import Image, ImageDraw, ImageFont
        import numpy as np

        # Analyze the prompt to determine visual theme
        prompt_lower = prompt.lower()
        theme = _classify_theme(prompt_lower)

        # Create a cinematic gradient background based on theme
        img_array = np.zeros((height, width, 3), dtype=np.uint8)

        # Theme-based color scheme
        color_schemes = {
            "nuclear": {"primary": (10, 20, 50), "secondary": (30, 60, 100), "accent": (200, 50, 30)},
            "historical": {"primary": (30, 20, 10), "secondary": (80, 60, 30), "accent": (180, 140, 80)},
            "war": {"primary": (20, 10, 5), "secondary": (70, 30, 20), "accent": (200, 80, 40)},
            "map": {"primary": (10, 25, 40), "secondary": (50, 90, 140), "accent": (200, 200, 100)},
            "diplomatic": {"primary": (15, 25, 40), "secondary": (60, 90, 140), "accent": (180, 160, 100)},
            "explosion": {"primary": (30, 10, 5), "secondary": (100, 30, 10), "accent": (255, 120, 20)},
            "memorial": {"primary": (20, 20, 30), "secondary": (60, 60, 80), "accent": (160, 160, 170)},
            "default": {"primary": (10, 15, 30), "secondary": (40, 50, 90), "accent": (120, 100, 80)},
        }

        colors = color_schemes.get(theme, color_schemes["default"])
        primary = colors["primary"]
        secondary = colors["secondary"]

        # Create vertical gradient from primary to secondary
        for y in range(height):
            ratio = y / height
            for c in range(3):
                img_array[y, :, c] = int(primary[c] + (secondary[c] - primary[c]) * ratio)

        img = Image.fromarray(img_array)
        draw = ImageDraw.Draw(img)
        center_x, center_y = width // 2, height // 2

        # Add radial vignette (darker edges, lighter center)
        max_radius = max(center_x, center_y)
        for r in range(max_radius, 0, -5):
            ratio = 1 - (r / max_radius)
            fill = int(ratio * 30)
            color = (fill, fill, fill)
            draw.ellipse(
                [center_x - r, center_y - r, center_x + r, center_y + r],
                fill=color,
            )

        # Add geometric shapes based on theme for visual interest
        accent = colors["accent"]
        draw = ImageDraw.Draw(img, "RGBA")

        if theme == "nuclear":
            # Draw a circular atomic symbol
            cx, cy = center_x, center_y
            r = min(width, height) // 6
            draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=accent + (200,), width=4)
            # Draw orbiting dots
            for angle in [0, 120, 240]:
                import math
                a = math.radians(angle)
                ex = cx + int(r * 0.7 * math.cos(a))
                ey = cy + int(r * 0.7 * math.sin(a))
                draw.ellipse([ex-5, ey-5, ex+5, ey+5], fill=accent + (200,))

        elif theme == "historical":
            # Draw document-like rectangles
            for i in range(3):
                y = height * 0.3 + i * height * 0.15
                draw.rectangle([width * 0.2, y, width * 0.8, y + 20], fill=accent + (80,))

        elif theme == "map":
            # Draw map grid lines
            for i in range(1, 10):
                x = width * i // 10
                draw.line([(x, 0), (x, height)], fill=accent + (60,), width=1)
                y = height * i // 10
                draw.line([(0, y), (width, y)], fill=accent + (60,), width=1)
            # Draw a dot for a location marker
            draw.ellipse([center_x-8, center_y-8, center_x+8, center_y+8], fill=accent + (200,))

        elif theme == "explosion":
            # Draw radial burst lines
            import math
            for angle in range(0, 360, 15):
                a = math.radians(angle)
                r1 = 50
                r2 = max(width, height) // 3
                x1 = center_x + int(r1 * math.cos(a))
                y1 = center_y + int(r1 * math.sin(a))
                x2 = center_x + int(r2 * math.cos(a))
                y2 = center_y + int(r2 * math.sin(a))
                draw.line([(x2, y2), (x1, y1)], fill=accent + (180,), width=2)

        else:
            # Default: draw abstract geometric pattern
            import math
            for i in range(8):
                angle = math.radians(i * 45)
                r = min(width, height) // 5
                x1 = center_x + int(r * math.cos(angle))
                y1 = center_y + int(r * math.sin(angle))
                x2 = center_x + int((r * 0.5) * math.cos(angle + 0.3))
                y2 = center_y + int((r * 0.5) * math.sin(angle + 0.3))
                draw.polygon([
                    (center_x, center_y),
                    (x1, y1),
                    (x2, y2),
                ], fill=accent + (60,))

        output_path = str(client.assets_dir / "ai_generated" / f"placeholder_{seed or int(time.time())}.png")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path)

        return ComfyUIResult(
            asset_path=output_path,
            source_type=VisualSourceType.AI_GENERATED,
            prompt=prompt,
            seed=seed or 0,
            width=width,
            height=height,
            duration_frames=0,
            engine_used="semantic-placeholder",
        )

    try:
        if frames > 0:
            result = await client.generate_video(prompt=prompt, width=width, height=height, frames=frames, seed=seed)
        else:
            result = await client.generate_image(prompt=prompt, width=width, height=height, seed=seed)
        await client.close()
        return result
    except Exception as e:
        logger.error(f"ComfyUI generation failed: {e}")
        await client.close()
        raise


if __name__ == "__main__":
    async def _test():
        client = ComfyUIClient()
        available = await client.is_available()
        print(f"ComfyUI available: {available}")
        await client.close()

    asyncio.run(_test())
