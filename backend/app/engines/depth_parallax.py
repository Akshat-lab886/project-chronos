"""Project Chronos - 2.5D Depth Parallax Engine.

Implements cinematic depth-parallax technique:
  Input Image -> Depth Estimation (Depth-Anything ONNX)
              -> Foreground Extraction (RMBG ONNX)
              -> Background Inpainting (OpenCV-based)
              -> Multiplane rendering with 3D-like parallax

Models are loaded as ONNX for CPU inference.
"""

from __future__ import annotations

import hashlib
import logging
import os
import urllib.request
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger("chronos.depth.parallax")

# Model URLs (ONNX format for CPU inference)
DEPTH_MODEL_URL = "https://huggingface.co/deepseek-ai/Depth-Anything-V2/resolve/main/depth_anything_v2.onnx"
RMBG_MODEL_URL = "https://huggingface.co/akhali47/RMBG-1.4-Onnx/resolve/main/onnx/rmbg14_1024.onnx"

# Input size constants
DEPTH_INPUT_SIZE = 518
RMBG_INPUT_SIZE = 1024

NUM_LAYERS = 3


class DepthParallaxEngine:
    """Generates depth-aware multiplane parallax assets."""

    def __init__(self):
        self.model_cache = Path(os.environ.get(
            "CHRONOS_MODEL_CACHE",
            str(Path("workspace") / "models" / "onnx")
        ))
        self.model_cache.mkdir(parents=True, exist_ok=True)
        self.output_dir = Path("workspace/assets/parallax_layers")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._depth_session = None
        self._rmbg_session = None

    def _load_onnx_session(self, model_name: str, url: str):
        """Download and load an ONNX model, caching it locally."""
        import onnxruntime as ort

        model_path = self.model_cache / model_name
        if not model_path.exists():
            logger.info(f"Downloading {model_name}...")
            try:
                urllib.request.urlretrieve(url, str(model_path))
                logger.info(f"Downloaded {model_name} ({model_path.stat().st_size} bytes)")
            except Exception as e:
                logger.warning(f"Could not download {model_name}: {e}")
                return None

        try:
            session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
            logger.info(f"Loaded ONNX model: {model_name}")
            return session
        except Exception as e:
            logger.warning(f"Could not load ONNX model {model_name}: {e}")
            return None

    @property
    def depth_session(self):
        if self._depth_session is None:
            self._depth_session = self._load_onnx_session("depth_anything_v2.onnx", DEPTH_MODEL_URL)
        return self._depth_session

    @property
    def rmbg_session(self):
        if self._rmbg_session is None:
            self._rmbg_session = self._load_onnx_session("rmbg14_1024.onnx", RMBG_MODEL_URL)
        return self._rmbg_session

    def _estimate_depth(self, image: np.ndarray) -> Optional[np.ndarray]:
        """Estimate depth map using Depth-Anything-V2 ONNX."""
        if self.depth_session is None:
            return self._fallback_depth(image)

        try:
            session = self.depth_session
            input_name = session.get_inputs()[0].name
            h, w = image.shape[:2]
            resized = cv2.resize(image, (DEPTH_INPUT_SIZE, DEPTH_INPUT_SIZE))
            normalized = resized.astype(np.float32) / 255.0
            input_tensor = np.transpose(normalized, (2, 0, 1))[np.newaxis, ...]
            outputs = session.run(None, {input_name: input_tensor})
            depth = outputs[0][0]
            depth = cv2.resize(depth, (w, h))
            depth_min = depth.min()
            depth_max = depth.max()
            if depth_max > depth_min:
                depth = (depth - depth_min) / (depth_max - depth_min)
            return depth.astype(np.float32)
        except Exception as e:
            logger.warning(f"Depth estimation failed: {e}")
            return self._fallback_depth(image)

    def _fallback_depth(self, image: np.ndarray) -> np.ndarray:
        """Simple gradient-based fallback depth estimation."""
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        depth = gray.astype(np.float32) / 255.0
        edges = cv2.Laplacian(gray, cv2.CV_64F)
        edge_map = np.abs(edges) / (np.abs(edges).max() + 1e-8)
        depth = depth * 0.7 + (1.0 - edge_map.astype(np.float32)) * 0.3
        return depth

    def _extract_foreground(self, image: np.ndarray) -> Optional[np.ndarray]:
        """Extract foreground subject with alpha channel using RMBG ONNX."""
        if self.rmbg_session is None:
            return self._fallback_foreground(image)

        try:
            session = self.rmbg_session
            input_name = session.get_inputs()[0].name
            h, w = image.shape[:2]
            resized = cv2.resize(image, (RMBG_INPUT_SIZE, RMBG_INPUT_SIZE))
            normalized = resized.astype(np.float32) / 255.0
            input_tensor = np.transpose(normalized, (2, 0, 1))[np.newaxis, ...]
            outputs = session.run(None, {input_name: input_tensor})
            mask = outputs[0][0, 0]
            mask = cv2.resize(mask, (w, h))
            mask = np.clip(mask, 0, 1)
            rgba = np.dstack([image, (mask * 255).astype(np.uint8)])
            return rgba
        except Exception as e:
            logger.warning(f"Foreground extraction failed: {e}")
            return self._fallback_foreground(image)

    def _fallback_foreground(self, image: np.ndarray) -> np.ndarray:
        """Fallback: use center region as foreground with heuristic alpha."""
        h, w = image.shape[:2]
        yy, xx = np.ogrid[:h, :w]
        center_x, center_y = w / 2, h / 2
        a, b = w * 0.35, h * 0.35
        ellipse = ((xx - center_x) ** 2 / a ** 2 + (yy - center_y) ** 2 / b ** 2) <= 1
        dist = np.sqrt((xx - center_x) ** 2 / a ** 2 + (yy - center_y) ** 2 / b ** 2)
        alpha = np.clip((1.5 - dist), 0, 1) * 255
        alpha = (alpha * ellipse + alpha * 0.3 * ~ellipse).astype(np.uint8)
        rgba = np.dstack([image, alpha])
        return rgba

    def generate_parallax_layers(self, image_path: str, scene_id: str) -> dict:
        """Generate multiplane parallax layers from a single image.

        Returns dict with keys: background, midground, foreground, depth_map, mask
        """
        image = Image.open(image_path).convert("RGB")
        img_array = np.array(image)

        depth_map = self._estimate_depth(img_array)
        foreground_rgba = self._extract_foreground(img_array)

        layers = {}

        # Background layer (inpainted)
        if foreground_rgba is not None:
            mask = foreground_rgba[:, :, 3] / 255.0
            mask_3ch = np.stack([mask, mask, mask], axis=2)
            background_only = img_array * (1 - mask_3ch)
            mask_uint8 = (mask * 255).astype(np.uint8)
            background_inpainted = cv2.inpaint(
                background_only.astype(np.uint8), mask_uint8,
                7, cv2.INPAINT_TELEA,
            )
            bg_path = str(self.output_dir / f"{scene_id}_layer_bg.png")
            Image.fromarray(background_inpainted).save(bg_path)
            layers["background"] = bg_path
        else:
            bg_path = str(self.output_dir / f"{scene_id}_layer_bg.png")
            image.save(bg_path)
            layers["background"] = bg_path

        # Midground layer (subject with alpha)
        if foreground_rgba is not None:
            mid_path = str(self.output_dir / f"{scene_id}_layer_mid.png")
            Image.fromarray(foreground_rgba).save(mid_path)
            layers["midground"] = mid_path

        # Foreground (atmospheric particles)
        fg_layer = self._generate_atmospheric_layer(img_array, depth_map)
        fg_path = str(self.output_dir / f"{scene_id}_layer_fg.png")
        Image.fromarray(fg_layer).save(fg_path)
        layers["foreground"] = fg_path

        # Depth map
        depth_path = str(self.output_dir / f"{scene_id}_depth.png")
        depth_vis = (depth_map * 255).astype(np.uint8)
        Image.fromarray(depth_vis).save(depth_path)
        layers["depth_map"] = depth_path

        # Alpha mask
        if foreground_rgba is not None:
            mask_path = str(self.output_dir / f"{scene_id}_mask.png")
            Image.fromarray(foreground_rgba[:, :, 3]).save(mask_path)
            layers["mask"] = mask_path

        logger.info(f"Generated parallax layers for {scene_id}")
        return layers

    def _generate_atmospheric_layer(self, image: np.ndarray, depth_map) -> np.ndarray:
        """Generate atmospheric particle layer (dust, light rays)."""
        h, w = image.shape[:2]
        seed = int(hashlib.md5(image.tobytes()).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed=seed)
        noise = rng.random((h, w)).astype(np.float32) * 0.3

        if depth_map is not None:
            haze = 1.0 - depth_map
            noise += haze * 0.2

        noise_small = cv2.resize(noise, (w // 4, h // 4))
        noise_small = cv2.GaussianBlur(noise_small, (9, 9), 3)
        noise_full = cv2.resize(noise_small, (w, h))

        warm = np.zeros((h, w, 3), dtype=np.float32)
        warm[:, :, 0] = noise_full * 0.1
        warm[:, :, 1] = noise_full * 0.08
        warm[:, :, 2] = noise_full * 0.05

        alpha = np.clip(noise_full * 0.3, 0, 0.2) * 255
        rgba = np.dstack([warm * 255, alpha]).astype(np.uint8)
        return rgba
