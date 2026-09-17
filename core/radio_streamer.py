"""
Internet Radio, YouTube, YouTube Music & Web Streamer for SoundFlow Studio.
Features adaptive jitter buffering, IceCast/ShoutCast stream decoding,
full YouTube/Twitch support via yt-dlp and FFmpeg, YouTube Shorts support,
clean parameter normalization, queue backpressure (zero CPU spin),
playback time tracking, seeking ([-10s] / [+10s]), and playlist auto-advance.
"""

import sys
import threading
import queue
import time
import re
import urllib.request
import subprocess
from collections import deque
from typing import Optional, Callable, Tuple, Dict, Any, List
from pathlib import Path
import numpy as np
import miniaudio

try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_PATH = None


def clean_and_normalize_stream_url(raw_url: str) -> str:
    """
    Cleans and normalizes stream URLs:
    - Converts YouTube Shorts to standard watch URLs.
    - Normalizes mobile m.youtube.com to standard URLs.
    - Preserves playlist & mix parameters so full playlists load smoothly.
    - Removes tracking query parameters (?si=..., ?feature=..., &pp=..., &utm_*).
    """
    url = raw_url.strip()
    if not url:
        return ""

    # 1. Normalize YouTube Shorts
    # e.g. https://www.youtube.com/shorts/VIDEO_ID -> https://www.youtube.com/watch?v=VIDEO_ID
    url = re.sub(
        r'(?:https?://)?(?:www\.|m\.)?youtube\.com/shorts/([a-zA-Z0-9_-]+)',
        r'https://www.youtube.com/watch?v=\1',
        url
    )

    # 2. Normalize mobile URLs
    url = re.sub(r'https?://m\.youtube\.com/', 'https://www.youtube.com/', url)

    # 3. Strip tracking parameters: si, feature, pp, utm_*, fbclid, igshid
    url = re.sub(r'[?&](?:si|feature|pp|fbclid|igshid|utm_[^&]+)=[^&]*', '', url)

    # Clean up malformed URL query delimiters
    if '?' not in url and '&' in url:
        url = url.replace('&', '?', 1)
    if url.endswith('?') or url.endswith('&'):
        url = url[:-1]

    return url


def get_best_stream_proxy() -> Optional[str]:
    """
    Intelligently detects active proxy to bypass ISP YouTube/stream throttling:
    1. Environment variables: HTTPS_PROXY, HTTP_PROXY, ALL_PROXY.
    2. Windows Registry Internet Settings (ProxyServer, e.g. Clash / system proxy).
    3. Common local DPI-bypass proxy ports: 7897 (Clash Verge/Koala), 7890 (Clash for Windows), 10809/10808 (v2ray/xray), 2080.
    """
    import os
    import socket

    # 1. Common local proxy ports (Clash, V2Ray, Xray, Nekoray, etc.)
    for port in [7897, 7890, 10809, 10808, 2080, 8080]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.08)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    return f"http://127.0.0.1:{port}"
        except Exception:
            pass

    # 2. Windows Registry Internet Settings
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Internet Settings") as key:
                server, _ = winreg.QueryValueEx(key, "ProxyServer")
                if server:
                    if ";" in server:
                        for part in server.split(";"):
                            if part.startswith("http=") or part.startswith("https="):
                                host_port = part.split("=")[1]
                                return f"http://{host_port}" if not host_port.startswith("http") else host_port
                    else:
                        return f"http://{server}" if not server.startswith("http") else server
        except Exception:
            pass

    # 3. Environment variables
    for var in ["HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"]:
        val = os.environ.get(var)
        if val:
            return val

def extract_youtube_next_video(video_url: str, proxy_url: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Extracts the official YouTube 'Autoplay' next video and sidebar recommendations directly
    from YouTube initialData within <1 second.
    """
    m_vid = re.search(r'(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([a-zA-Z0-9_-]{11})', video_url)
    if not m_vid:
        return None, []
    vid = m_vid.group(1)
    watch_url = f"https://www.youtube.com/watch?v={vid}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    try:
        req = urllib.request.Request(watch_url, headers=headers)
        if proxy_url:
            proxy_handler = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
            opener = urllib.request.build_opener(proxy_handler)
        else:
            opener = urllib.request.build_opener()

        with opener.open(req, timeout=5) as resp:
            html = resp.read().decode("utf-8", "ignore")

        m = re.search(r'var ytInitialData = ({.*?});</script>', html)
        if not m:
            m = re.search(r'window\["ytInitialData"\] = ({.*?});</script>', html)
        if not m:
            return None, []

        data = json.loads(m.group(1))
        tc = data.get("contents", {}).get("twoColumnWatchNextResults", {})

        # 1. Autoplay target video ID
        ap = tc.get("autoplay", {})
        if "autoplay" in ap:
            ap = ap["autoplay"]
        next_vid_id = None
        for s in ap.get("sets", []):
            we = s.get("autoplayVideo", {}).get("watchEndpoint", {})
            nid = we.get("videoId")
            if nid and nid != vid:
                next_vid_id = nid
                break

        # 2. Extract lockupViewModels / compactVideoRenderers from secondaryResults
        sec_block = tc.get("secondaryResults", {}).get("secondaryResults", {})
        results = sec_block.get("results", [])
        items_to_check = []
        for res in results:
            if "itemSectionRenderer" in res:
                items_to_check.extend(res["itemSectionRenderer"].get("contents", []))
            else:
                items_to_check.append(res)

        extracted_videos: List[Dict[str, Any]] = []
        for it in items_to_check:
            if "compactVideoRenderer" in it:
                cvr = it["compactVideoRenderer"]
                c_id = cvr.get("videoId")
                if c_id and c_id != vid:
                    t = cvr.get("title", {}).get("simpleText") or cvr.get("title", {}).get("runs", [{}])[0].get("text", "")
                    a = cvr.get("shortBylineText", {}).get("runs", [{}])[0].get("text", "")
                    dur = cvr.get("lengthText", {}).get("simpleText", "")
                    extracted_videos.append({
                        "id": c_id,
                        "title": t,
                        "artist": a,
                        "duration_str": dur,
                        "url": f"https://www.youtube.com/watch?v={c_id}",
                        "thumbnail_url": f"https://i.ytimg.com/vi/{c_id}/hqdefault.jpg"
                    })
            elif "lockupViewModel" in it:
                lvm = it["lockupViewModel"]
                txt = json.dumps(lvm, ensure_ascii=False)
                m_id = re.search(r'/vi/([a-zA-Z0-9_-]{11})/', txt)
                if not m_id:
                    m_id = re.search(r'"videoId":\s*"([a-zA-Z0-9_-]{11})"', txt)
                if m_id and m_id.group(1) != vid:
                    c_id = m_id.group(1)
                    meta = lvm.get("metadata", {}).get("lockupMetadataViewModel", {})
                    t = meta.get("title", {}).get("content", "")
                    parts = meta.get("metadata", {}).get("contentMetadataViewModel", {}).get("metadataRows", [{}])[0].get("metadataParts", [{}])
                    a = parts[0].get("text", {}).get("content", "") if parts else ""
                    extracted_videos.append({
                        "id": c_id,
                        "title": t,
                        "artist": a,
                        "url": f"https://www.youtube.com/watch?v={c_id}",
                        "thumbnail_url": f"https://i.ytimg.com/vi/{c_id}/hqdefault.jpg"
                    })

        # Match next autoplay video with its title
        next_entry = None
        if next_vid_id:
            for ev in extracted_videos:
                if ev["id"] == next_vid_id:
                    next_entry = ev
                    break
            if not next_entry:
                next_entry = {
                    "id": next_vid_id,
                    "url": f"https://www.youtube.com/watch?v={next_vid_id}",
                    "title": f"YouTube Video ({next_vid_id})",
                    "artist": "YouTube",
                    "thumbnail_url": f"https://i.ytimg.com/vi/{next_vid_id}/hqdefault.jpg"
                }
        elif extracted_videos:
            next_entry = extracted_videos[0]

        return next_entry, extracted_videos
    except Exception as e:
        print(f"[RadioStreamer] extract_youtube_next_video notice: {e}")
        return None, []


def resolve_stream_info(raw_url: str) -> Dict[str, Any]:
    """
    Resolves any stream URL (YouTube, YouTube Shorts, YouTube Music, Twitch, radio, or direct audio link)
    into structured metadata including direct audio URL, title, artist, duration, and playlist items.
    """
    url = clean_and_normalize_stream_url(raw_url)
    if not url:
        return {"url": "", "title": "", "artist": "", "duration": None, "is_live": True, "playlist": []}

    proxy_url = get_best_stream_proxy()

    # 1. Russian Radio websites special resolution
    if "rusradio.ru" in url.lower():
        return {
            "url": "http://rusradio.hostingradio.ru/rusradio128.mp3",
            "web_url": url,
            "title": "Русское Радио",
            "artist": "Русское Радио",
            "duration": None,
            "is_live": True,
            "playlist": []
        }

    if "radiorecord.ru" in url.lower() and not url.lower().endswith((".aacp", ".mp3", ".m3u8")):
        return {
            "url": "https://radiorecord.hostingradio.ru/rr_96.aacp",
            "web_url": url,
            "title": "Radio Record Club Dance",
            "artist": "Radio Record",
            "duration": None,
            "is_live": True,
            "playlist": []
        }

    if "dfm.ru" in url.lower() and not url.lower().endswith((".aacp", ".mp3", ".m3u8")):
        return {
            "url": "https://dfm.hostingradio.ru/dfm96.aacp",
            "web_url": url,
            "title": "DFM Club",
            "artist": "DFM",
            "duration": None,
            "is_live": True,
            "playlist": []
        }

    if "hitfm.ru" in url.lower() and not url.lower().endswith((".aacp", ".mp3", ".m3u8")):
        return {
            "url": "https://hitfm.hostingradio.ru/hitfm96.aacp",
            "web_url": url,
            "title": "Hit FM",
            "artist": "Hit FM",
            "duration": None,
            "is_live": True,
            "playlist": []
        }

    if "maximum.ru" in url.lower() and not url.lower().endswith((".aacp", ".mp3", ".m3u8")):
        return {
            "url": "https://maximum.hostingradio.ru/maximum96.aacp",
            "web_url": url,
            "title": "Радио MAXIMUM",
            "artist": "MAXIMUM",
            "duration": None,
            "is_live": True,
            "playlist": []
        }

    # 2. YouTube / YouTube Shorts / YouTube Music / Twitch via yt-dlp
    is_video_platform = any(d in url.lower() for d in [
        "youtube.com", "youtu.be", "music.youtube.com", "twitch.tv", "soundcloud.com"
    ])

    if is_video_platform:
        try:
            import yt_dlp

            # Check if URL contains a playlist identifier (either /playlist?list= or watch?v=...&list=...)
            has_playlist = ("list=" in url.lower() or "/playlist" in url.lower())

            ydl_opts: Dict[str, Any] = {
                'quiet': True,
                'no_warnings': True,
                'format': 'bestaudio/best',
                'skip_download': True,
            }
            if has_playlist:
                ydl_opts['extract_flat'] = 'in_playlist'
                ydl_opts['noplaylist'] = False
                ydl_opts['playlistend'] = 50
            else:
                ydl_opts['noplaylist'] = True

            if proxy_url:
                ydl_opts['proxy'] = proxy_url
            if FFMPEG_PATH:
                ydl_opts['ffmpeg_location'] = FFMPEG_PATH

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                # Check if it's a playlist or container with multiple entries
                if (info.get('_type') == 'playlist' or 'entries' in info) and info.get('entries'):
                    entries = list(info.get('entries') or [])
                    playlist_items = []
                    start_idx = 0
                    current_vid = None
                    match_vid = re.search(r'[?&]v=([a-zA-Z0-9_-]+)', url)
                    if match_vid:
                        current_vid = match_vid.group(1)

                    for idx, entry in enumerate(entries):
                        if not entry:
                            continue
                        e_id = entry.get('id')
                        e_url = entry.get('url') or entry.get('webpage_url')
                        if e_id and (not e_url or not e_url.startswith("http")):
                            e_url = f"https://www.youtube.com/watch?v={e_id}"
                        elif not e_url:
                            e_url = url

                        if current_vid and e_id == current_vid:
                            start_idx = idx

                        e_thumb = None
                        if entry.get('thumbnail'):
                            e_thumb = entry.get('thumbnail')
                        elif entry.get('thumbnails'):
                            e_thumb = entry['thumbnails'][-1].get('url') or entry['thumbnails'][0].get('url')
                        elif e_id:
                            e_thumb = f"https://i.ytimg.com/vi/{e_id}/hqdefault.jpg"

                        playlist_items.append({
                            "url": e_url,
                            "title": entry.get('title') or f"Видео {idx + 1}",
                            "artist": entry.get('uploader') or entry.get('channel') or info.get('title', "YouTube"),
                            "duration": entry.get('duration'),
                            "thumbnail_url": e_thumb,
                            "is_live": False
                        })

                    # Extract direct audio for current selected track
                    active_track = playlist_items[start_idx] if (0 <= start_idx < len(playlist_items)) else (playlist_items[0] if playlist_items else None)
                    if active_track:
                        sub_opts = {'quiet': True, 'no_warnings': True, 'format': 'bestaudio/best', 'noplaylist': True, 'skip_download': True}
                        if proxy_url:
                            sub_opts['proxy'] = proxy_url
                        if FFMPEG_PATH:
                            sub_opts['ffmpeg_location'] = FFMPEG_PATH
                        with yt_dlp.YoutubeDL(sub_opts) as sub_ydl:
                            track_info = sub_ydl.extract_info(active_track["url"], download=False)
                            direct_url = track_info.get('url')
                            track_thumb = track_info.get('thumbnail') or active_track.get('thumbnail_url')
                            if not track_thumb and track_info.get('id'):
                                track_thumb = f"https://i.ytimg.com/vi/{track_info.get('id')}/hqdefault.jpg"

                            next_track = playlist_items[start_idx + 1] if (start_idx + 1 < len(playlist_items)) else None

                            return {
                                "url": direct_url or active_track["url"],
                                "web_url": active_track["url"],
                                "title": track_info.get('title') or active_track["title"],
                                "artist": track_info.get('uploader') or track_info.get('channel') or active_track["artist"],
                                "duration": track_info.get('duration') or active_track["duration"],
                                "thumbnail_url": track_thumb,
                                "next_title": next_track.get("title") if next_track else None,
                                "next_artist": next_track.get("artist") if next_track else None,
                                "is_live": bool(track_info.get('is_live', False)),
                                "playlist": playlist_items,
                                "playlist_index": start_idx
                            }

                # Single video / audio track (including Shorts)
                direct_url = info.get('url')
                title = info.get('title') or "Web Stream"
                artist = info.get('uploader') or info.get('channel') or info.get('artist') or "YouTube"
                duration = info.get('duration')
                is_live = bool(info.get('is_live', False) or duration is None or duration == 0)

                thumb_url = info.get('thumbnail')
                if not thumb_url and info.get('thumbnails'):
                    thumb_url = info['thumbnails'][-1].get('url')
                if not thumb_url and info.get('id'):
                    thumb_url = f"https://i.ytimg.com/vi/{info.get('id')}/hqdefault.jpg"

                if direct_url:
                    return {
                        "url": direct_url,
                        "web_url": url,
                        "title": title,
                        "artist": artist,
                        "duration": duration if not is_live else None,
                        "thumbnail_url": thumb_url,
                        "next_title": None,
                        "next_artist": None,
                        "is_live": is_live,
                        "playlist": [],
                        "playlist_index": 0
                    }
        except Exception as e:
            print(f"[RadioStreamer] yt-dlp extraction notice for {url}: {e}")

    # 3. Direct audio extension or Icecast stream
    direct_patterns = (".mp3", ".aac", ".aacp", ".ogg", ".opus", ".m4a")
    if any(ext in url.lower() for ext in direct_patterns) or ":80" in url or "icecast" in url or "stream" in url:
        clean_url = re.sub(r'[?&]utm_[^&]+', '', url)
        if clean_url.endswith("?") or clean_url.endswith("&"):
            clean_url = clean_url[:-1]
        return {
            "url": clean_url,
            "web_url": clean_url,
            "title": "Онлайн-поток",
            "artist": "Интернет-радио",
            "duration": None,
            "is_live": True,
            "playlist": []
        }

    # 4. Discovery via HTML webpage
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            html = resp.read(120000).decode("utf-8", errors="ignore")
        candidates = re.findall(r'https?://[^\s"\'<>]+\.(?:mp3|aac|aacp)[^\s"\'<>]*', html)
        if candidates:
            return {
                "url": candidates[0],
                "web_url": url,
                "title": "Радиостанция",
                "artist": "Онлайн эфир",
                "duration": None,
                "is_live": True,
                "playlist": []
            }
    except Exception as e:
        print(f"[RadioStreamer] HTML stream discovery error for {url}: {e}")

    return {
        "url": url,
        "web_url": url,
        "title": "Онлайн-стрим",
        "artist": "Стрим",
        "duration": None,
        "is_live": True,
        "playlist": []
    }


def resolve_stream_url(raw_url: str) -> Tuple[str, str]:
    """Backwards compatibility helper."""
    info = resolve_stream_info(raw_url)
    return info["url"], info["title"]


class AudioStreamBuffer:
    """
    Thread-safe continuous float32 PCM stream buffer (FIFO).
    Supports pushing chunks of arbitrary size and reading exact frame counts.
    Ensures ZERO sample loss, seamless cross-callback playback, and jitter-free buffering.
    """

    def __init__(self, max_frames: int = 48000 * 12):
        self.max_frames = max_frames
        self._lock = threading.Lock()
        self._chunks: deque = deque()
        self._total_frames: int = 0

    def clear(self):
        with self._lock:
            self._chunks.clear()
            self._total_frames = 0

    def write(self, data: np.ndarray):
        """Append float32 stereo array (N, 2)."""
        if len(data) == 0:
            return
        if data.ndim == 1:
            data = np.column_stack([data, data])
        with self._lock:
            self._chunks.append(data)
            self._total_frames += len(data)
            # Cap maximum frames to avoid unbounded memory growth
            while self._total_frames > self.max_frames and self._chunks:
                overflow = self._total_frames - self.max_frames
                first = self._chunks[0]
                first_len = len(first)
                if first_len <= overflow:
                    self._chunks.popleft()
                    self._total_frames -= first_len
                else:
                    self._chunks[0] = first[overflow:]
                    self._total_frames -= overflow
                    break

    def read_frames(self, num_frames: int) -> Optional[np.ndarray]:
        """Reads exactly num_frames. Returns None if fewer frames available."""
        with self._lock:
            if self._total_frames < num_frames:
                return None

            collected = []
            needed = num_frames
            while needed > 0 and self._chunks:
                first = self._chunks[0]
                first_len = len(first)
                if first_len <= needed:
                    collected.append(first)
                    self._chunks.popleft()
                    needed -= first_len
                    self._total_frames -= first_len
                else:
                    collected.append(first[:needed])
                    self._chunks[0] = first[needed:]
                    self._total_frames -= needed
                    needed = 0

            if len(collected) == 1:
                return collected[0]
            return np.vstack(collected)

    @property
    def available_frames(self) -> int:
        with self._lock:
            return self._total_frames


class RadioStreamer:
    """Streams and decodes online radio, YouTube, YouTube Music, and web streams into float32 audio chunks."""

    def __init__(self, sample_rate: int = 48000, buffer_size: int = 512):
        self.sample_rate = sample_rate
        self.buffer_size = buffer_size

        # Continuous stream buffers (zero sample loss FIFO)
        self.buffer_monitor = AudioStreamBuffer(max_frames=sample_rate * 12)
        self.buffer_mic = AudioStreamBuffer(max_frames=sample_rate * 12)
        self.monitor_output_enabled: bool = True
        self.mic_output_enabled: bool = False

        # Buffering thresholds: 2.0 seconds prebuffer target to prevent stream stuttering
        self.is_buffering = True
        self.prebuffer_target_frames = int(sample_rate * 2.0)
        self.current_peak: float = 0.0

        # State
        self.is_playing = False
        self.is_paused = False
        self.current_url: Optional[str] = None
        self.current_web_url: Optional[str] = None
        self.current_name: Optional[str] = None
        self.current_title: str = "Остановлено"
        self.current_artist: str = ""
        self.duration_sec: Optional[float] = None
        self.current_pos_sec: float = 0.0
        self.is_live: bool = True

        # Playlist queue & artwork
        self.playlist_queue: List[Dict[str, Any]] = []
        self.playlist_index: int = 0
        self.current_thumbnail_url: Optional[str] = None
        self.next_title: Optional[str] = None
        self.next_artist: Optional[str] = None
        self.next_url: Optional[str] = None
        self.youtube_history: List[Dict[str, Any]] = []
        self.youtube_recommendations: List[Dict[str, Any]] = []

        # Seeking state
        self._seek_requested_pos: Optional[float] = None

        # Error tracking & diagnostics
        self.last_error_details: str = ""

        # Threading
        self._session_id: int = 0
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._ffmpeg_proc: Optional[subprocess.Popen] = None
        self.client: Optional[miniaudio.IceCastClient] = None

        # Callbacks (Thread-safe signals should be bound by UI)
        self.on_metadata_changed: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_status_changed: Optional[Callable[[str], None]] = None
        self.on_progress: Optional[Callable[[float, float], None]] = None
        self.on_title_changed: Optional[Callable[[str], None]] = None

    @property
    def unplayed_buffer_sec(self) -> float:
        """Calculates remaining buffered audio time not yet sent to the audio output device."""
        if self.monitor_output_enabled:
            frames = self.buffer_monitor.available_frames
        elif self.mic_output_enabled:
            frames = self.buffer_mic.available_frames
        else:
            frames = 0
        return float(frames) / float(self.sample_rate)

    @property
    def playback_pos_sec(self) -> float:
        """
        Real-time playback position currently reaching listener ears.
        Accurately subtracts unplayed jitter buffer latency from the producer position.
        """
        if not self.is_playing and not self.is_paused:
            return 0.0
        pos = max(0.0, self.current_pos_sec - self.unplayed_buffer_sec)
        if self.duration_sec and self.duration_sec > 0:
            return min(pos, float(self.duration_sec))
        return pos

    @property
    def queue_monitor(self):
        class _QueueProxy:
            def __init__(proxy_self, buf, bsize):
                proxy_self.buf = buf
                proxy_self.bsize = bsize
                proxy_self.maxsize = 300
            def qsize(proxy_self):
                return proxy_self.buf.available_frames // proxy_self.bsize
            def empty(proxy_self):
                return proxy_self.buf.available_frames == 0
            def full(proxy_self):
                return False
            def get_nowait(proxy_self):
                res = proxy_self.buf.read_frames(proxy_self.bsize)
                if res is None:
                    raise queue.Empty()
                return res
            def put_nowait(proxy_self, chunk):
                proxy_self.buf.write(chunk)
        return _QueueProxy(self.buffer_monitor, self.buffer_size)

    @property
    def queue_mic(self):
        class _QueueProxy:
            def __init__(proxy_self, buf, bsize):
                proxy_self.buf = buf
                proxy_self.bsize = bsize
                proxy_self.maxsize = 300
            def qsize(proxy_self):
                return proxy_self.buf.available_frames // proxy_self.bsize
            def empty(proxy_self):
                return proxy_self.buf.available_frames == 0
            def full(proxy_self):
                return False
            def get_nowait(proxy_self):
                res = proxy_self.buf.read_frames(proxy_self.bsize)
                if res is None:
                    raise queue.Empty()
                return res
            def put_nowait(proxy_self, chunk):
                proxy_self.buf.write(chunk)
        return _QueueProxy(self.buffer_mic, self.buffer_size)

    def get_last_error_details(self) -> str:
        """Returns the last captured technical stream error diagnostics."""
        return self.last_error_details or "Подробности ошибки отсутствуют."

    def prepare(self, url: str, name: str = "Online Stream"):
        """Resolves stream metadata in background and updates UI without starting playback."""
        if self.is_playing:
            self.stop()

        self._session_id += 1
        session_id = self._session_id
        self.current_url = url
        self.current_web_url = url
        self.current_name = name
        self.current_pos_sec = 0.0
        self.is_playing = False
        self.is_paused = False
        self.is_buffering = False
        self._stop_event.set()

        threading.Thread(
            target=self._prepare_worker,
            args=(url, name, session_id),
            daemon=True,
            name="SoundFlow-StreamPrepareWorker"
        ).start()

    def _prepare_worker(self, raw_url: str, default_name: str, session_id: int):
        if session_id != self._session_id:
            return
        if self.on_status_changed:
            self.on_status_changed("Загрузка информации...")

        try:
            info = resolve_stream_info(raw_url)
            if session_id != self._session_id:
                return
            self.current_web_url = info.get("web_url") or raw_url
            self.current_title = info.get("title") or default_name
            self.current_artist = info.get("artist") or ""
            self.duration_sec = info.get("duration")
            self.is_live = info.get("is_live", True)
            self.current_pos_sec = 0.0

            self.current_thumbnail_url = info.get("thumbnail_url")
            self.next_title = info.get("next_title")
            self.next_artist = info.get("next_artist")

            if info.get("playlist"):
                self.playlist_queue = info["playlist"]
                if "playlist_index" in info:
                    self.playlist_index = info["playlist_index"]
                else:
                    for idx, item in enumerate(self.playlist_queue):
                        if item.get("url") == raw_url or item.get("title") == self.current_title:
                            self.playlist_index = idx
                            break
                if not self.next_title and self.playlist_index + 1 < len(self.playlist_queue):
                    nxt = self.playlist_queue[self.playlist_index + 1]
                    self.next_title = nxt.get("title")
                    self.next_artist = nxt.get("artist")

            if self.on_metadata_changed:
                self.on_metadata_changed({
                    "title": self.current_title,
                    "artist": self.current_artist,
                    "duration": self.duration_sec,
                    "thumbnail_url": self.current_thumbnail_url,
                    "next_title": self.next_title,
                    "next_artist": self.next_artist,
                    "is_live": self.is_live,
                    "playlist_count": len(self.playlist_queue),
                    "playlist_index": self.playlist_index,
                    "playlist": self.playlist_queue
                })

            if self.on_title_changed:
                self.on_title_changed(self.current_title)

            if self.on_status_changed:
                self.on_status_changed("Готов к воспроизведению")
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self.last_error_details = f"Ошибка подготовки/загрузки информации:\nURL: {raw_url}\nИсключение: {e}\n\n{tb}"
            print(f"[RadioStreamer] Prepare worker exception: {e}")
            if self.on_status_changed:
                self.on_status_changed(f"Ошибка загрузки: {e}")

    def play(self, url: str, name: str = "Online Radio", start_pos: float = 0.0):
        """Starts streaming the given radio station or video URL."""
        if self.is_playing:
            self.stop()

        # Track history for YouTube back button
        if self.is_youtube_active() and self.current_web_url:
            if not self.youtube_history or self.youtube_history[-1].get("url") != self.current_web_url:
                self.youtube_history.append({
                    "url": self.current_web_url,
                    "title": self.current_title,
                    "artist": self.current_artist
                })

        self._session_id += 1
        session_id = self._session_id
        self.current_url = url
        self.current_web_url = url
        self.current_name = name
        self.current_pos_sec = start_pos
        self.next_url = None
        self.is_playing = True
        self.is_paused = False
        self.is_buffering = True
        self._stop_event.clear()
        self._seek_requested_pos = None

        self._thread = threading.Thread(
            target=self._stream_worker,
            args=(url, name, start_pos, session_id),
            daemon=True,
            name="SoundFlow-StreamWorker"
        )
        self._thread.start()

    def pause(self):
        """Pauses current stream, keeping track and playback position."""
        if not self.is_playing or self.is_paused:
            return
        self._session_id += 1
        self.is_paused = True
        self.is_playing = False
        self._stop_event.set()

        self._terminate_subprocesses()
        self._clear_queues()

        if self.on_status_changed:
            self.on_status_changed("Приостановлено")

    def resume(self):
        """Resumes playback from the last paused position or URL."""
        if self.current_url:
            self.play(self.current_url, self.current_name or "Online Radio", start_pos=self.current_pos_sec)

    def stop(self):
        """Completely stops playback and resets state."""
        self._session_id += 1
        self.is_playing = False
        self.is_paused = False
        self.is_buffering = True
        self._stop_event.set()

        self._terminate_subprocesses()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None

        self.current_pos_sec = 0.0
        self.current_title = "Остановлено"
        self.current_peak = 0.0
        self._clear_queues()

        if self.on_status_changed:
            self.on_status_changed("Остановлено")

    def seek_relative(self, delta_sec: float):
        """Seeks forward or backward by delta_sec (e.g. +10 or -10)."""
        if self.is_live or not self.duration_sec or self.duration_sec <= 0:
            return
        target = max(0.0, min(self.duration_sec - 1.0, self.current_pos_sec + delta_sec))
        self.seek_to(target)

    def seek_to(self, target_sec: float):
        """Jumps directly to target_sec in the current video/track."""
        if self.is_live or not self.duration_sec or self.duration_sec <= 0:
            return
        target = max(0.0, min(self.duration_sec - 1.0, target_sec))
        self.current_pos_sec = target
        if self.is_playing:
            self._seek_requested_pos = target
            self._terminate_subprocesses()

    def is_youtube_active(self) -> bool:
        url = (self.current_web_url or self.current_url or "").lower()
        return "youtube.com" in url or "youtu.be" in url

    def has_next(self) -> bool:
        if self.playlist_queue and self.playlist_index < len(self.playlist_queue) - 1:
            return True
        if self.next_url and self.is_youtube_active():
            return True
        return False

    def has_prev(self) -> bool:
        if self.playlist_queue and self.playlist_index > 0:
            return True
        if len(self.youtube_history) > 1 and self.is_youtube_active():
            return True
        return False

    def play_next(self):
        """Advances to the next video in the playlist/queue or next recommended YouTube video."""
        if self.playlist_queue and self.playlist_index < len(self.playlist_queue) - 1:
            self.play_playlist_index(self.playlist_index + 1)
        elif self.next_url and self.is_youtube_active():
            nxt_url = self.next_url
            nxt_title = self.next_title or "YouTube Video"
            self.next_url = None
            self.next_title = None
            self.play(nxt_url, nxt_title)

    def play_prev(self):
        """Goes back to the previous video in the playlist/queue or YouTube history."""
        if self.playlist_queue and self.playlist_index > 0:
            self.play_playlist_index(self.playlist_index - 1)
        elif len(self.youtube_history) > 1 and self.is_youtube_active():
            self.youtube_history.pop()  # Pop current video
            prev_item = self.youtube_history.pop()  # Pop previous video to play
            self.play(prev_item["url"], prev_item.get("title", "YouTube Video"))

    def play_playlist_index(self, index: int):
        """Plays a specific video from the playlist queue by its index."""
        if not self.playlist_queue or index < 0 or index >= len(self.playlist_queue):
            return
        saved_queue = list(self.playlist_queue)
        self.playlist_index = index
        item = saved_queue[index]
        self.play(item["url"], item.get("title", f"Video {index + 1}"))
        self.playlist_queue = saved_queue
        self.playlist_index = index

    def _terminate_subprocesses(self):
        if self._ffmpeg_proc:
            try:
                self._ffmpeg_proc.terminate()
                self._ffmpeg_proc.wait(timeout=0.6)
            except Exception:
                try:
                    self._ffmpeg_proc.kill()
                except Exception:
                    pass
            self._ffmpeg_proc = None

        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None

    def _clear_queues(self):
        self.buffer_monitor.clear()
        self.buffer_mic.clear()

    def _stream_worker(self, raw_url: str, default_name: str, initial_pos: float, session_id: int):
        had_error = False
        try:
            if session_id != self._session_id or self._stop_event.is_set():
                return
            if self.on_status_changed:
                self.on_status_changed("Поиск и разрешение потока...")

            info = resolve_stream_info(raw_url)
            if session_id != self._session_id or self._stop_event.is_set():
                return
            direct_url = info.get("url") or raw_url
            self.current_web_url = info.get("web_url") or raw_url
            self.current_title = info.get("title") or default_name
            self.current_artist = info.get("artist") or ""
            self.duration_sec = info.get("duration")
            self.is_live = info.get("is_live", True)
            self.current_pos_sec = initial_pos

            self.current_thumbnail_url = info.get("thumbnail_url")
            self.next_title = info.get("next_title")
            self.next_artist = info.get("next_artist")

            if info.get("playlist") and not self.playlist_queue:
                self.playlist_queue = info["playlist"]
                if "playlist_index" in info:
                    self.playlist_index = info["playlist_index"]
                else:
                    for idx, item in enumerate(self.playlist_queue):
                        if item.get("url") == raw_url or item.get("title") == self.current_title:
                            self.playlist_index = idx
                            break

            if not self.next_title and self.playlist_queue and self.playlist_index + 1 < len(self.playlist_queue):
                nxt = self.playlist_queue[self.playlist_index + 1]
                self.next_title = nxt.get("title")
                self.next_artist = nxt.get("artist")

            if not self.playlist_queue and self.is_youtube_active():
                threading.Thread(
                    target=self._resolve_youtube_next_worker,
                    args=(self.current_web_url or raw_url, session_id),
                    daemon=True,
                    name="SoundFlow-YTNextWorker"
                ).start()

            if session_id != self._session_id:
                return

            if self.on_metadata_changed:
                self.on_metadata_changed({
                    "title": self.current_title,
                    "artist": self.current_artist,
                    "duration": self.duration_sec,
                    "thumbnail_url": self.current_thumbnail_url,
                    "next_title": self.next_title,
                    "next_artist": self.next_artist,
                    "is_live": self.is_live,
                    "playlist_count": len(self.playlist_queue),
                    "playlist_index": self.playlist_index,
                    "playlist": self.playlist_queue
                })

            if self.on_title_changed:
                self.on_title_changed(self.current_title)

            # Main streaming loop (with seek restart support)
            while not self._stop_event.is_set() and session_id == self._session_id:
                if self._seek_requested_pos is not None:
                    self.current_pos_sec = self._seek_requested_pos
                    self._seek_requested_pos = None
                    self._clear_queues()

                success = False
                if FFMPEG_PATH:
                    success = self._run_ffmpeg_stream(direct_url, self.current_pos_sec)
                    if not success and not self._stop_event.is_set() and self._seek_requested_pos is None and session_id == self._session_id:
                        print(f"[RadioStreamer] FFmpeg stream failed for {direct_url}. Trying miniaudio fallback...")
                        if self.on_status_changed and session_id == self._session_id:
                            self.on_status_changed("Резервный декодер (miniaudio)...")
                        success = self._run_miniaudio_stream(direct_url)
                else:
                    success = self._run_miniaudio_stream(direct_url)

                if not success:
                    had_error = True
                    if self.on_status_changed and not self._stop_event.is_set() and session_id == self._session_id:
                        self.on_status_changed("Ошибка радиопотока")
                    break

                # If EOF reached naturally and seek wasn't requested
                if not self._stop_event.is_set() and self._seek_requested_pos is None and session_id == self._session_id:
                    # Wait for playing buffer to finish before advancing to next video
                    while (self.buffer_monitor.available_frames > 4800 or self.buffer_mic.available_frames > 4800) and not self._stop_event.is_set() and session_id == self._session_id:
                        time.sleep(0.05)

                    if not self._stop_event.is_set() and session_id == self._session_id:
                        if self.playlist_queue and self.playlist_index + 1 < len(self.playlist_queue):
                            self.playlist_index += 1
                            next_item = self.playlist_queue[self.playlist_index]
                            next_info = resolve_stream_info(next_item["url"])
                            direct_url = next_info.get("url") or next_item["url"]
                            self.current_url = next_item["url"]
                            self.current_web_url = next_info.get("web_url") or next_item["url"]
                            self.current_title = next_info.get("title") or next_item.get("title", f"Video {self.playlist_index + 1}")
                            self.current_artist = next_info.get("artist") or next_item.get("artist", "")
                            self.duration_sec = next_info.get("duration") or next_item.get("duration")
                            self.current_thumbnail_url = next_info.get("thumbnail_url") or next_item.get("thumbnail_url")
                            self.is_live = bool(next_info.get("is_live", False))
                            self.current_pos_sec = 0.0

                            next_sub = self.playlist_queue[self.playlist_index + 1] if self.has_next() else None
                            self.next_title = next_sub.get("title") if next_sub else None
                            self.next_artist = next_sub.get("artist") if next_sub else None

                            if self.on_metadata_changed and session_id == self._session_id:
                                self.on_metadata_changed({
                                    "title": self.current_title,
                                    "artist": self.current_artist,
                                    "duration": self.duration_sec,
                                    "thumbnail_url": self.current_thumbnail_url,
                                    "next_title": self.next_title,
                                    "next_artist": self.next_artist,
                                    "next_url": self.next_url,
                                    "is_live": self.is_live,
                                    "playlist_count": len(self.playlist_queue),
                                    "playlist_index": self.playlist_index,
                                    "playlist": self.playlist_queue
                                })
                            if self.on_title_changed and session_id == self._session_id:
                                self.on_title_changed(self.current_title)
                            continue
                        elif self.next_url and self.is_youtube_active():
                            # Autoplay advance to next recommended YouTube video
                            nxt_u = self.next_url
                            nxt_t = self.next_title or "YouTube Video"
                            self.next_url = None
                            self.next_title = None
                            self.play(nxt_u, nxt_t)
                            break
                        else:
                            break
        except Exception as e:
            had_error = True
            import traceback
            tb = traceback.format_exc()
            self.last_error_details = f"Ошибка в рабочем потоке стримера:\nURL: {raw_url}\nИсключение: {e}\n\n{tb}"
            print(f"[RadioStreamer] Stream worker exception: {e}")
            if self.on_status_changed and session_id == self._session_id:
                self.on_status_changed(f"Ошибка потока: {e}")
        finally:
            if session_id == self._session_id:
                self.is_playing = False
                self.is_buffering = True
                if self.on_status_changed and not self.is_paused and not had_error:
                    self.on_status_changed("Остановлено")

    def _resolve_youtube_next_worker(self, video_url: str, session_id: int):
        """Asynchronously fetches the next related YouTube video in background without blocking audio."""
        try:
            nxt, recs = extract_youtube_next_video(video_url, proxy_url=get_best_stream_proxy())
            if session_id != self._session_id or not nxt or self._stop_event.is_set():
                return
            self.next_url = nxt.get("url")
            self.next_title = nxt.get("title")
            self.next_artist = nxt.get("artist")
            self.youtube_recommendations = recs
            if self.on_metadata_changed and session_id == self._session_id:
                self.on_metadata_changed({
                    "title": self.current_title,
                    "artist": self.current_artist,
                    "duration": self.duration_sec,
                    "thumbnail_url": self.current_thumbnail_url,
                    "next_title": self.next_title,
                    "next_artist": self.next_artist,
                    "next_url": self.next_url,
                    "is_live": self.is_live,
                    "playlist_count": len(self.playlist_queue),
                    "playlist_index": self.playlist_index,
                    "playlist": self.playlist_queue
                })
        except Exception as e:
            print(f"[RadioStreamer] _resolve_youtube_next_worker notice: {e}")

    def is_backpressure_full(self) -> bool:
        """
        Checks if active consumer buffers are sufficiently filled (around 4 seconds).
        Crucially respects whether monitor or mic outputs are independently enabled,
        preventing buffer starvation when a user turns off 'Слышать самому'.
        """
        limit = self.sample_rate * 4
        mon_active = self.monitor_output_enabled
        mic_active = self.mic_output_enabled

        if mon_active and mic_active:
            return (self.buffer_monitor.available_frames >= limit and self.buffer_mic.available_frames >= limit)
        elif mic_active:
            return self.buffer_mic.available_frames >= limit
        elif mon_active:
            return self.buffer_monitor.available_frames >= limit
        else:
            return True

    def dispatch_stream_chunk(self, chunk: np.ndarray):
        """
        Dispatches audio chunk to active consumer buffers.
        Clears inactive buffers so they don't accumulate stale audio or trigger false backpressure stalls.
        """
        if self.monitor_output_enabled:
            self.buffer_monitor.write(chunk)
        else:
            self.buffer_monitor.clear()

        if self.mic_output_enabled:
            self.buffer_mic.write(chunk)
        else:
            self.buffer_mic.clear()

        if self.is_buffering:
            target = self.prebuffer_target_frames
            ready = False
            if self.monitor_output_enabled and self.mic_output_enabled:
                ready = (self.buffer_monitor.available_frames >= target or self.buffer_mic.available_frames >= target)
            elif self.mic_output_enabled:
                ready = (self.buffer_mic.available_frames >= target)
            elif self.monitor_output_enabled:
                ready = (self.buffer_monitor.available_frames >= target)

            if ready:
                self.is_buffering = False
                if self.on_status_changed:
                    self.on_status_changed("В эфире" if self.is_live else "Воспроизведение")

    def _run_ffmpeg_stream(self, stream_url: str, start_sec: float) -> bool:
        """Pipes float32 stereo PCM audio directly from FFmpeg stdout with producer backpressure."""
        proxy_url = get_best_stream_proxy()
        cmd = [
            FFMPEG_PATH,
            "-hide_banner",
            "-loglevel", "error",
            "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "-probesize", "131072",
            "-analyzeduration", "1000000",
        ]
        if proxy_url:
            cmd.extend(["-http_proxy", proxy_url])
        cmd.extend([
            "-rw_timeout", "15000000",
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_at_eof", "1",
            "-reconnect_on_network_error", "1",
            "-reconnect_delay_max", "5",
        ])
        if start_sec > 0.0 and not self.is_live:
            cmd.extend(["-ss", f"{start_sec:.2f}"])

        cmd.extend([
            "-i", stream_url,
            "-vn",
            "-f", "f32le",
            "-ac", "2",
            "-ar", str(self.sample_rate),
            "pipe:1"
        ])

        # Ensure no console window appears on Windows when spawning FFmpeg
        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE

        stderr_lines: List[str] = []

        def _drain_stderr(proc):
            try:
                for line in iter(proc.stderr.readline, b''):
                    if line:
                        text = line.decode('utf-8', errors='replace').strip()
                        if text:
                            stderr_lines.append(text)
                            if len(stderr_lines) > 50:
                                stderr_lines.pop(0)
            except Exception:
                pass

        try:
            self._ffmpeg_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=self.buffer_size * 2 * 4 * 16,
                startupinfo=startupinfo,
                creationflags=creationflags
            )
            threading.Thread(target=_drain_stderr, args=(self._ffmpeg_proc,), daemon=True).start()
            bytes_per_chunk = 1024 * 2 * 4  # 1024 frames (8192 bytes)

            if self.on_status_changed:
                self.on_status_changed("В эфире" if self.is_live else "Воспроизведение")

            total_chunks = 0
            while not self._stop_event.is_set() and self._seek_requested_pos is None:
                # Producer backpressure: Keep buffer smooth around 1.0 to 4.0s (192,000 frames)
                while self.is_backpressure_full() and not self._stop_event.is_set() and self._seek_requested_pos is None:
                    time.sleep(0.02)

                if self._stop_event.is_set() or self._seek_requested_pos is not None:
                    break

                raw_bytes = self._ffmpeg_proc.stdout.read(bytes_per_chunk)
                if not raw_bytes or len(raw_bytes) < bytes_per_chunk:
                    break

                chunk = np.frombuffer(raw_bytes, dtype=np.float32).reshape(-1, 2)
                total_chunks += 1

                self.dispatch_stream_chunk(chunk)

                # Update playback timestamp
                self.current_pos_sec += (len(chunk) / float(self.sample_rate))

            if total_chunks == 0 and not self._stop_event.is_set() and self._seek_requested_pos is None:
                err_text = "\n".join(stderr_lines) if stderr_lines else "FFmpeg не вернул аудиоданных (таймаут соединения или сетевая блокировка)."
                self.last_error_details = f"URL: {stream_url}\nПрокси: {proxy_url or 'Нет (прямое соединение)'}\nFFmpeg лог:\n{err_text}"
                if self.on_status_changed:
                    self.on_status_changed("Ошибка: поток недоступен или заблокирован")
                return False

            return True
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            err_text = "\n".join(stderr_lines) if stderr_lines else ""
            self.last_error_details = f"Ошибка запуска FFmpeg: {e}\nURL: {stream_url}\nПрокси: {proxy_url or 'Нет'}\n{tb}\n\nFFmpeg лог:\n{err_text}"
            print(f"[RadioStreamer] FFmpeg stream exception: {e}")
            if self.on_status_changed:
                self.on_status_changed(f"Ошибка видеопотока: {e}")
            return False
        finally:
            if self._ffmpeg_proc:
                try:
                    self._ffmpeg_proc.terminate()
                except Exception:
                    pass
                self._ffmpeg_proc = None

    def _run_miniaudio_stream(self, stream_url: str) -> bool:
        """Streams live radio via miniaudio.IceCastClient without artificial backpressure stalls."""
        try:
            self.client = miniaudio.IceCastClient(stream_url, update_stream_title=self._on_icy_title)
            generator = miniaudio.stream_any(
                self.client,
                output_format=miniaudio.SampleFormat.FLOAT32,
                nchannels=2,
                sample_rate=self.sample_rate,
                frames_to_read=self.buffer_size
            )

            if self.on_status_changed:
                self.on_status_changed("В эфире")

            total_chunks = 0
            for samples in generator:
                if self._stop_event.is_set() or self._seek_requested_pos is not None:
                    break

                while self.is_backpressure_full() and not self._stop_event.is_set() and self._seek_requested_pos is None:
                    time.sleep(0.02)

                if self._stop_event.is_set() or self._seek_requested_pos is not None:
                    break

                data = np.frombuffer(samples, dtype=np.float32).reshape(-1, 2)
                total_chunks += 1

                self.dispatch_stream_chunk(data)

                self.current_pos_sec += (len(data) / float(self.sample_rate))

            if total_chunks == 0 and not self._stop_event.is_set() and self._seek_requested_pos is None:
                self.last_error_details = f"Miniaudio не получил аудиопакетов от сервера.\nURL: {stream_url}"
                return False

            return True
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self.last_error_details = f"Ошибка подключения к радиопотоку через miniaudio:\nURL: {stream_url}\nИсключение: {e}\n\n{tb}"
            print(f"[RadioStreamer] Miniaudio stream error: {e}")
            return False
        finally:
            if self.client:
                try:
                    self.client.close()
                except Exception:
                    pass
                self.client = None

    def _on_icy_title(self, client, title: str):
        cleaned = title.strip()
        if cleaned:
            self.current_title = cleaned
            if self.on_title_changed:
                self.on_title_changed(cleaned)
            if self.on_metadata_changed:
                self.on_metadata_changed({
                    "title": self.current_title,
                    "artist": self.current_artist,
                    "duration": self.duration_sec,
                    "is_live": True,
                    "playlist_count": len(self.playlist_queue),
                    "playlist_index": self.playlist_index
                })

    def read_frames_monitor(self, num_frames: int) -> Optional[np.ndarray]:
        if not self.monitor_output_enabled:
            return None
        if self.is_buffering:
            if self.buffer_monitor.available_frames >= self.prebuffer_target_frames:
                self.is_buffering = False
                if self.on_status_changed and not self.is_paused:
                    self.on_status_changed("В эфире" if self.is_live else "Воспроизведение")
            else:
                return None
        data = self.buffer_monitor.read_frames(num_frames)
        if data is None:
            if self.is_playing and not self.is_paused and not self.mic_output_enabled:
                self.is_buffering = True
            self.current_peak = 0.0
            return None
        self.current_peak = float(np.max(np.abs(data)))
        return data

    def read_frames_mic(self, num_frames: int) -> Optional[np.ndarray]:
        if not self.mic_output_enabled:
            return None
        if self.is_buffering:
            if self.buffer_mic.available_frames >= self.prebuffer_target_frames:
                self.is_buffering = False
                if self.on_status_changed and not self.is_paused:
                    self.on_status_changed("В эфире" if self.is_live else "Воспроизведение")
            else:
                return None
        data = self.buffer_mic.read_frames(num_frames)
        if data is None:
            if self.is_playing and not self.is_paused and not self.monitor_output_enabled:
                self.is_buffering = True
            if not self.monitor_output_enabled:
                self.current_peak = 0.0
            return None
        if not self.monitor_output_enabled:
            self.current_peak = float(np.max(np.abs(data)))
        return data

    def get_chunk_monitor(self) -> Optional[np.ndarray]:
        return self.read_frames_monitor(self.buffer_size)

    def get_chunk_mic(self) -> Optional[np.ndarray]:
        return self.read_frames_mic(self.buffer_size)

    def get_chunk(self) -> Optional[np.ndarray]:
        return self.get_chunk_monitor()
