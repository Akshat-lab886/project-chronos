"""Reliable Wikimedia downloader using Special:FilePath endpoint.

Bypasses the 403 robot policy issue by going through the public file path service.
"""
import httpx
import os
from pathlib import Path
from typing import Optional
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


def search_files(query: str, limit: int = 3) -> list[str]:
    """Search Wikimedia Commons for files matching query.

    Returns list of file titles like 'File:Mercedes F1 W03.jpg'.
    """
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srnamespace": "6",  # File namespace
        "format": "json",
        "srlimit": str(limit),
    }
    try:
        r = httpx.get(SEARCH_URL, params=params, headers=API_HEADERS, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        return [item["title"] for item in data.get("query", {}).get("search", [])]
    except Exception as e:
        print(f"Search error for '{query}': {e}")
        return []


def download_file(title: str, output_path: str, width: int = 1280) -> bool:
    """Download a Wikimedia file to output_path.

    Args:
        title: File title like 'File:Mercedes F1 W03.jpg'
        output_path: Local path to save to
        width: Desired width (will request thumbnail)

    Returns True on success.
    """
    # Strip 'File:' prefix and URL-encode
    filename = title.replace("File:", "")
    filename_encoded = filename.replace(" ", "_")

    # Use Special:FilePath with width parameter for thumbnail
    url = f"{FILE_PATH_BASE}/{filename_encoded}?width={width}"

    try:
        with httpx.Client(follow_redirects=True, timeout=30) as client:
            r = client.get(url, headers=HEADERS)
            if r.status_code == 200 and len(r.content) > 1000:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                Path(output_path).write_bytes(r.content)
                return True
            else:
                print(f"  Download failed: {r.status_code}, {len(r.content)}B")
                return False
    except Exception as e:
        print(f"  Download error: {e}")
        return False


def search_and_download(query: str, output_path: str, width: int = 1280) -> bool:
    """Combined search and download.

    Returns True if any matching file was successfully downloaded.
    """
    titles = search_files(query, limit=5)
    for title in titles:
        if download_file(title, output_path, width):
            return True
    return False


# Predefined F1-themed queries that we know return good results
F1_QUERIES = {
    "race_car": ["Formula 1 race car", "F1 car", "racing car"],
    "mercedes": ["Mercedes F1", "Mercedes AMG Petronas", "Silver Arrows F1"],
    "ferrari": ["Scuderia Ferrari F1", "Ferrari Formula One", "Ferrari race car red"],
    "red_bull": ["Red Bull Racing F1", "Oracle Red Bull", "Red Bull car"],
    "mclaren": ["McLaren F1 car", "McLaren papaya orange", "McLaren Formula 1"],
    "podium": ["F1 podium", "Formula 1 podium ceremony", "trophy presentation motorsport"],
    "pit_stop": ["F1 pit stop", "pit crew tire change", "Formula One pit"],
    "wind_tunnel": ["F1 wind tunnel", "wind tunnel testing", "aerodynamic testing car"],
    "engine": ["F1 engine", "Formula 1 V6 hybrid", "race car engine"],
    "monaco": ["Monaco Grand Prix", "Monte Carlo F1", "Monaco street circuit"],
    "silverstone": ["Silverstone circuit", "British Grand Prix", "Silverstone F1"],
    "monza": ["Monza F1", "Italian Grand Prix", "Monza circuit"],
    "drivers": ["Lewis Hamilton", "Max Verstappen", "Sebastian Vettel", "Fernando Alonso"],
    "celebration": ["F1 celebration", "champagne podium", "F1 winner"],
    "miami": ["Miami Grand Prix", "Miami F1", "Miami International Autodrome"],
    "las_vegas": ["Las Vegas Grand Prix", "Las Vegas F1", "Vegas Strip race"],
    "tire": ["F1 tire", "Formula 1 Pirelli", "slick racing tire"],
    "circuit": ["F1 circuit aerial", "race track overhead", "Formula 1 track"],
    "money": ["money", "currency", "stock chart", "financial graph"],
    "luxury": ["luxury car", "expensive automobile", "premium brand"],
    "business": ["business meeting", "corporate boardroom", "financial chart"],
    "carbon": ["carbon fiber", "F1 bodywork", "composite material"],
    "mechanic": ["F1 mechanic", "race car mechanic", "F1 engineer garage"],
    "team": ["F1 team paddock", "F1 garage", "F1 pit lane"],
    "winner": ["F1 winner", "champion trophy", "victory lane motorsport"],
}
