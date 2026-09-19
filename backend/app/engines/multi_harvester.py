"""Multi-asset harvester: download 2-3 images/videos per scene for visual variety.

Also adds video support: searches for .webm files on Wikimedia for motion.
"""
import httpx
from pathlib import Path
from typing import Optional
import os
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
API_HEADERS = {
    "User-Agent": "ProjectChronos/1.0 (https://github.com/Akshat-lab886/project-chronos) python-httpx/0.27"
}

SEARCH_URL = "https://commons.wikimedia.org/w/api.php"
FILE_PATH_BASE = "https://commons.wikimedia.org/wiki/Special:FilePath"


def search_files(query: str, file_type: str = "image", limit: int = 5) -> list[str]:
    """Search Wikimedia Commons for files.

    file_type: "image" or "video"
    """
    # Filter by mime type using srnamespace=6 (File) and content model filter
    if file_type == "video":
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srnamespace": "6",
            "format": "json",
            "srlimit": str(limit * 2),  # Get more to filter
        }
    else:
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srnamespace": "6",
            "format": "json",
            "srlimit": str(limit * 2),
        }
    try:
        r = httpx.get(SEARCH_URL, params=params, headers=API_HEADERS, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        all_titles = [item["title"] for item in data.get("query", {}).get("search", [])]

        # Post-filter by mime type from imageinfo
        filtered = []
        for title in all_titles:
            info = get_file_url_and_metadata(title)
            if not info:
                continue
            mime = info.get("mime", "")
            if file_type == "video" and (mime.startswith("video/") or title.lower().endswith(('.webm', '.ogv'))):
                filtered.append(title)
            elif file_type == "image" and mime.startswith("image/"):
                filtered.append(title)
            if len(filtered) >= limit:
                break
        return filtered
    except Exception as e:
        print(f"Search error for '{query}': {e}")
        return []


def get_file_url_and_metadata(title: str) -> Optional[dict]:
    """Get file URL and MIME type for a Wikimedia file."""
    params = {
        "action": "query",
        "titles": title,
        "prop": "imageinfo",
        "iiprop": "url|mime|size",
        "format": "json",
    }
    try:
        r = httpx.get(SEARCH_URL, params=params, headers=API_HEADERS, timeout=15)
        data = r.json()
        pages = data.get("query", {}).get("pages", {})
        for p in pages.values():
            info = p.get("imageinfo", [{}])[0]
            return {
                "url": info.get("url"),
                "mime": info.get("mime"),
                "size": info.get("size", 0),
            }
    except Exception as e:
        print(f"  Get URL error: {e}")
    return None


def download_file(title: str, output_path: str, width: int = 1280) -> dict:
    """Download a Wikimedia file to output_path.

    Returns dict with: success, mime, size_bytes
    """
    info = get_file_url_and_metadata(title)
    if not info or not info.get("url"):
        return {"success": False, "error": "no_url"}

    url = info["url"].split("?")[0]
    mime = info.get("mime", "")

    # For images, use Special:FilePath for thumbnail resizing
    if mime.startswith("image/"):
        filename = title.replace("File:", "").replace(" ", "_")
        download_url = f"{FILE_PATH_BASE}/{filename}?width={width}"
        headers = HEADERS
    else:
        # For videos, must use the original URL (thumbnails not supported)
        download_url = url
        headers = API_HEADERS

    try:
        with httpx.Client(follow_redirects=True, timeout=120) as client:
            r = client.get(download_url, headers=headers)
            if r.status_code == 200 and len(r.content) > 5000:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                Path(output_path).write_bytes(r.content)
                return {"success": True, "mime": mime, "size_bytes": len(r.content)}
            else:
                return {"success": False, "error": f"status_{r.status_code}", "size": len(r.content)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_and_download_image(query: str, output_path: str, width: int = 1280) -> bool:
    """Combined image search and download."""
    titles = search_files(query, "image", limit=8)
    for title in titles:
        result = download_file(title, output_path, width)
        if result.get("success"):
            return True
    return False


def search_and_download_video(query: str, output_path: str, max_size_mb: int = 50) -> bool:
    """Search and download a small video. Skips files > max_size_mb."""
    titles = search_files(query, "video", limit=8)
    for title in titles:
        info = get_file_url_and_metadata(title)
        if not info:
            continue
        size_mb = info.get("size", 0) / (1024 * 1024)
        if size_mb > max_size_mb:
            print(f"  Skip {title}: {size_mb:.0f}MB too large")
            continue
        result = download_file(title, output_path)
        if result.get("success"):
            return True
    return False


def harvest_multi_assets(
    scene_id: str,
    queries: list[str],
    asset_dir: Path,
    num_images: int = 3,
    try_video: bool = False,
) -> dict:
    """Harvest multiple images and optionally a video for a scene.

    Returns dict with:
        images: list of relative paths
        video: relative path or None
    """
    images = []
    video_path = None

    # Try video first if requested
    if try_video:
        video_path_full = asset_dir / f"{scene_id}_motion.webm"
        for q in queries:
            if search_and_download_video(q, str(video_path_full), max_size_mb=30):
                video_path = str(video_path_full.name)
                print(f"  Got video: {video_path}")
                break

    # Then download images
    for i in range(num_images):
        img_path = asset_dir / f"{scene_id}_{i+1}.jpg"
        # Rotate through queries
        q = queries[i % len(queries)] if i < len(queries) else queries[0]
        if search_and_download_image(q, str(img_path), width=1280):
            images.append(str(img_path.name))
        else:
            break  # No more images available

    return {
        "images": images,
        "video": video_path,
    }
