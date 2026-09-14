"""AI VTuber - Microphone Input Module"""

import logging
import queue
import numpy as np
import threading
from collections import deque
from typing import Optional

logger = logging.getLogger(__name__)


class Microphone:
    """Microphone input handler using sounddevice.
    
    Provides non-blocking audio capture with circular buffer.
    
    OPTIMIZATION: Uses deque for efficient bounded buffer instead of list slicing.
    FIX: Uses queue.Queue for collect_speech() to ensure each chunk is consumed exactly once.
    """

    def __init__(self, config: dict) -> None:
        self.device_index: int = config.get("microphone_index", -1)
        self.chunk_size: int = config.get("chunk_size", 1024)
        self.channels: int = config.get("channels", 1)
        self.sample_rate: int = 16000  # Required for Whisper
        self.mute_during_playback: bool = config.get("mute_during_playback", True)

        self._stream = None
        # OPTIMIZATION: Use deque with maxlen for efficient bounded buffer
        # No manual slicing needed, automatically discards old items
        # This is used by read_chunk() for interruption checking
        self._buffer: deque = deque(maxlen=int(10 * self.sample_rate / self.chunk_size))
        self._speech_buffer: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._is_recording: bool = False
        self._muted: bool = False
        # FIX: Queue for collect_speech() to consume chunks one-by-one without duplicates
        self._chunk_queue: queue.Queue = queue.Queue()

    def start(self) -> None:
        """Start microphone capture."""
        try:
            import sounddevice as sd

            device = self.device_index if self.device_index >= 0 else None

            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype='int16',
                blocksize=self.chunk_size,
                device=device,
                callback=self._audio_callback
            )
            self._stream.start()
            self._is_recording = True
            logger.info(f"Microphone started (device: {device or 'default'}, rate: {self.sample_rate}Hz)")

        except Exception as e:
            logger.error(f"Failed to start microphone: {e}")
            raise

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        """Callback for audio stream."""
        if status:
            logger.warning(f"Audio callback status: {status}")

        if self._muted:
            return

        with self._lock:
            # Keep a rolling buffer of recent audio
            # OPTIMIZATION: deque with maxlen automatically discards old items
            # No need for manual slicing which creates copies
            self._buffer.append(indata.copy().flatten())
        
        # FIX: Also push to queue for collect_speech() to consume without duplicates
        try:
            self._chunk_queue.put_nowait(indata.copy().flatten())
        except queue.Full:
            # Queue is full, drop oldest (shouldn't happen with unbounded queue)
            pass

    def read_chunk(self) -> Optional[np.ndarray]:
        """Read the most recent audio chunk.
        
        Returns:
            numpy array of audio samples, or None if no data available.
        """
        with self._lock:
            if not self._buffer:
                return None
            chunk = self._buffer[-1].copy()
            return chunk

    def get_speech_buffer(self) -> Optional[np.ndarray]:
        """Get accumulated speech buffer."""
        with self._lock:
            if not self._speech_buffer:
                return None
            return np.concatenate(self._speech_buffer)

    def collect_speech(self, vad, silence_duration: float = 1.5,
                       min_duration: float = 0.3) -> Optional[np.ndarray]:
        """Collect speech audio until silence is detected.
        
        This blocks the calling thread until speech ends.
        
        Args:
            vad: VoiceActivityDetector instance
            silence_duration: Seconds of silence to end speech
            min_duration: Minimum speech duration in seconds
            
        Returns:
            numpy array of speech audio, or None if too short.
        """
        speech_chunks = []
        silence_start = None
        min_chunks = int(min_duration * self.sample_rate / self.chunk_size)
        silence_chunks = int(silence_duration * self.sample_rate / self.chunk_size)

        while self._is_recording:
            # FIX: Use queue.get() to block until new audio arrives - no busy-polling
            # Each chunk is consumed exactly once from the queue
            try:
                chunk = self._chunk_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            is_speech = vad.is_speech(chunk)

            if is_speech:
                speech_chunks.append(chunk)
                silence_start = None
            else:
                if speech_chunks:
                    speech_chunks.append(chunk)  # Include trailing silence
                    if silence_start is None:
                        silence_start = len(speech_chunks)
                    elif len(speech_chunks) - silence_start >= silence_chunks:
                        break

            # Prevent infinite loop
            if len(speech_chunks) > 1000:  # ~10 seconds max
                break

        if len(speech_chunks) < min_chunks:
            return None

        return np.concatenate(speech_chunks).astype(np.float32) / 32768.0

    def mute(self) -> None:
        """Mute microphone (ignore incoming audio)."""
        self._muted = True

    def _clear_chunk_queue(self) -> None:
        """Clear the chunk queue to prevent stale audio buildup."""
        while not self._chunk_queue.empty():
            try:
                self._chunk_queue.get_nowait()
            except queue.Empty:
                break

    def clear_chunk_queue(self) -> None:
        """Public method to clear the chunk queue (called at start of listening cycle)."""
        self._clear_chunk_queue()

    def unmute(self) -> None:
        """Unmute microphone."""
        self._muted = False
        with self._lock:
            self._buffer.clear()
        # FIX: Also clear the chunk queue to prevent stale audio
        self._clear_chunk_queue()
    
    def is_muted(self) -> bool:
        """Check if microphone is currently muted."""
        return self._muted

    def stop(self) -> None:
        """Stop microphone capture."""
        self._is_recording = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        logger.info("Microphone stopped")

    @property
    def is_recording(self) -> bool:
        """Check if microphone is recording."""
        return self._is_recording and self._stream is not None
