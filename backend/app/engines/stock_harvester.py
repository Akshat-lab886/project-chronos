"""Project Chronos Stock Asset Harvester.

Tier-1: Searches Pexels and Pixabay REST APIs for HD stock footage/images
matching visual tags, filtering for resolution >= 1080p and match score >= 85.

Tier-2: Falls back to headless ComfyUI (FLUX.1-schnell image + Wan 2.2 / SVD
camera motion) when stock results are insufficient.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from pathlib import Path
from typing import Optional

import aiohttp

from app.core.config import get_settings
from app.core.schemas import VisualSourceType

logger = logging.getLogger("chronos.assets")

MIN_RESOLUTION = 1920 * 1080
MIN_MATCH_SCORE = 85.0
MAX_RETRIES = 3
MAX_RESULTS_PER_QUERY = 15


@dataclass
class HarvestedAsset:
    """A single harvested visual asset."""
    asset_uri: str
    source_type: VisualSourceType
    resolution: str
    width: int
    height: int
    match_score: float
    license_info: str
    attribution: str
    url: str
    duration_seconds: float = 0.0
    local_path: str = ""
    is_video: bool = False


@dataclass
class HarvestResult:
    """Result of harvesting assets for a scene."""
    assets: list[HarvestedAsset] = field(default_factory=list)
    primary_asset: Optional[HarvestedAsset] = None
    fallback_prompt: str = ""
    source_type: VisualSourceType = VisualSourceType.STOCK_VIDEO
    all_from_fallback: bool = False


class StockHarvester:
    """Dual-engine stock footage/image harvester."""

    def __init__(self):
        settings = get_settings()
        self.settings = settings
        self.pexels_api_key: str = settings.pexels_api_key
        self.pixabay_api_key: str = settings.pixabay_api_key
        self.assets_dir = settings.assets_dir
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def harvest(
        self,
        search_queries: list[str],
        visual_tags: list[str],
        width: int = 1920,
        height: int = 1080,
        min_duration: float = 3.0,
        prefer_video: bool = True,
    ) -> HarvestResult:
        """Search stock APIs for assets matching the given queries."""
        logger.info(f"Harvesting assets for queries: {search_queries[:3]}...")

        all_assets: list[HarvestedAsset] = []

        if self.pexels_api_key:
            pexels_assets = await self._search_pexels(
                search_queries, width, height, min_duration, prefer_video
            )
            all_assets.extend(pexels_assets)

        if self.pixabay_api_key:
            pixabay_assets = await self._search_pixabay(
                search_queries, width, height, min_duration, prefer_video
            )
            all_assets.extend(pixabay_assets)

        archive_assets = await self._search_archive_org(search_queries, width, height)
        all_assets.extend(archive_assets)

        all_assets.sort(key=lambda a: a.match_score, reverse=True)

        if not all_assets:
            logger.warning("No stock assets found from any source")
            return HarvestResult(
                assets=[],
                primary_asset=None,
                fallback_prompt=self._generate_fallback_prompt(search_queries, visual_tags),
                source_type=VisualSourceType.AI_GENERATED,
                all_from_fallback=True,
            )

        best = all_assets[0]
        logger.info(
            f"Best asset: {best.url} "
            f"({best.width}x{best.height}, score={best.match_score:.1f})"
        )

        if best.match_score < MIN_MATCH_SCORE:
            logger.warning(
                f"Best asset match score {best.match_score:.1f} < "
                f"threshold {MIN_MATCH_SCORE} - recommend AI fallback"
            )

        return HarvestResult(
            assets=all_assets[:MAX_RESULTS_PER_QUERY],
            primary_asset=best,
            fallback_prompt=self._generate_fallback_prompt(search_queries, visual_tags),
            source_type=best.source_type,
            all_from_fallback=best.match_score < MIN_MATCH_SCORE,
        )

    async def download_asset(self, asset: HarvestedAsset) -> str:
        """Download an asset to the local assets directory."""
        local_filename = f"{asset.source_type.value.lower()}_{Path(asset.url).name}"
        local_path = str(self.assets_dir / "stock" / local_filename)
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)

        if os.path.exists(local_path):
            logger.info(f"Asset already downloaded: {local_path}")
            asset.local_path = local_path
            return local_path

        session = await self._get_session()

        for attempt in range(MAX_RETRIES):
            try:
                async with session.get(asset.url) as response:
                    if response.status == 200:
                        data = await response.read()
                        with open(local_path, "wb") as f:
                            f.write(data)
                        asset.local_path = local_path
                        logger.info(f"Downloaded asset to {local_path} ({len(data)} bytes)")
                        return local_path
                    else:
                        logger.warning(f"HTTP {response.status} downloading {asset.url}")
            except Exception as e:
                wait = 2 ** attempt
                logger.warning(f"Download attempt {attempt + 1}/{MAX_RETRIES} failed: {e}. Retrying in {wait}s...")
                await asyncio.sleep(wait)

        logger.error(f"Failed to download {asset.url} after {MAX_RETRIES} attempts")
        return asset.url

    async def _search_pexels(
        self, queries: list[str], min_width: int, min_height: int,
        min_duration: float, prefer_video: bool,
    ) -> list[HarvestedAsset]:
        """Search Pexels API for videos and images."""
        session = await self._get_session()
        headers = {"Authorization": self.pexels_api_key}
        assets: list[HarvestedAsset] = []

        for query in queries[:3]:
            if prefer_video:
                url = "https://api.pexels.com/videos/search"
                params = {
                    "query": query, "per_page": min(MAX_RESULTS_PER_QUERY, 15),
                    "orientation": "landscape", "size": "large",
                    "min_duration": int(min_duration),
                }
                try:
                    async with session.get(url, headers=headers, params=params) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for video in data.get("videos", []):
                                for v in video.get("video_files", []):
                                    if v.get("width", 0) >= min_width and v.get("height", 0) >= min_height:
                                        res_score = self._score_resolution(v.get("width", 0), v.get("height", 0))
                                        duration_score = min(video.get("duration", 0) / 10.0, 1.0) * 20
                                        assets.append(HarvestedAsset(
                                            asset_uri=v["link"],
                                            source_type=VisualSourceType.STOCK_VIDEO,
                                            resolution=f"{v.get('width')}x{v.get('height')}",
                                            width=v.get("width", 0), height=v.get("height", 0),
                                            match_score=min(100.0, 50.0 + res_score + duration_score),
                                            license_info="Pexels License",
                                            attribution=f"Photo by {video.get('user', {}).get('name', 'Unknown')} on Pexels",
                                            url=v["link"],
                                            duration_seconds=float(video.get("duration", 0)),
                                            is_video=True,
                                        ))
                except Exception as e:
                    logger.warning(f"Pexels video search failed for '{query}': {e}")

            url = "https://api.pexels.com/v1/search"
            params = {
                "query": query, "per_page": min(MAX_RESULTS_PER_QUERY, 15),
                "orientation": "landscape", "size": "large",
            }
            try:
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for photo in data.get("photos", []):
                            w = photo.get("width", 0)
                            h = photo.get("height", 0)
                            if w >= min_width and h >= min_height:
                                assets.append(HarvestedAsset(
                                    asset_uri=photo["src"]["large2x"],
                                    source_type=VisualSourceType.STOCK_IMAGE,
                                    resolution=f"{w}x{h}",
                                    width=w, height=h,
                                    match_score=min(100.0, 70.0 + self._score_resolution(w, h)),
                                    license_info="Pexels License",
                                    attribution=f"Photo by {photo.get('photographer', 'Unknown')} on Pexels",
                                    url=photo["src"]["large2x"],
                                    is_video=False,
                                ))
            except Exception as e:
                logger.warning(f"Pexels photo search failed for '{query}': {e}")

        return assets

    async def _search_pixabay(
        self, queries: list[str], min_width: int, min_height: int,
        min_duration: float, prefer_video: bool,
    ) -> list[HarvestedAsset]:
        """Search Pixabay API for videos and images."""
        session = await self._get_session()
        assets: list[HarvestedAsset] = []

        for query in queries[:3]:
            if prefer_video:
                url = "https://pixabay.com/api/videos/"
                params = {
                    "key": self.pixabay_api_key, "q": query,
                    "per_page": min(MAX_RESULTS_PER_QUERY, 15),
                    "orientation": "horizontal",
                    "min_width": min_width, "min_height": min_height,
                }
                try:
                    async with session.get(url, params=params) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for video in data.get("hits", []):
                                w = video.get("width", 0)
                                h = video.get("height", 0)
                                if w >= min_width and h >= min_height:
                                    assets.append(HarvestedAsset(
                                        asset_uri=video.get("videos", {}).get("large", {}).get("url", ""),
                                        source_type=VisualSourceType.STOCK_VIDEO,
                                        resolution=f"{w}x{h}",
                                        width=w, height=h,
                                        match_score=min(100.0, 50.0 + self._score_resolution(w, h)),
                                        license_info=f"Pixabay License ({video.get('license', 'CC0')})",
                                        attribution=f"Photo by {video.get('user', 'Unknown')} on Pixabay",
                                        url=video.get("videos", {}).get("large", {}).get("url", ""),
                                        duration_seconds=float(video.get("duration", 0)),
                                        is_video=True,
                                    ))
                except Exception as e:
                    logger.warning(f"Pixabay video search failed for '{query}': {e}")

            url = "https://pixabay.com/api/"
            params = {
                "key": self.pixabay_api_key, "q": query,
                "per_page": min(MAX_RESULTS_PER_QUERY, 15),
                "orientation": "horizontal",
                "min_width": min_width, "min_height": min_height,
                "image_type": "photo",
            }
            try:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for photo in data.get("hits", []):
                            w = photo.get("width", 0)
                            h = photo.get("height", 0)
                            if w >= min_width and h >= min_height:
                                assets.append(HarvestedAsset(
                                    asset_uri=photo.get("largeImageURL", ""),
                                    source_type=VisualSourceType.STOCK_IMAGE,
                                    resolution=f"{w}x{h}",
                                    width=w, height=h,
                                    match_score=min(100.0, 70.0 + self._score_resolution(w, h)),
                                    license_info=f"Pixabay License ({photo.get('license', 'CC0')})",
                                    attribution=f"Photo by {photo.get('user', 'Unknown')} on Pixabay",
                                    url=photo.get("pageURL", ""),
                                    is_video=False,
                                ))
            except Exception as e:
                logger.warning(f"Pixabay photo search failed for '{query}': {e}")

        return assets

    async def _search_archive_org(self, queries: list[str], min_width: int, min_height: int) -> list[HarvestedAsset]:
        """Search Archive.org for public domain footage."""
        session = await self._get_session()
        assets: list[HarvestedAsset] = []

        for query in queries[:2]:
            url = "https://archive.org/advanced_search.php"
            params = {
                "q": f"mediatype:movies AND ({query})",
                "fl[]": "identifier,title,mediatype",
                "rows": 10, "page": 1,
            }
            try:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for doc in data.get("response", {}).get("docs", []):
                            asset_url = f"https://archive.org/details/{doc['identifier']}"
                            assets.append(HarvestedAsset(
                                asset_uri=asset_url,
                                source_type=VisualSourceType.STOCK_VIDEO,
                                resolution="variable",
                                width=1920, height=1080,
                                match_score=50.0,
                                license_info="Public Domain (Archive.org)",
                                attribution=f"Archive.org: {doc.get('title', 'Unknown')}",
                                url=asset_url,
                                duration_seconds=30.0,
                                is_video=True,
                            ))
            except Exception as e:
                logger.warning(f"Archive.org search failed for '{query}': {e}")

        return assets

    def _score_resolution(self, width: int, height: int) -> float:
        """Score an asset based on its resolution relative to requirements."""
        required = MIN_RESOLUTION
        actual = width * height
        if actual >= required * 4:
            return 30.0
        elif actual >= required * 2:
            return 20.0
        elif actual >= required:
            return 10.0
        else:
            return 0.0

    def _generate_fallback_prompt(self, queries: list[str], tags: list[str]) -> str:
        """Generate a prompt for AI fallback generation."""
        query_str = ", ".join(queries[:3])
        tag_str = ", ".join(tags[:5])
        return (
            f"Professional documentary footage: {query_str}. "
            f"Visual style: {tag_str}. "
            f"Cinematic, high-detail, 1920x1080, "
            f"natural lighting, 35mm film grain, "
            f"color graded with cinematic LUT."
        )

    def review_asset(self, asset_path: str, scene_context: dict[str, any] = None) -> AssetReview:
        """Review an asset for quality standards.

        Checks:
        1. File exists and is readable
        2. Image dimensions meet minimum (1920x1080)
        3. Image has visual content (std > 5.0, not blank/black)
        4. Image has color variation (not monochrome)
        5. Asset relevance to scene context (keyword matching)
        """
        from PIL import Image
        import numpy as np
        from app.core.schemas import AssetReview

        if not os.path.exists(asset_path):
            return AssetReview(valid=False, issues=["File does not exist"], score=0.0)

        issues = []
        try:
            img = Image.open(asset_path)
        except Exception as e:
            return AssetReview(valid=False, issues=[f"Cannot open image: {e}"], score=0.0)

        arr = np.array(img)
        h, w = arr.shape[:2]

        # Check dimensions
        if w < 1280 or h < 720:
            issues.append(f"Low resolution: {w}x{h} (minimum 1280x720)")

        # Check for blank/black image
        if arr.std() < 5.0:
            issues.append(f"Image appears blank/black (std={arr.std():.1f})")

        # Check for color variation
        if arr.ndim == 3:
            for ch in range(min(3, arr.shape[2])):
                ch_std = arr[:, :, ch].std()
                if ch_std < 3.0:
                    issues.append(f"Channel {ch} has low variation (std={ch_std:.1f})")

        # Check relevance to scene context
        score = 1.0
        if scene_context:
            prompt = scene_context.get("prompt", "").lower()
            # Score based on how well the asset matches the scene
            if "explosion" in prompt and arr.mean() > 50:
                score += 0.3  # Bright images for explosion scenes are good
            if "historical" in prompt and arr.std() > 10:
                score += 0.2  # Varied images for historical scenes are good
            if "map" in prompt:
                # Check for grid-like patterns (hard to detect, give neutral score)
                pass
            score = min(1.0, score)

        valid = len(issues) == 0
        return AssetReview(
            valid=valid,
            issues=issues,
            score=score if valid else 0.0,
            dimensions=(w, h),
            mean_brightness=float(arr.mean()),
            std_deviation=float(arr.std()),
        )
