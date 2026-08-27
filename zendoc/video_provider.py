"""
Video Provider — provider abstraction for fitness video discovery.

Provider selection via ZENDOC_VIDEO_PROVIDER environment variable:
    none     → NullVideoProvider (returns structured unavailable response)
    youtube  → YouTubeProvider (requires ZENDOC_YOUTUBE_API_KEY)

IMPORTANT: No video results are ever fabricated.
If a provider is unavailable or fails, the response clearly states this.
"""

import hashlib
import time
from urllib.parse import urlencode
from urllib.request import urlopen, Request
import json
import os
from threading import Lock


# ---------------------------------------------------------------------------
# Simple in-memory LRU cache (no Redis required)
# ---------------------------------------------------------------------------

_CACHE = {}          # key → (timestamp, result)
_CACHE_TTL = 3600    # 1 hour
_CACHE_MAX = 128
_CACHE_LOCK = Lock()


def _cache_key(query, max_results):
    return hashlib.md5(f"{query}:{max_results}".encode()).hexdigest()


def _cache_get(key):
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if entry and (time.time() - entry[0]) < _CACHE_TTL:
            return entry[1]
        _CACHE.pop(key, None)
        return None


def _cache_set(key, value):
    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_MAX:
            oldest = min(_CACHE, key=lambda k: _CACHE[k][0])
            del _CACHE[oldest]
        _CACHE[key] = (time.time(), value)


# ---------------------------------------------------------------------------
# Provider base
# ---------------------------------------------------------------------------

class VideoResult:
    def __init__(self, title, channel, url, thumbnail_url=None, duration=None, provider="unknown"):
        self.title = title
        self.channel = channel
        self.url = url
        self.thumbnail_url = thumbnail_url
        self.duration = duration
        self.provider = provider

    def to_dict(self):
        return {
            "title": self.title,
            "channel": self.channel,
            "url": self.url,
            "thumbnail_url": self.thumbnail_url,
            "duration": self.duration,
            "provider": self.provider,
        }


class NullVideoProvider:
    """Returns a structured 'unavailable' response.  Never fabricates results."""

    name = "none"

    def search(self, query, max_results=5):
        return {
            "available": False,
            "reason": (
                "Video discovery requires a video provider API key. "
                "Set ZENDOC_VIDEO_PROVIDER=youtube and ZENDOC_YOUTUBE_API_KEY "
                "to enable real video results."
            ),
            "results": [],
            "query": query,
        }


class YouTubeProvider:
    """
    YouTube Data API v3 video search.
    Requires ZENDOC_YOUTUBE_API_KEY.
    Timeout: 5 seconds.  Results cached 1 hour in-process.
    """

    name = "youtube"
    _BASE = "https://www.googleapis.com/youtube/v3/search"

    def __init__(self, api_key):
        self._api_key = api_key

    def search(self, query, max_results=5):
        cache_key = _cache_key(query, max_results)
        cached = _cache_get(cache_key)
        if cached:
            return cached

        params = urlencode({
            "part": "snippet",
            "q": f"{query} fitness tutorial",
            "type": "video",
            "maxResults": min(int(max_results), 10),
            "safeSearch": "moderate",
            "key": self._api_key,
        })
        url = f"{self._BASE}?{params}"
        try:
            req = Request(url, headers={"Accept": "application/json"})
            with urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
        except Exception as exc:
            return {
                "available": False,
                "reason": f"Video provider request failed: {type(exc).__name__}. Please try again later.",
                "results": [],
                "query": query,
            }

        results = []
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            vid_id = item.get("id", {}).get("videoId", "")
            if not vid_id:
                continue
            results.append(VideoResult(
                title=snippet.get("title", ""),
                channel=snippet.get("channelTitle", ""),
                url=f"https://www.youtube.com/watch?v={vid_id}",
                thumbnail_url=(snippet.get("thumbnails", {}).get("medium", {}).get("url")),
                duration=None,  # Requires a separate /videos?part=contentDetails call
                provider="youtube",
            ).to_dict())

        response = {
            "available": True,
            "results": results,
            "query": query,
            "provider": "youtube",
            "total": len(results),
        }
        _cache_set(cache_key, response)
        return response


def configured_video_provider():
    """
    Return the video provider configured via ZENDOC_VIDEO_PROVIDER.
    Defaults to NullVideoProvider if not set or key is missing.
    """
    provider_name = os.environ.get("ZENDOC_VIDEO_PROVIDER", "none").strip().lower()
    if provider_name == "youtube":
        api_key = os.environ.get("ZENDOC_YOUTUBE_API_KEY", "").strip()
        if api_key:
            return YouTubeProvider(api_key)
        # Key not set — degrade gracefully
        return NullVideoProvider()
    return NullVideoProvider()


def search_fitness_video(query, max_results=5):
    """
    Top-level entry point used by routes and FitnessCoach.
    Sanitises query and delegates to the configured provider.
    """
    clean_query = str(query or "").strip()[:200]
    if not clean_query:
        return {
            "available": False,
            "reason": "A search query is required.",
            "results": [],
            "query": "",
        }
    return configured_video_provider().search(clean_query, max_results)
