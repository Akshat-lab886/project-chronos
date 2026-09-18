"""Project Chronos — Multi-tiered Asset Harvester.

Searches Wikimedia Commons for authentic historical/public domain media first,
falls back to Pexels stock API for atmospheric B-roll, and uses AI-generated
fallbacks (PIL/comfyui) when neither source yields results.

Assets are downloaded into remotion-engine/public/assets/ and written as
relative paths into scene.visual_asset.asset_uri for Remotion staticFile() resolution.
"""
from __future__ import annotations

import logging
import os
import mimetypes
from pathlib import Path
from typing import Optional

import requests

from app.core.config import get_settings
from app.core.schemas import (
    VisualAssetSpec,
    VisualSourceType,
    AssetReview,
)

logger = logging.getLogger("chronos.assets")

# ── Paths ──
REMOTION_PUBLIC_DIR = Path("remotion-engine/public/assets")
REMOTION_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

# Wikimedia Commons API endpoint
WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"

# User-Agent header for Wikimedia API requests
WM_USER_AGENT = "ProjectChronos/1.0 (contact@projectchronos.local)"


class AssetHarvester:
    """Multi-tiered asset harvester using Wikimedia Commons, Pexels, and AI fallback."""

    def __init__(self, pexels_api_key: str = None):
        self.settings = get_settings()
        self.pexels_key = pexels_api_key or self.settings.pexels_api_key
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": WM_USER_AGENT})

    def fetch_wikimedia_image(self, query: str) -> Optional[str]:
        """Search Wikimedia Commons for a public domain historical image.

        Uses the File namespace (ns=6) for proper media search.
        Returns the direct URL to the image file, or None if not found.
        """
        search_terms = query.split()
        search_query = " ".join(search_terms[:5])

        # Step 1: Search the File namespace (ns=6) for matching files
        search_params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": f"{search_query} filetype:bitmap",
            "srnamespace": 6,
            "srlimit": 5,
        }

        try:
            res = self.session.get(WIKIMEDIA_API, params=search_params, timeout=15)
            res.raise_for_status()
            data = res.json()

            search_results = data.get("query", {}).get("search", [])
            if not search_results:
                logger.debug(f"[Wikimedia] No files found for: {search_query}")
                return None

            # Step 2: Get imageinfo (direct file URL) for the first result
            file_title = search_results[0]["title"]

            info_params = {
                "action": "query",
                "format": "json",
                "titles": file_title,
                "prop": "imageinfo",
                "iiprop": "url|mime",
            }
            res2 = self.session.get(WIKIMEDIA_API, params=info_params, timeout=15)
            res2.raise_for_status()
            data2 = res2.json()

            pages = data2.get("query", {}).get("pages", {})
            for page_id, page_data in pages.items():
                image_info = page_data.get("imageinfo", [])
                if not image_info:
                    continue

                direct_url = image_info[0].get("url", "")
                mime = image_info[0].get("mime", "")
                if direct_url and mime.startswith("image/"):
                    # Strip query parameters (utm_source etc) to get clean URL
                    clean_url = direct_url.split("?")[0]
                    # Check if this is a thumbnail (smaller version)
                    # If so, construct the original URL from the upload path
                    # Wikimedia upload URLs: https://upload.wikimedia.org/...
                    if clean_url.startswith("https://upload.wikimedia.org/"):
                        logger.info(f"[Wikimedia] Found image: {clean_url[:80]}...")
                        return clean_url
                    return direct_url
        except requests.exceptions.RequestException as e:
            logger.debug(f"[Wikimedia] Request failed: {e}")
        except Exception as e:
            logger.debug(f"[Wikimedia] Parse failed: {e}")

        return None

    def fetch_wikimedia_video(self, query: str) -> Optional[str]:
        """Search Wikimedia Commons for historical video footage.

        Returns the direct URL to a video file, or None if not found.
        """
        search_query = " ".join(query.split()[:5])

        # Step 1: Search File namespace for video files
        search_params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": f"{search_query}",
            "srnamespace": 6,
            "srlimit": 5,
        }

        try:
            res = self.session.get(WIKIMEDIA_API, params=search_params, timeout=15)
            data = res.json()
            search_results = data.get("query", {}).get("search", [])

            for item in search_results:
                file_title = item.get("title", "")
                # Step 2: Get file info
                info_params = {
                    "action": "query",
                    "format": "json",
                    "titles": file_title,
                    "prop": "imageinfo",
                    "iiprop": "url|mime",
                }
                res2 = self.session.get(WIKIMEDIA_API, params=info_params, timeout=15)
                data2 = res2.json()
                pages = data2.get("query", {}).get("pages", {})

                for page_id, page_data in pages.items():
                    image_info = page_data.get("imageinfo", [])
                    if not image_info:
                        continue
                    direct_url = image_info[0].get("url")
                    mime = image_info[0].get("mime", "")
                    # Accept video formats
                    if direct_url and mime.startswith("video/"):
                        logger.info(f"[Wikimedia] Found video: {direct_url[:80]}...")
                        return direct_url
        except Exception as e:
            logger.debug(f"[Wikimedia video] Failed: {e}")

        return None

    def fetch_pexels_video(self, query: str, width: int = 1920) -> Optional[str]:
        """Search Pexels for atmospheric stock video B-roll.

        Returns the HD video file URL, or None if not found.
        """
        if not self.pexels_key:
            logger.debug("[Pexels] API key not configured")
            return None

        url = "https://api.pexels.com/videos/search"
        params = {
            "query": query,
            "per_page": 3,
            "orientation": "landscape",
            "size": "large",  # 1080p
        }
        headers = {"Authorization": self.pexels_key}

        try:
            res = self.session.get(url, params=params, headers=headers, timeout=15)
            res.raise_for_status()
            data = res.json()

            videos = data.get("videos", [])
            for video in videos:
                files = video.get("video_files", [])
                # Prefer 1080p (1920x1080) stream
                hd_files = [f for f in files if f.get("width", 0) >= 1920]
                if hd_files:
                    return hd_files[0]["link"]
                # Fall back to largest available
                if files:
                    return files[0]["link"]
        except Exception as e:
            logger.debug(f"[Pexels] Request failed: {e}")

        return None

    def fetch_pexels_image(self, query: str) -> Optional[str]:
        """Search Pexels for atmospheric stock imagery.

        Returns the image URL, or None if not found.
        """
        if not self.pexels_key:
            logger.debug("[Pexels] API key not configured")
            return None

        url = "https://api.pexels.com/v1/search"
        params = {
            "query": query,
            "per_page": 3,
            "orientation": "landscape",
            "size": "large",
        }
        headers = {"Authorization": self.pexels_key}

        try:
            res = self.session.get(url, params=params, headers=headers, timeout=15)
            res.raise_for_status()
            data = res.json()

            photos = data.get("photos", [])
            if photos:
                # Return 1920px wide version
                return photos[0].get("src", {}).get("large2x") or photos[0].get("src", {}).get("large")
        except Exception as e:
            logger.debug(f"[Pexels image] Request failed: {e}")

        return None

    def download_asset(self, download_url: str, filename: str) -> Optional[str]:
        """Download a remote asset to remotion-engine/public/assets/.

        Returns the relative path (e.g., 'assets/filename.jpg') suitable for
        use with Remotion's staticFile(), or None on failure.
        """
        # Determine extension from URL (strip query params first)
        clean_url = download_url.split("?")[0]
        url_ext = os.path.splitext(clean_url)[1].lower()
        if url_ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".webm"):
            # Fallback: guess from content-type via HEAD request
            try:
                head_resp = self.session.head(download_url, timeout=10, allow_redirects=True)
                ct = head_resp.headers.get("content-type", "image/jpeg")
                ext = mimetypes.guess_extension(ct) or ".jpg"
            except Exception:
                ext = ".jpg"
        else:
            ext = url_ext

        safe_filename = f"{filename}{ext}"
        output_path = REMOTION_PUBLIC_DIR / safe_filename

        try:
            # Stream download to handle large video files
            r = self.session.get(download_url, stream=True, timeout=30)
            if r.status_code == 200:
                with open(output_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

                file_size = output_path.stat().st_size
                logger.info(
                    f"[Download] {safe_filename}: {file_size / 1024:.0f}KB"
                )
                return f"assets/{safe_filename}"
            else:
                logger.warning(f"[Download] HTTP {r.status_code} for {download_url}")
        except Exception as e:
            logger.warning(f"[Download] Failed for {download_url}: {e}")

        return None

    def harvest_asset_for_scene(
        self,
        scene_id: str,
        search_queries: list[str],
        visual_tags: list[str],
        prefer_video: bool = False,
        width: int = 1920,
        height: int = 1080,
    ) -> Optional[dict]:
        """Harvest an asset for a single scene using multi-tiered fallback.

        Returns dict with keys: asset_uri, source_type, or None if all fail.
        """
        # Build combined search query from search_queries and visual_tags
        search_terms = " ".join(search_queries[:3]) if search_queries else " ".join(visual_tags[:3])
        if not search_terms:
            search_terms = "historical documentary footage"

        # ── Tier 1: Wikimedia Commons (free historical archives) ──
        # Try video first if scene prefers motion
        if prefer_video:
            url = self.fetch_wikimedia_video(search_terms)
            if url:
                uri = self.download_asset(url, f"{scene_id}_archive_video")
                if uri:
                    return {"asset_uri": uri, "source_type": VisualSourceType.STOCK_VIDEO}

        # Try image from Wikimedia
        url = self.fetch_wikimedia_image(search_terms)
        if url:
            uri = self.download_asset(url, scene_id)
            if uri:
                return {"asset_uri": uri, "source_type": VisualSourceType.STOCK_IMAGE}

        # ── Tier 2: Pexels (modern stock B-roll) ──
        if prefer_video:
            url = self.fetch_pexels_video(search_terms, width)
            if url:
                uri = self.download_asset(url, f"{scene_id}_stock_video")
                if uri:
                    return {"asset_uri": uri, "source_type": VisualSourceType.STOCK_VIDEO}

        url = self.fetch_pexels_image(search_terms)
        if url:
            uri = self.download_asset(url, scene_id)
            if uri:
                return {"asset_uri": uri, "source_type": VisualSourceType.STOCK_IMAGE}

        # ── Tier 3: AI fallback (handled externally by ComfyUI/PIL) ──
        logger.debug(f"[{scene_id}] No remote assets found — AI fallback needed")
        return None

    def review_asset(self, asset_uri: str, scene_id: str) -> AssetReview:
        """Run quality review on a downloaded asset.

        Checks:
        1. File exists on disk
        2. Image dimensions >= 1280x720
        3. Visual content present (std > 5.0, not blank)
        4. Color variation and brightness are reasonable
        """
        from PIL import Image
        import numpy as np

        full_path = Path("remotion-engine/public") / asset_uri

        issues = []
        score = 1.0

        if not full_path.exists():
            return AssetReview(
                valid=False,
                issues=["File does not exist"],
                score=0.0,
                dimensions=(0, 0),
                mean_brightness=0.0,
                std_deviation=0.0,
            )

        try:
            img = Image.open(full_path)
            arr = np.array(img)

            h, w = arr.shape[:2]
            if w < 1280 or h < 720:
                issues.append(f"Resolution {w}x{h} below 1280x720 minimum")
                score -= 0.3

            mean_brightness = float(np.mean(arr))
            std_dev = float(np.std(arr))

            if std_dev < 5.0:
                issues.append(f"Image too uniform (std={std_dev:.1f} < 5.0)")
                score -= 0.4

            if mean_brightness < 5.0:
                issues.append("Image too dark (mean < 5)")
                score -= 0.2
            elif mean_brightness > 245:
                issues.append("Image too bright (mean > 245)")
                score -= 0.2

            # Color variation check
            if arr.ndim == 3:
                std_r = np.std(arr[:, :, 0])
                std_g = np.std(arr[:, :, 1])
                std_b = np.std(arr[:, :, 2])
                if std_r < 3.0 and std_g < 3.0 and std_b < 3.0:
                    issues.append("Low color variation")
                    score -= 0.3

            score = max(0.0, min(1.0, score))
            valid = score >= 0.5

            return AssetReview(
                valid=valid,
                issues=issues,
                score=score,
                dimensions=(w, h),
                mean_brightness=mean_brightness,
                std_deviation=std_dev,
            )

        except Exception as e:
            return AssetReview(
                valid=False,
                issues=[f"Failed to process image: {str(e)}"],
                score=0.0,
                dimensions=(0, 0),
                mean_brightness=0.0,
                std_deviation=0.0,
            )

    def close(self):
        """Clean up session."""
        self.session.close()
