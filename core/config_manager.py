"""
Configuration and data manager for SoundFlow Studio.
Handles loading/saving settings, sound library, radio stations, and TTS phrases.
"""

import json
import os
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "SoundFlowStudio"
APP_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = APP_DIR / "config.json"
SOUNDS_FILE = APP_DIR / "sounds.json"
CATEGORIES_FILE = APP_DIR / "categories.json"
STATIONS_FILE = APP_DIR / "stations.json"
TTS_PRESETS_FILE = APP_DIR / "tts_presets.json"
VOICE_PRESETS_FILE = APP_DIR / "voice_presets.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "monitor_device_id": None,
    "mic_target_device_id": None,
    "mic_input_device_id": None,
    "monitor_volume": 1.0,
    "mic_volume": 1.0,
    "app_stream_monitor_vol": 0.8,
    "app_stream_mic_vol": 1.0,
    "radio_monitor_vol": 0.7,
    "radio_mic_vol": 0.9,
    "radio_monitor_enabled": True,
    "radio_mic_enabled": True,
    "tts_monitor_vol": 0.8,
    "tts_mic_vol": 1.0,
    "mic_passthrough_enabled": True,
    "mic_gate_threshold": -40.0,
    "mic_voice_fx": "normal",
    "instant_replay_duration": 30,  # seconds
    "minimize_to_tray": True,
    "notify_on_minimize": True,
    "hide_cable_default_banner": False,
    "close_to_tray": True,
    "buffer_size": 1024,
    "exit_mic_behavior": "restore_default",
    "recordings_dir": str(APP_DIR / "recordings"),
    "ptt_enabled": False,
    "ptt_key": "v",
    "ptt_delay_ms": 150,
    "ducking_enabled": True,
    "ducking_amount": 0.25,
    "ducking_threshold_db": -35.0,
    "auto_normalize": True,
    "random_sound_hotkey": "",
    "hotkeys": {
        "stop_all": "esc",
        "app_stream_toggle": "ctrl+f9",
        "radio_toggle": "ctrl+f10",
        "instant_replay_clip": "ctrl+f11",
        "mic_mute_toggle": "ctrl+f12",
        "random_sound": ""
    }
}

DEFAULT_STATIONS: List[Dict[str, Any]] = [
    {
        "id": "rusradio",
        "name": "Русское Радио",
        "genre": "Поп / Русские хиты",
        "url": "http://rusradio.hostingradio.ru/rusradio128.mp3",
        "description": "Всё будет хорошо! Главные русские хиты"
    },
    {
        "id": "record_edm",
        "name": "Radio Record Club Dance",
        "genre": "EDM / Electronic",
        "url": "https://hls-01-radiorecord.hostingradio.ru/record/playlist.m3u8",
        "description": "Энергичная электронная клубная музыка"
    },
    {
        "id": "rock_fm",
        "name": "Rock Classic Hits",
        "genre": "Classic Rock",
        "url": "https://nashe1.hostingradio.ru/rock-128.mp3",
        "description": "Легендарные рок-хиты всех времен"
    },
    {
        "id": "dfm_club",
        "name": "DFM Club",
        "genre": "Dance / Pop",
        "url": "https://dfm.hostingradio.ru/dfm128.mp3",
        "description": "Зажигательные хиты и клубные ремиксы"
    },
    {
        "id": "lofi_beats",
        "name": "Lofi Chill & Study",
        "genre": "Lofi / Hip-Hop",
        "url": "http://stream.laut.fm/lofi",
        "description": "Расслабляющий чилловый хип-хоп для фона и каток"
    },
    {
        "id": "nightride_synth",
        "name": "Nightride Synthwave",
        "genre": "Synthwave / Cyberpunk",
        "url": "https://stream.nightride.fm/nightride.mp3",
        "description": "Ретровейв, синтвейв и неоновый вайб 80-х"
    }
]

DEFAULT_TTS_PRESETS: List[Dict[str, Any]] = [
    {"id": "tts_1", "text": "GG WP! Отличная игра!", "voice": "ru-RU-DmitryNeural", "fx": "normal"},
    {"id": "tts_2", "text": "Всем привет, подключаюсь!", "voice": "ru-RU-DmitryNeural", "fx": "normal"},
    {"id": "tts_3", "text": "Я отойду на пару минут (AFK).", "voice": "ru-RU-SvetlanaNeural", "fx": "normal"},
    {"id": "tts_4", "text": "Осторожно, враг сзади!", "voice": "ru-RU-DmitryNeural", "fx": "monster"},
    {"id": "tts_5", "text": "Да ладно, как так-то?!", "voice": "ru-RU-DmitryNeural", "fx": "helium"},
    {"id": "tts_6", "text": "Внимание, база атакована!", "voice": "ru-RU-DmitryNeural", "fx": "robot"},
    {"id": "tts_7", "text": "Hello guys, nice to meet you!", "voice": "en-US-GuyNeural", "fx": "megaphone"}
]


DEFAULT_CATEGORIES: List[Dict[str, Any]] = [
    {"id": "ALL", "name": "Все", "system": True},
    {"id": "FAVORITES", "name": "Избранное", "system": True},
    {"id": "MEMES", "name": "Мемы", "system": False},
    {"id": "GAMING", "name": "Игры", "system": False},
    {"id": "SFX", "name": "SFX", "system": False},
    {"id": "CLIPS", "name": "Клипы", "system": True}
]


class ConfigManager:
    """Manages persistent configuration for SoundFlow Studio."""

    def __init__(self):
        self.config = self._load_json(CONFIG_FILE, DEFAULT_CONFIG)
        self.sounds = self._load_json(SOUNDS_FILE, [])
        self.categories = self._load_json(CATEGORIES_FILE, DEFAULT_CATEGORIES)
        self.stations = self._load_json(STATIONS_FILE, DEFAULT_STATIONS)
        self.tts_presets = self._load_json(TTS_PRESETS_FILE, DEFAULT_TTS_PRESETS)
        self.voice_presets = self._load_json(VOICE_PRESETS_FILE, [])
        self._ensure_system_categories()
        self._ensure_default_stations()

    def _ensure_system_categories(self):
        existing_ids = {c["id"] for c in self.categories}
        for def_cat in DEFAULT_CATEGORIES:
            if def_cat["id"] not in existing_ids:
                self.categories.append(def_cat)

    def _ensure_default_stations(self):
        broken_url_map = {
            "https://radiorecord.hostingradio.ru/rr_96.aacp": "https://hls-01-radiorecord.hostingradio.ru/record/playlist.m3u8",
            "http://radiorecord.hostingradio.ru/rr_96.aacp": "https://hls-01-radiorecord.hostingradio.ru/record/playlist.m3u8",
            "https://icecast-vgtrk.cdnvideo.ru/rockfm_mp3_128kbps": "https://nashe1.hostingradio.ru/rock-128.mp3",
            "http://icecast-vgtrk.cdnvideo.ru/rockfm_mp3_128kbps": "https://nashe1.hostingradio.ru/rock-128.mp3",
            "https://dfm.hostingradio.ru/dfm96.aacp": "https://dfm.hostingradio.ru/dfm128.mp3",
            "https://stream.nightride.fm/nightride.m4a": "https://stream.nightride.fm/nightride.mp3",
            "https://stream.zeno.fm/f3wvbbqmdg8uv": "http://stream.laut.fm/lofi",
        }
        modified = False
        existing_ids = {s.get("id") for s in self.stations}
        for s in self.stations:
            curr_url = s.get("url", "")
            if curr_url in broken_url_map:
                s["url"] = broken_url_map[curr_url]
                modified = True

        for def_st in DEFAULT_STATIONS:
            if def_st["id"] not in existing_ids:
                self.stations.append(def_st)
                modified = True
        if modified:
            self.save_stations()

    def _load_json(self, path: Path, default: Any) -> Any:
        try:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(default, dict) and isinstance(data, dict):
                        merged = default.copy()
                        merged.update(data)
                        return merged
                    return data
        except Exception as e:
            print(f"[ConfigManager] Error reading {path}: {e}")
        return default

    def _save_json(self, path: Path, data: Any):
        try:
            temp_path = path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            temp_path.replace(path)
        except Exception as e:
            print(f"[ConfigManager] Error saving {path}: {e}")

    def save_config(self):
        self._save_json(CONFIG_FILE, self.config)

    def save_sounds(self):
        self._save_json(SOUNDS_FILE, self.sounds)

    def save_categories(self):
        self._save_json(CATEGORIES_FILE, self.categories)

    def get_categories(self) -> List[Dict[str, Any]]:
        return list(self.categories)

    def add_category(self, name: str, position: Optional[int] = None) -> Optional[Dict[str, Any]]:
        name_clean = name.strip()
        if not name_clean:
            return None
        # Check if already exists
        for c in self.categories:
            if c.get("name", "").lower() == name_clean.lower():
                return c
        cat_id = name_clean.upper().replace(" ", "_")
        base_id = cat_id
        counter = 1
        existing_ids = {c["id"] for c in self.categories}
        while cat_id in existing_ids:
            cat_id = f"{base_id}_{counter}"
            counter += 1
        new_cat = {"id": cat_id, "name": name_clean, "system": False}
        if position is not None and 0 <= position <= len(self.categories):
            self.categories.insert(position, new_cat)
        else:
            self.categories.append(new_cat)
        self.save_categories()
        return new_cat

    def batch_add_sounds(self, sound_items: List[Dict[str, Any]]) -> int:
        """Adds multiple sound items and saves config in a single disk write."""
        added = 0
        for s in sound_items:
            existing = next((item for item in self.sounds if item.get("path") == s.get("path")), None)
            if existing:
                if s.get("category"):
                    existing["category"] = s.get("category")
            else:
                self.sounds.append(s)
                added += 1
        self.save_sounds()
        return added

    def rename_category(self, cat_id: str, new_name: str) -> bool:
        new_name_clean = new_name.strip()
        if not new_name_clean:
            return False
        cat = next((c for c in self.categories if c.get("id") == cat_id), None)
        if not cat or cat.get("system", False):
            return False
        old_name = cat.get("name", "")
        cat["name"] = new_name_clean
        self.save_categories()

        # Update any sounds referencing old_name as category
        for s in self.sounds:
            scat = str(s.get("category", ""))
            if scat.upper() in (cat_id.upper(), old_name.upper()):
                s["category"] = cat_id
        self.save_sounds()
        return True

    def remove_category(self, cat_id: str, delete_sounds: bool = False) -> bool:
        cat = next((c for c in self.categories if c.get("id") == cat_id), None)
        if not cat or cat.get("system", False):
            return False
        self.categories = [c for c in self.categories if c.get("id") != cat_id]
        self.save_categories()

        if delete_sounds:
            # Delete all sounds belonging to this category
            self.sounds = [s for s in self.sounds if str(s.get("category", "")).upper() != cat_id.upper()]
        else:
            # Safely migrate any sounds in this category to SFX (visible in "ALL")
            for s in self.sounds:
                if str(s.get("category", "")).upper() == cat_id.upper():
                    s["category"] = "SFX"
        self.save_sounds()
        return True

    def save_stations(self):
        self._save_json(STATIONS_FILE, self.stations)

    def add_station(self, name: str, url: str, genre: str = "Radio", desc: str = "") -> Optional[Dict[str, Any]]:
        name_clean = name.strip()
        url_clean = url.strip()
        if not name_clean or not url_clean:
            return None
        st_id = f"st_{int(time.time() * 1000)}" if 'time' in globals() else f"st_{len(self.stations)+1}"
        new_st = {
            "id": st_id,
            "name": name_clean,
            "url": url_clean,
            "genre": genre.strip() or "Custom",
            "description": desc.strip()
        }
        self.stations.append(new_st)
        self.save_stations()
        return new_st

    def remove_station(self, station_id: str) -> bool:
        initial_len = len(self.stations)
        self.stations = [s for s in self.stations if s.get("id") != station_id]
        if len(self.stations) < initial_len:
            self.save_stations()
            return True
        return False

    def save_tts_presets(self):
        self._save_json(TTS_PRESETS_FILE, self.tts_presets)

    def add_tts_preset(self, text: str, voice: str = "ru-RU-DmitryNeural", fx: str = "normal") -> Optional[Dict[str, Any]]:
        text_clean = text.strip()
        if not text_clean:
            return None
        preset_id = f"tts_custom_{len(self.tts_presets) + 1}"
        preset = {
            "id": preset_id,
            "text": text_clean,
            "voice": voice,
            "fx": fx,
            "system": False
        }
        self.tts_presets.append(preset)
        self.save_tts_presets()
        return preset

    def remove_tts_preset(self, preset_id: str) -> bool:
        initial_len = len(self.tts_presets)
        self.tts_presets = [p for p in self.tts_presets if p.get("id") != preset_id]
        if len(self.tts_presets) < initial_len:
            self.save_tts_presets()
            return True
        return False

    def update_tts_preset(self, preset_id: str, updates: Dict[str, Any]) -> bool:
        for p in self.tts_presets:
            if p.get("id") == preset_id:
                p.update(updates)
                self.save_tts_presets()
                return True
        return False

    def get_recordings_dir(self) -> Path:
        dir_str = self.get("recordings_dir")
        if dir_str:
            p = Path(dir_str)
        else:
            p = Path(__file__).parent.parent / "recordings"
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception:
            p = Path(__file__).parent.parent / "recordings"
            p.mkdir(parents=True, exist_ok=True)
        return p

    def save_voice_presets(self):
        self._save_json(VOICE_PRESETS_FILE, self.voice_presets)

    def add_voice_preset(self, name: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        name_clean = name.strip()
        if not name_clean:
            return None
        preset_id = f"vp_{len(self.voice_presets) + 1}"
        preset = {
            "id": preset_id,
            "name": name_clean,
            "params": dict(params),
            "custom": True
        }
        self.voice_presets.append(preset)
        self.save_voice_presets()
        return preset

    def remove_voice_preset(self, preset_id: str) -> bool:
        initial_len = len(self.voice_presets)
        self.voice_presets = [p for p in self.voice_presets if p.get("id") != preset_id]
        if len(self.voice_presets) < initial_len:
            self.save_voice_presets()
            return True
        return False

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        self.config[key] = value
        self.save_config()

    def add_sound(self, sound_data: Dict[str, Any]):
        self.sounds.append(sound_data)
        self.save_sounds()

    def remove_sound(self, sound_id: str):
        self.sounds = [s for s in self.sounds if s.get("id") != sound_id]
        self.save_sounds()

    def update_sound(self, sound_id: str, updates: Dict[str, Any]):
        for s in self.sounds:
            if s.get("id") == sound_id:
                s.update(updates)
                break
        self.save_sounds()
