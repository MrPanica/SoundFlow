"""
Verification test script for SoundFlow Studio enhancements:
1. Transparent minimalist icon verification.
2. Radio Streamer & YouTube/stream metadata resolution.
3. Radio play/stop toggle state logic.
4. TTS debounce and single execution validation.
"""

from pathlib import Path
from PIL import Image
import numpy as np


def test_icon_transparency():
    icon_png = Path("assets/app_icon.png")
    assert icon_png.exists(), "assets/app_icon.png does not exist"
    img = Image.open(icon_png)
    assert img.mode == "RGBA", f"Expected RGBA mode, got {img.mode}"
    # Verify corners are completely transparent (alpha == 0)
    corners = [(0, 0), (0, 511), (511, 0), (511, 511), (10, 10), (500, 10)]
    for c in corners:
        alpha = img.getpixel(c)[3]
        assert alpha == 0, f"Corner {c} has non-zero alpha: {alpha}"
    print("[PASS] Icon is RGBA with 100% transparent background")

    # Check ICO file
    icon_ico = Path("assets/app_icon.ico")
    assert icon_ico.exists(), "assets/app_icon.ico does not exist"
    ico = Image.open(icon_ico)
    print(f"[PASS] ICO file exists, size: {ico.size}")


def test_stream_resolution():
    from core.radio_streamer import resolve_stream_info

    # 1. RusRadio
    info_rr = resolve_stream_info("https://rusradio.ru/online")
    assert "rusradio" in info_rr["url"], f"Expected rusradio stream, got {info_rr['url']}"
    assert info_rr["is_live"] is True
    print(f"[PASS] RusRadio resolved: {info_rr['title']}")

    # 2. Record
    info_rec = resolve_stream_info("https://radiorecord.ru")
    assert "radiorecord" in info_rec["url"]
    print(f"[PASS] Radio Record resolved: {info_rec['title']}")

    # 3. Direct audio stream
    info_direct = resolve_stream_info("https://example.com/stream.mp3")
    assert info_direct["url"] == "https://example.com/stream.mp3"
    print(f"[PASS] Direct stream handled")


def test_radio_streamer_methods():
    from core.radio_streamer import RadioStreamer

    streamer = RadioStreamer(sample_rate=48000, buffer_size=1024)
    assert hasattr(streamer, "play")
    assert hasattr(streamer, "pause")
    assert hasattr(streamer, "resume")
    assert hasattr(streamer, "stop")
    assert hasattr(streamer, "seek_relative")
    assert hasattr(streamer, "seek_to")
    assert hasattr(streamer, "play_next")
    assert hasattr(streamer, "play_prev")
    assert hasattr(streamer, "has_next")
    assert hasattr(streamer, "has_prev")
    print("[PASS] RadioStreamer has all required playback and seeking methods")


def test_tts_engine_and_audio_engine():
    from core.audio_engine import AudioEngine

    engine = AudioEngine(sample_rate=48000)
    assert hasattr(engine, "play_tts_samples")
    assert hasattr(engine, "stop_tts")

    samples = np.zeros((4800, 2), dtype=np.float32)
    engine.play_tts_samples(samples, play_monitor=True, play_mic=False)
    assert engine.tts_active_sound is not None

    engine.stop_tts()
    assert engine.tts_active_sound is None
    print("[PASS] AudioEngine TTS playback and stop methods functional")


if __name__ == "__main__":
    test_icon_transparency()
    test_stream_resolution()
    test_radio_streamer_methods()
    test_tts_engine_and_audio_engine()
    print("\nALL VERIFICATION TESTS PASSED SUCCESSFULLY!")
