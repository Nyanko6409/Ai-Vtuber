"""AI VTuber - Audio Playback Module

Cross-platform audio playback using sounddevice.
Supports Windows, Linux, WSL, and macOS.

OPTIMIZATION: Uses streaming playback instead of temporary WAV files.
"""

import logging
import numpy as np
import threading
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class AudioPlayer:
    """Audio playback with interruption support using sounddevice."""

    def __init__(self, config: dict) -> None:
        self.sample_rate: int = config.get("sample_rate", 24000)
        self._is_playing: bool = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._stream = None
        
        # Initialize sounddevice
        try:
            import sounddevice as sd
            logger.debug(f"SoundDevice available at {self.sample_rate}Hz")
        except Exception as e:
            logger.warning(f"Failed to initialize sounddevice: {e}")

    def play(self, audio_data: np.ndarray,
             interrupt_check: Optional[Callable[[], bool]] = None,
             check_interval: float = 0.1,
             on_start: Optional[Callable[[], None]] = None,
             on_end: Optional[Callable[[], None]] = None) -> None:
        """Play audio data with optional interruption support and callbacks using sounddevice.
        
        Args:
            audio_data: numpy array of audio samples (float32 at sample_rate)
            interrupt_check: Optional callback that returns True to stop playback
            check_interval: How often to check for interruption (seconds)
            on_start: Optional callback called when playback starts
            on_end: Optional callback called when playback ends (normal or interrupted)
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
            
            # Create a copy for playback
            audio_copy = audio_data.copy()
            total_frames = len(audio_copy)
            frame_index = [0]  # Use list for mutable closure
            
            # Define callback for streaming playback
            def audio_callback(outdata, frames, time, status):
                if status:
                    logger.warning(f"Audio stream status: {status}")
                
                remaining = total_frames - frame_index[0]
                if remaining == 0:
                    raise sd.CallbackStop()
                
                chunk = min(frames, remaining)
                outdata[:chunk] = audio_copy[frame_index[0]:frame_index[0] + chunk]
                frame_index[0] += chunk
                
                if remaining <= frames:
                    raise sd.CallbackStop()
            
            # Start streaming playback
            self._stream = sd.Stream(
                samplerate=self.sample_rate,
                channels=1,
                dtype=np.float32,
                callback=audio_callback
            )
            self._stream.start()
            
            # Call on_start callback after playback begins
            if on_start:
                on_start()
            
            # Wait for completion or interruption
            total_duration = len(audio_data) / self.sample_rate
            elapsed = 0
            
            while elapsed < total_duration:
                if self._stop_event.is_set():
                    logger.debug("Playback stopped by stop event")
                    break
                
                if interrupt_check and interrupt_check():
                    logger.info("Playback interrupted by user")
                    self._stop_event.set()
                    break
                
                # Check stream status
                if self._stream and not self._stream.active:
                    break
                    
                import time
                time.sleep(check_interval)
                elapsed += check_interval

        except Exception as e:
            logger.error(f"Audio playback failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            # Stop and close stream
            if self._stream:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
            
            with self._lock:
                self._is_playing = False
            
            # Call on_end callback when playback finishes
            if on_end:
                on_end()

    def stop(self) -> None:
        """Stop current playback immediately."""
        self._stop_event.set()
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        with self._lock:
            self._is_playing = False
        logger.debug("Audio playback stopped")

    @property
    def is_playing(self) -> bool:
        """Check if audio is currently playing."""
        with self._lock:
            return self._is_playing
