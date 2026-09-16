"""Video-provider abstraction for real educational video discovery.

Provider selection via ``ZENDOC_VIDEO_PROVIDER``:
- ``none``: return a truthful direct YouTube search handoff;
- ``youtube``: use YouTube Data API v3 when ``ZENDOC_YOUTUBE_API_KEY`` exists.

No video cards or links are fabricated as API results.
"""

import hashlib
import json
import os
import time
from threading import Lock
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

_CACHE = {}
_CACHE_TTL = 3600
_CACHE_MAX = 128
_CACHE_LOCK = Lock()

def _cache_key(query, max_results):
    return hashlib.sha256(f"{query}:{max_results}".encode()).hexdigest()

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
            oldest = min(_CACHE, key=lambda item: _CACHE[item][0])
            del _CACHE[oldest]
        _CACHE[key] = (time.time(), value)

def _youtube_search_url(query):
    clean = " ".join(str(query or "").strip().split())[:200]
    if not clean:
        return None
    return "https://www.youtube.com/results?search_query=" + quote_plus(clean)

class VideoResult:
    def __init__(self, title, channel, url, thumbnail_url=None, duration=None, provider="unknown"):
        self.title = title
        self.channel = channel
        self.url = url
        self.thumbnail_url = thumbnail_url
        self.duration = duration
        self.provider = provider

    def to_dict(self):
        return {"title": self.title, "channel": self.channel, "url": self.url, "thumbnail_url": self.thumbnail_url, "duration": self.duration, "provider": self.provider}

class NullVideoProvider:
    name = "none"

    def search(self, query, max_results=5):
        return {
            "available": False,
            "reason": "Video discovery requires a video provider API key for live in-app results. You can still open this exact topic as a real YouTube search using the link below.",
            "results": [],
            "query": query,
            "search_url": _youtube_search_url(query),
            "search_provider": "youtube_web_search",
            "provider": "none",
        }

class YouTubeProvider:
    name = "youtube"
    _BASE = "https://www.googleapis.com/youtube/v3/search"

    def __init__(self, api_key):
        self._api_key = api_key

    def search(self, query, max_results=5):
        cache_key = _cache_key(query, max_results)
        cached = _cache_get(cache_key)
        if cached:
            return cached
        params = urlencode({"part": "snippet", "q": query, "type": "video", "maxResults": min(max(int(max_results), 1), 10), "safeSearch": "moderate", "relevanceLanguage": "en", "key": self._api_key})
        try:
            request = Request(f"{self._BASE}?{params}", headers={"Accept": "application/json", "User-Agent": "ZENDOC/1.0 VideoDiscovery"})
            with urlopen(request, timeout=5) as response:
                raw = response.read(2_097_153)
            if len(raw) > 2_097_152:
                raise ValueError("YouTube response exceeded the safe response limit.")
            data = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            return {"available": False, "reason": f"Video provider request failed: {type(exc).__name__}. You can use the direct YouTube search link below.", "results": [], "query": query, "search_url": _youtube_search_url(query), "search_provider": "youtube_web_search", "provider": "youtube"}
        results = []
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            video_id = item.get("id", {}).get("videoId", "")
            if not video_id:
                continue
            results.append(VideoResult(str(snippet.get("title") or "")[:300], str(snippet.get("channelTitle") or "")[:160], f"https://www.youtube.com/watch?v={video_id}", snippet.get("thumbnails", {}).get("medium", {}).get("url"), None, "youtube").to_dict())
        response = {"available": True, "results": results, "query": query, "provider": "youtube", "total": len(results), "search_url": _youtube_search_url(query)}
        _cache_set(cache_key, response)
        return response

def configured_video_provider():
    provider_name = os.environ.get("ZENDOC_VIDEO_PROVIDER", "none").strip().lower()
    if provider_name == "youtube":
        api_key = os.environ.get("ZENDOC_YOUTUBE_API_KEY", "").strip()
        if api_key:
            return YouTubeProvider(api_key)
    return NullVideoProvider()

def search_fitness_video(query, max_results=5):
    clean_query = " ".join(str(query or "").strip().split())[:200]
    if not clean_query:
        return {"available": False, "reason": "A search query is required.", "results": [], "query": "", "search_url": None, "provider": "none"}
    return configured_video_provider().search(clean_query, max_results)
