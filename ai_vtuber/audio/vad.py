"""AI VTuber - Voice Activity Detection Module"""

import logging
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)


class VoiceActivityDetector:
    """Voice Activity Detection using energy-based detection and webrtcvad."""

    def __init__(self, config: dict) -> None:
        self.threshold: float = config.get("vad_threshold", 0.5)
        self.sample_rate: int = config.get("sample_rate", 16000)
        self.silence_duration: float = config.get("silence_duration", 1.5)

        self._vad = None
        self._init_vad()

        # State tracking
        self._speech_frame_count: int = 0
        self._silence_frame_count: int = 0
        self._frame_size: int = int(0.03 * self.sample_rate)  # 30ms frames

    def _init_vad(self) -> None:
        """Initialize VAD engine."""
        try:
            import webrtcvad
            self._vad = webrtcvad.Vad(2)  # Aggressiveness: 0-3
            logger.info("webrtcvad initialized (aggressiveness: 2)")
        except ImportError:
            logger.warning("webrtcvad not available, using energy-based VAD only")
            self._vad = None

    def is_speech(self, audio_chunk: np.ndarray) -> bool:
        """Check if audio chunk contains speech.
        
        Args:
            audio_chunk: Audio data (int16 or float32)
            
        Returns:
            True if speech is detected.
        """
        # Convert to int16 if needed
        if audio_chunk.dtype == np.float32:
            audio_int16 = (audio_chunk * 32768).astype(np.int16)
        elif audio_chunk.dtype == np.float64:
            audio_int16 = (audio_chunk * 32768).astype(np.int16)
        else:
            audio_int16 = audio_chunk.astype(np.int16)

        # Energy-based detection
        energy = self._compute_energy(audio_int16)
        energy_speech = energy > self.threshold * 1000  # Scale threshold

        # webrtcvad detection
        webrtc_speech = False
        if self._vad is not None:
            try:
                # webrtcvad requires specific frame sizes: 10, 20, or 30ms
                frame_bytes = audio_int16.tobytes()
                frame_size = int(0.03 * self.sample_rate)  # 30ms

                if len(audio_int16) >= frame_size:
                    frame = audio_int16[:frame_size].tobytes()
                    webrtc_speech = self._vad.is_voice(frame, self.sample_rate)
            except Exception:
                # Fallback to energy-based only
                pass

        # Combine both methods
        if self._vad is not None:
            is_speech = webrtc_speech or energy_speech
        else:
            is_speech = energy_speech

        # Update state tracking
        if is_speech:
            self._speech_frame_count += 1
            self._silence_frame_count = 0
        else:
            self._silence_frame_count += 1

        return is_speech

    def check_silence(self, audio_data: np.ndarray) -> bool:
        """Check if silence has been sustained long enough to end speech.
        
        Args:
            audio_data: Recent audio data
            
        Returns:
            True if silence duration exceeded.
        """
        is_speech = self.is_speech(audio_data)
        if is_speech:
            return False

        silence_frames = self._silence_frame_count
        silence_duration = silence_frames * (self._frame_size / self.sample_rate)
        return silence_duration >= self.silence_duration

    def _compute_energy(self, audio: np.ndarray) -> float:
        """Compute RMS energy of audio signal."""
        if len(audio) == 0:
            return 0.0
        return float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))

    def reset(self) -> None:
        """Reset VAD state."""
        self._speech_frame_count = 0
        self._silence_frame_count = 0
