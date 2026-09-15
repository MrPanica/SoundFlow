"""
Neural Text-to-Speech Engine for SoundFlow Studio using edge-tts.
Synthesizes speech in real-time in memory and outputs decoded float32 PCM samples directly into the audio mixer.
"""

import asyncio
import threading
from typing import Optional, Callable, Dict, List
import numpy as np
import edge_tts
import miniaudio

AVAILABLE_VOICES: List[Dict[str, str]] = [
    {"id": "ru-RU-DmitryNeural", "name": "Дмитрий (Русский)", "lang": "ru"},
    {"id": "ru-RU-SvetlanaNeural", "name": "Светлана (Русский)", "lang": "ru"},
    {"id": "en-US-GuyNeural", "name": "Guy (English US)", "lang": "en"},
    {"id": "en-US-JennyNeural", "name": "Jenny (English US)", "lang": "en"},
    {"id": "en-US-AnaNeural", "name": "Ana (English Child)", "lang": "en"},
    {"id": "en-GB-RyanNeural", "name": "Ryan (English UK)", "lang": "en"},
    {"id": "de-DE-ConradNeural", "name": "Conrad (Deutsch)", "lang": "de"},
    {"id": "ja-JP-KeitaNeural", "name": "Keita (Japanese)", "lang": "ja"}
]


class TTSEngine:
    """Synthesizes text using Microsoft Neural TTS into float32 audio arrays."""

    def __init__(self, sample_rate: int = 48000):
        self.sample_rate = sample_rate

    def synthesize_async(
        self,
        text: str,
        voice: str = "ru-RU-DmitryNeural",
        rate: str = "+0%",
        pitch: str = "+0Hz",
        callback: Optional[Callable[[Optional[np.ndarray]], None]] = None
    ):
        """Asynchronously generates float32 stereo audio from text and executes callback."""
        def worker():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                samples = loop.run_until_complete(self._generate_speech(text, voice, rate, pitch))
                if callback:
                    callback(samples)
            except Exception as e:
                print(f"[TTSEngine] Generation error: {e}")
                if callback:
                    callback(None)
            finally:
                loop.close()

        threading.Thread(target=worker, daemon=True, name="SoundFlow-TTSWorker").start()

    async def _generate_speech(
        self,
        text: str,
        voice: str,
        rate: str = "+0%",
        pitch: str = "+0Hz"
    ) -> Optional[np.ndarray]:
        try:
            communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
            mp3_bytes = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_bytes.extend(chunk["data"])

            if not mp3_bytes:
                return None

            decoded = miniaudio.decode(
                bytes(mp3_bytes),
                output_format=miniaudio.SampleFormat.FLOAT32,
                nchannels=2,
                sample_rate=self.sample_rate
            )

            # Reshape into (N, 2)
            arr = np.array(decoded.samples, dtype=np.float32).reshape(-1, 2)
            return arr
        except Exception as e:
            print(f"[TTSEngine] Async synthesize error: {e}")
            return None
