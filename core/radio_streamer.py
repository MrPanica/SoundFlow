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
    - Strips radio mix/auto-generated playlist parameters (&list=RD..., &list=UL...)
      from video URLs so single videos play instantly instead of queueing 50 items.
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

    # 3. Strip auto-generated mix parameters from watch URLs (list=RD..., list=UL..., list=PU...)
    if "watch?v=" in url and any(k in url for k in ["&list=RD", "&list=UL", "&list=PU", "&list=TL"]):
        url = re.sub(r'&list=[^&]+', '', url)
        url = re.sub(r'&start_radio=[^&]+', '', url)

    # 4. Strip tracking parameters: si, feature, pp, utm_*
    url = re.sub(r'[?&](?:si|feature|pp|utm_[^&]+)=[^&]*', '', url)

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

    return None


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

            # If user explicitly provided a playlist page (/playlist?list=)
            is_explicit_playlist = ("/playlist?list=" in url.lower())

            ydl_opts: Dict[str, Any] = {
                'quiet': True,
                'no_warnings': True,
                'format': 'bestaudio/best',
                'noplaylist': not is_explicit_playlist,
                'skip_download': True,
            }
            if proxy_url:
                ydl_opts['proxy'] = proxy_url
            if FFMPEG_PATH:
                ydl_opts['ffmpeg_location'] = FFMPEG_PATH

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                # Check if it's an explicit playlist
                if is_explicit_playlist and (info.get('_type') == 'playlist' or 'entries' in info):
                    entries = list(info.get('entries') or [])
                    playlist_items = []
                    for idx, entry in enumerate(entries):
                        e_url = entry.get('url') or entry.get('webpage_url') or entry.get('id')
                        if e_url and not e_url.startswith("http"):
                            e_url = f"https://www.youtube.com/watch?v={e_url}"
                        playlist_items.append({
                            "url": e_url,
                            "title": entry.get('title') or f"Трек {idx + 1}",
                            "artist": entry.get('uploader') or entry.get('channel') or info.get('title', "Плейлист"),
                            "duration": entry.get('duration'),
                            "is_live": False
                        })

                    # Extract direct audio for first item
                    first_track = playlist_items[0] if playlist_items else None
                    if first_track:
                        sub_opts = {'quiet': True, 'no_warnings': True, 'format': 'bestaudio/best', 'noplaylist': True, 'skip_download': True}
                        if proxy_url:
                            sub_opts['proxy'] = proxy_url
                        if FFMPEG_PATH:
                            sub_opts['ffmpeg_location'] = FFMPEG_PATH
                        with yt_dlp.YoutubeDL(sub_opts) as sub_ydl:
                            first_info = sub_ydl.extract_info(first_track["url"], download=False)
                            direct_url = first_info.get('url')
                            return {
                                "url": direct_url or first_track["url"],
                                "web_url": first_track["url"],
                                "title": first_info.get('title') or first_track["title"],
                                "artist": first_info.get('uploader') or first_info.get('channel') or first_track["artist"],
                                "duration": first_info.get('duration') or first_track["duration"],
                                "is_live": bool(first_info.get('is_live', False)),
                                "playlist": playlist_items
                            }

                # Single video / audio track (including Shorts)
                direct_url = info.get('url')
                title = info.get('title') or "Web Stream"
                artist = info.get('uploader') or info.get('channel') or info.get('artist') or "YouTube"
                duration = info.get('duration')
                is_live = bool(info.get('is_live', False) or duration is None or duration == 0)

                if direct_url:
                    return {
                        "url": direct_url,
                        "web_url": url,
                        "title": title,
                        "artist": artist,
                        "duration": duration if not is_live else None,
                        "is_live": is_live,
                        "playlist": []
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


class RadioStreamer:
    """Streams and decodes online radio, YouTube, YouTube Music, and web streams into float32 audio chunks."""

    def __init__(self, sample_rate: int = 48000, buffer_size: int = 1024):
        self.sample_rate = sample_rate
        self.buffer_size = buffer_size

        # Jitter buffer queues (~6.4 seconds max capacity)
        self.queue_monitor = queue.Queue(maxsize=300)
        self.queue_mic = queue.Queue(maxsize=300)

        # Buffering thresholds
        self.is_buffering = True
        self.prebuffer_target = 20

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

        # Playlist queue
        self.playlist_queue: List[Dict[str, Any]] = []
        self.playlist_index: int = 0

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

            if info.get("playlist"):
                self.playlist_queue = info["playlist"]
                for idx, item in enumerate(self.playlist_queue):
                    if item.get("url") == raw_url or item.get("title") == self.current_title:
                        self.playlist_index = idx
                        break

            if self.on_metadata_changed:
                self.on_metadata_changed({
                    "title": self.current_title,
                    "artist": self.current_artist,
                    "duration": self.duration_sec,
                    "is_live": self.is_live,
                    "playlist_count": len(self.playlist_queue),
                    "playlist_index": self.playlist_index
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

        self._session_id += 1
        session_id = self._session_id
        self.current_url = url
        self.current_web_url = url
        self.current_name = name
        self.current_pos_sec = start_pos
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

    def has_next(self) -> bool:
        return bool(self.playlist_queue and self.playlist_index < len(self.playlist_queue) - 1)

    def has_prev(self) -> bool:
        return bool(self.playlist_queue and self.playlist_index > 0)

    def play_next(self):
        if self.has_next():
            self.playlist_index += 1
            item = self.playlist_queue[self.playlist_index]
            self.play(item["url"], item.get("title", "Next Track"))

    def play_prev(self):
        if self.has_prev():
            self.playlist_index -= 1
            item = self.playlist_queue[self.playlist_index]
            self.play(item["url"], item.get("title", "Prev Track"))

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
        for q in (self.queue_monitor, self.queue_mic):
            while not q.empty():
                try:
                    q.get_nowait()
                except queue.Empty:
                    break

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

            if info.get("playlist") and not self.playlist_queue:
                self.playlist_queue = info["playlist"]
                for idx, item in enumerate(self.playlist_queue):
                    if item.get("url") == raw_url or item.get("title") == self.current_title:
                        self.playlist_index = idx
                        break

            if session_id != self._session_id:
                return

            if self.on_metadata_changed:
                self.on_metadata_changed({
                    "title": self.current_title,
                    "artist": self.current_artist,
                    "duration": self.duration_sec,
                    "is_live": self.is_live,
                    "playlist_count": len(self.playlist_queue),
                    "playlist_index": self.playlist_index
                })

            if self.on_title_changed:
                self.on_title_changed(self.current_title)

            # Main streaming loop (with seek restart support)
            while not self._stop_event.is_set() and session_id == self._session_id:
                if self._seek_requested_pos is not None:
                    self.current_pos_sec = self._seek_requested_pos
                    self._seek_requested_pos = None
                    self._clear_queues()

                # Choose streaming pipeline
                direct_lower = direct_url.lower()
                use_ffmpeg = bool(FFMPEG_PATH and (
                    not self.is_live
                    or "googlevideo.com" in direct_lower
                    or "twitch.tv" in direct_lower
                    or ".m3u8" in direct_lower
                    or ".aac" in direct_lower
                    or ".m4a" in direct_lower
                    or "hls" in direct_lower
                ))

                success = False
                if use_ffmpeg:
                    success = self._run_ffmpeg_stream(direct_url, self.current_pos_sec)
                else:
                    success = self._run_miniaudio_stream(direct_url)
                    # Automatic fallback to FFmpeg if miniaudio fails on this stream
                    if not success and FFMPEG_PATH and not self._stop_event.is_set() and self._seek_requested_pos is None and session_id == self._session_id:
                        print(f"[RadioStreamer] Miniaudio stream failed for {direct_url}. Falling back to FFmpeg...")
                        if self.on_status_changed and session_id == self._session_id:
                            self.on_status_changed("Резервный декодер (FFmpeg)...")
                        success = self._run_ffmpeg_stream(direct_url, self.current_pos_sec)

                if not success:
                    had_error = True
                    if self.on_status_changed and not self._stop_event.is_set() and session_id == self._session_id:
                        self.on_status_changed("Ошибка радиопотока")
                    break

                # If EOF reached naturally and seek wasn't requested
                if not self._stop_event.is_set() and self._seek_requested_pos is None and session_id == self._session_id:
                    if self.has_next():
                        self.playlist_index += 1
                        next_item = self.playlist_queue[self.playlist_index]
                        direct_url, _ = resolve_stream_url(next_item["url"])
                        self.current_title = next_item.get("title", "Next Track")
                        self.current_artist = next_item.get("artist", "")
                        self.duration_sec = next_item.get("duration")
                        self.current_pos_sec = 0.0
                        if self.on_metadata_changed and session_id == self._session_id:
                            self.on_metadata_changed({
                                "title": self.current_title,
                                "artist": self.current_artist,
                                "duration": self.duration_sec,
                                "is_live": False,
                                "playlist_count": len(self.playlist_queue),
                                "playlist_index": self.playlist_index
                            })
                        continue
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

    def _run_ffmpeg_stream(self, stream_url: str, start_sec: float) -> bool:
        """Pipes float32 stereo PCM audio directly from FFmpeg stdout with producer backpressure."""
        proxy_url = get_best_stream_proxy()
        cmd = [
            FFMPEG_PATH,
            "-hide_banner",
            "-loglevel", "error",
            "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]
        if proxy_url:
            cmd.extend(["-http_proxy", proxy_url])
        cmd.extend([
            "-rw_timeout", "15000000",
            "-reconnect", "1",
            "-reconnect_streamed", "1",
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
            bytes_per_chunk = self.buffer_size * 2 * 4  # 1024 frames * 2 channels * float32 (4 bytes) = 8192 bytes

            if self.on_status_changed:
                self.on_status_changed("В эфире" if self.is_live else "Воспроизведение")

            total_chunks = 0
            while not self._stop_event.is_set() and self._seek_requested_pos is None:
                # Producer-Consumer Backpressure:
                # ONLY for non-live files / VOD to prevent infinite RAM buffering.
                # Live streams are already 1.0x real-time pace from server and must NEVER be throttled!
                if not self.is_live:
                    while max(self.queue_monitor.qsize(), self.queue_mic.qsize()) >= 120 and not self._stop_event.is_set() and self._seek_requested_pos is None:
                        time.sleep(0.015)

                if self._stop_event.is_set() or self._seek_requested_pos is not None:
                    break

                raw_bytes = self._ffmpeg_proc.stdout.read(bytes_per_chunk)
                if not raw_bytes or len(raw_bytes) < bytes_per_chunk:
                    break

                chunk = np.frombuffer(raw_bytes, dtype=np.float32).reshape(-1, 2)
                total_chunks += 1

                for q in (self.queue_monitor, self.queue_mic):
                    if q.full():
                        try:
                            q.get_nowait()
                        except queue.Empty:
                            pass
                    try:
                        q.put_nowait(chunk)
                    except Exception:
                        pass

                # Update playback timestamp
                self.current_pos_sec += (len(chunk) / float(self.sample_rate))

                if self.is_buffering and max(self.queue_monitor.qsize(), self.queue_mic.qsize()) >= self.prebuffer_target:
                    self.is_buffering = False
                    if self.on_status_changed:
                        self.on_status_changed("В эфире" if self.is_live else "Воспроизведение")

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

                data = np.frombuffer(samples, dtype=np.float32).reshape(-1, 2)
                total_chunks += 1

                for q in (self.queue_monitor, self.queue_mic):
                    if q.full():
                        try:
                            q.get_nowait()
                        except queue.Empty:
                            pass
                    try:
                        q.put_nowait(data)
                    except Exception:
                        pass

                self.current_pos_sec += (len(data) / float(self.sample_rate))
                if self.is_buffering and max(self.queue_monitor.qsize(), self.queue_mic.qsize()) >= self.prebuffer_target:
                    self.is_buffering = False
                    if self.on_status_changed:
                        self.on_status_changed("В эфире")

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

    def get_chunk_monitor(self) -> Optional[np.ndarray]:
        if self.is_buffering:
            return None
        try:
            return self.queue_monitor.get_nowait()
        except queue.Empty:
            return None

    def get_chunk_mic(self) -> Optional[np.ndarray]:
        if self.is_buffering:
            return None
        try:
            return self.queue_mic.get_nowait()
        except queue.Empty:
            return None

    def get_chunk(self) -> Optional[np.ndarray]:
        return self.get_chunk_monitor()
