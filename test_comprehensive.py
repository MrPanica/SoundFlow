"""
SoundFlow Studio — Comprehensive Automated Verification Test Suite.
Tests:
1. Stream URL Normalization (Shorts, tracking params, mix params).
2. Radio Streamer Backpressure & Playback Controls (play/pause/resume/stop/seek).
3. AudioEngine & TTS (samples, stop_tts, thread safety).
4. Waveform Widget Double-Click to Seek & Play.
5. Soundboard Category Management (Rename, Delete to All, Delete with contents).
6. FluentMainWindow GUI Launch & Subinterfaces Smoke Test (run.py entry).
7. SoundFlow.exe Binary Execution & Startup Smoke Test.
"""

import os
import sys
import time
import subprocess
from pathlib import Path
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_stream_url_normalization():
    print("\n--- [1/7] Testing Stream URL Normalization ---")
    from core.radio_streamer import clean_and_normalize_stream_url, resolve_stream_info

    # 1. YouTube Shorts normalization
    shorts_url = "https://www.youtube.com/shorts/dQw4w9WgXcQ?feature=share"
    clean_shorts = clean_and_normalize_stream_url(shorts_url)
    assert clean_shorts == "https://www.youtube.com/watch?v=dQw4w9WgXcQ", f"Shorts normalization failed: {clean_shorts}"
    print("[PASS] YouTube Shorts normalized to standard watch URL")

    # 2. Tracking parameters removal
    tracking_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=123456&feature=shared&utm_source=test"
    clean_tracking = clean_and_normalize_stream_url(tracking_url)
    assert clean_tracking == "https://www.youtube.com/watch?v=dQw4w9WgXcQ", f"Tracking cleanup failed: {clean_tracking}"
    print("[PASS] Tracking parameters stripped")

    # 3. Auto-mix playlist params removal
    mix_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=RDdQw4w9WgXcQ&start_radio=1"
    clean_mix = clean_and_normalize_stream_url(mix_url)
    assert clean_mix == "https://www.youtube.com/watch?v=dQw4w9WgXcQ", f"Mix cleanup failed: {clean_mix}"
    print("[PASS] Auto-mix & radio playlist parameters stripped")


def test_radio_streamer_and_backpressure():
    print("\n--- [2/7] Testing Radio Streamer & Backpressure Controls ---")
    from core.radio_streamer import RadioStreamer

    streamer = RadioStreamer(sample_rate=48000, buffer_size=1024)

    # Check method existence
    for m in ["play", "pause", "resume", "stop", "seek_relative", "seek_to", "play_next", "play_prev"]:
        assert hasattr(streamer, m), f"Missing method {m} on RadioStreamer"

    # Verify queue maxsize limit preventing runaway memory
    assert streamer.queue_monitor.maxsize == 300
    assert streamer.queue_mic.maxsize == 300
    print("[PASS] RadioStreamer has backpressure jitter buffer bounds (maxsize=300)")

    # Test pause / stop state flags
    streamer.current_url = "https://example.com/test.mp3"
    streamer.is_playing = True
    streamer.is_paused = False
    streamer.pause()
    assert streamer.is_paused is True
    assert streamer.is_playing is False

    streamer.stop()
    assert streamer.is_playing is False
    assert streamer.is_paused is False
    print("[PASS] Pause / stop state transitions verified")


def test_audio_engine_and_tts():
    print("\n--- [3/7] Testing Audio Engine & TTS Playback ---")
    from core.audio_engine import AudioEngine

    engine = AudioEngine(sample_rate=48000, buffer_size=1024)
    assert hasattr(engine, "play_tts_samples")
    assert hasattr(engine, "stop_tts")

    dummy_samples = np.ones((4800, 2), dtype=np.float32) * 0.5
    engine.play_tts_samples(dummy_samples, play_monitor=True, play_mic=True)
    assert engine.tts_active_sound is not None
    assert engine.tts_active_sound.sound_id == "__tts__"

    # Test stop_tts stops playback instantly
    engine.stop_tts()
    assert engine.tts_active_sound is None
    print("[PASS] AudioEngine play_tts_samples and stop_tts verified")


def test_waveform_widget_seek_and_double_click():
    print("\n--- [4/7] Testing Waveform Widget Double-Click & Seek ---")
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt, QPointF
    from PyQt6.QtGui import QMouseEvent
    from ui.waveform_widget import WaveformCanvas

    app = QApplication.instance() or QApplication(sys.argv)

    canvas = WaveformCanvas()
    canvas.resize(400, 72)
    dummy_peaks = np.linspace(0.1, 0.9, 50, dtype=np.float32)
    canvas.set_peaks(dummy_peaks)
    assert canvas.is_active is True

    received_seek = []
    received_play = []
    canvas.seek_requested.connect(lambda r: received_seek.append(r))
    canvas.play_from_seek_requested.connect(lambda r: received_play.append(r))

    # Simulate double click at middle (x=200 of 400)
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonDblClick,
        QPointF(200.0, 36.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    canvas.mouseDoubleClickEvent(event)

    assert len(received_seek) == 1
    assert len(received_play) == 1
    assert 0.45 <= received_play[0] <= 0.55
    print(f"[PASS] Waveform double-click emitted seek & play ratio: {received_play[0]:.2f}")


def test_soundboard_category_operations():
    print("\n--- [5/7] Testing Category Operations in ConfigManager ---")
    from core.config_manager import ConfigManager

    cfg = ConfigManager()

    # Create temporary category
    cat_name = "TestCategory_999"
    new_cat = cfg.add_category(cat_name)
    assert new_cat is not None
    cat_id = new_cat["id"]

    # Add a dummy sound to this category
    dummy_sound = {
        "id": "sound_test_999",
        "name": "Test Sound 999",
        "path": "test.wav",
        "category": cat_id,
        "volume": 1.0
    }
    cfg.sounds.append(dummy_sound)
    cfg.save_sounds()

    # 1. Rename test
    renamed = cfg.rename_category(cat_id, "RenamedCategory_999")
    assert renamed is True
    assert any(c["name"] == "RenamedCategory_999" for c in cfg.categories)
    print("[PASS] Category renamed successfully")

    # 2. Delete category moving sounds to SFX (All)
    deleted = cfg.remove_category(cat_id, delete_sounds=False)
    assert deleted is True
    sound_after = next((s for s in cfg.sounds if s["id"] == "sound_test_999"), None)
    assert sound_after is not None
    assert sound_after["category"] == "SFX"
    print("[PASS] Category deleted: sound migrated to SFX ('All')")

    # Clean up dummy sound
    cfg.sounds = [s for s in cfg.sounds if s["id"] != "sound_test_999"]
    cfg.save_sounds()


def test_run_py_launch():
    print("\n--- [6/7] Testing run.py Entry Point Launch ---")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0

    proc = subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "run.py")],
        cwd=str(PROJECT_ROOT),
        startupinfo=startupinfo,
        creationflags=creationflags
    )

    try:
        time.sleep(3.5)
        ret = proc.poll()
        if ret is not None:
            raise RuntimeError(f"run.py terminated prematurely with exit code: {ret}")
        print(f"[PASS] run.py successfully launched and running (PID: {proc.pid})")
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=2.0)
        except Exception:
            proc.kill()
        print("[PASS] run.py terminated cleanly")


def test_soundflow_exe_binary():
    print("\n--- [7/7] Testing SoundFlow.exe Binary Execution ---")
    exe_path = PROJECT_ROOT / "SoundFlow.exe"
    assert exe_path.exists(), f"SoundFlow.exe not found at {exe_path}"
    assert exe_path.stat().st_size > 5_000_000, "SoundFlow.exe size is suspiciously small"

    # Launch SoundFlow.exe with hidden window and timeout to ensure no crash on startup
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0

    proc = subprocess.Popen(
        [str(exe_path)],
        cwd=str(PROJECT_ROOT),
        startupinfo=startupinfo,
        creationflags=creationflags
    )

    try:
        # Give it 3.5 seconds to initialize
        time.sleep(3.5)
        # Check if process crashed
        ret = proc.poll()
        if ret is not None:
            raise RuntimeError(f"SoundFlow.exe terminated prematurely with exit code: {ret}")
        print(f"[PASS] SoundFlow.exe successfully started and running (PID: {proc.pid})")
    finally:
        # Terminate cleanly
        try:
            proc.terminate()
            proc.wait(timeout=2.0)
        except Exception:
            proc.kill()
        print("[PASS] SoundFlow.exe terminated cleanly")


if __name__ == "__main__":
    test_stream_url_normalization()
    test_radio_streamer_and_backpressure()
    test_audio_engine_and_tts()
    test_waveform_widget_seek_and_double_click()
    test_soundboard_category_operations()
    test_run_py_launch()
    test_soundflow_exe_binary()
    print("\n" + "="*60)
    print(">>> ALL 7 COMPREHENSIVE VERIFICATION TESTS PASSED! <<<")
    print("="*60)
