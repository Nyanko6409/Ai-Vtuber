"""AI VTuber - Audio Playback Module"""

import logging
import numpy as np
import threading
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class AudioPlayer:
    """Audio playback with interruption support using sounddevice."""

    def __init__(self, config: dict) -> None:
        self.sample_rate: int = config.get("sample_rate", 24000)
        self._stream = None
        self._is_playing: bool = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def play(self, audio_data: np.ndarray,
             interrupt_check: Optional[Callable[[], bool]] = None,
             check_interval: float = 0.1) -> None:
        """Play audio data with optional interruption support.
        
        Args:
            audio_data: numpy array of audio samples (float32 at sample_rate)
            interrupt_check: Optional callback that returns True to stop playback
            check_interval: How often to check for interruption (seconds)
        """
        self._stop_event.clear()

        with self._lock:
            self._is_playing = True

        try:
            import sounddevice as sd

            # Convert to appropriate format
            if audio_data.dtype != np.float32:
                audio_data = audio_data.astype(np.float32)

            # Normalize if needed
            max_val = np.max(np.abs(audio_data))
            if max_val > 1.0:
                audio_data = audio_data / max_val

            # Calculate total duration
            total_samples = len(audio_data)
            total_duration = total_samples / self.sample_rate

            # Play in chunks for interruption support
            chunk_duration = check_interval
            chunk_samples = int(chunk_duration * self.sample_rate)
            samples_played = 0

            while samples_played < total_samples:
                # Check for interruption
                if self._stop_event.is_set():
                    logger.debug("Playback stopped by stop event")
                    break

                if interrupt_check and interrupt_check():
                    logger.info("Playback interrupted by user")
                    self._stop_event.set()
                    break

                # Get next chunk
                end = min(samples_played + chunk_samples, total_samples)
                chunk = audio_data[samples_played:end]

                # Play chunk
                try:
                    sd.play(chunk, samplerate=self.sample_rate)
                    sd.wait()
                except Exception as e:
                    logger.error(f"Playback error: {e}")
                    break

                samples_played = end

        except ImportError:
            logger.error("sounddevice not installed. Install with: pip install sounddevice")
        except Exception as e:
            logger.error(f"Audio playback failed: {e}")
        finally:
            with self._lock:
                self._is_playing = False
            try:
                import sounddevice as sd
                sd.stop()
            except Exception:
                pass

    def stop(self) -> None:
        """Stop current playback immediately."""
        self._stop_event.set()
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass
        with self._lock:
            self._is_playing = False
        logger.debug("Audio playback stopped")

    @property
    def is_playing(self) -> bool:
        """Check if audio is currently playing."""
        with self._lock:
            return self._is_playing
