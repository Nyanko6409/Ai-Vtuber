"""AI VTuber - faster-whisper STT Module"""

import logging
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)


class WhisperSTT:
    """Speech-to-text using faster-whisper with CUDA/CPU support."""

    def __init__(self, config: dict) -> None:
        self.model_size: str = config["model_size"]
        self.device: str = config.get("device", "auto")
        self.compute_type: str = config.get("compute_type", "auto")
        self.language: str = config.get("language", "en")
        self.beam_size: int = config.get("beam_size", 5)
        self.sample_rate: int = config.get("sample_rate", 16000)

        self._model = None
        self._load_model()

    def _load_model(self) -> None:
        """Load the faster-whisper model."""
        try:
            from faster_whisper import WhisperModel

            # Determine device and compute type
            device = self.device
            compute_type = self.compute_type

            if device == "auto":
                try:
                    import torch
                    if torch.cuda.is_available():
                        device = "cuda"
                        compute_type = "float16" if compute_type == "auto" else compute_type
                        logger.info("CUDA detected, using GPU acceleration")
                    else:
                        device = "cpu"
                        compute_type = "int8" if compute_type == "auto" else compute_type
                        logger.info("No CUDA detected, using CPU")
                except ImportError:
                    device = "cpu"
                    compute_type = "int8" if compute_type == "auto" else compute_type
                    logger.info("torch not available, using CPU with int8")

            logger.info(f"Loading Whisper model '{self.model_size}' on {device} ({compute_type})")
            self._model = WhisperModel(
                self.model_size,
                device=device,
                compute_type=compute_type
            )
            logger.info("Whisper model loaded successfully")

        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise

    def transcribe(self, audio_data: np.ndarray) -> str:
        """Transcribe audio data to text.
        
        Args:
            audio_data: numpy array of audio samples (float32, mono, at sample_rate)
            
        Returns:
            Transcribed text string.
        """
        if self._model is None:
            raise RuntimeError("Whisper model not loaded")

        try:
            # Ensure audio is float32
            if audio_data.dtype != np.float32:
                if audio_data.dtype == np.int16:
                    audio_data = audio_data.astype(np.float32) / 32768.0
                else:
                    audio_data = audio_data.astype(np.float32)

            # Transcribe
            segments, info = self._model.transcribe(
                audio_data,
                language=self.language,
                beam_size=self.beam_size,
                vad_filter=True,
                vad_parameters=dict(
                    min_speech_duration_ms=300,
                    min_silence_duration_ms=500,
                )
            )

            # Collect all segments
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text.strip())

            result = " ".join(text_parts).strip()
            logger.debug(f"Transcription: {result}")
            return result

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise

    def unload(self) -> None:
        """Unload the model to free memory."""
        self._model = None
        logger.info("Whisper model unloaded")

    @property
    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._model is not None
