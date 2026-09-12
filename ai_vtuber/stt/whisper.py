"""AI VTuber - faster-whisper STT Module

Uses CTranslate2 for CUDA detection (no PyTorch dependency).
Supports automatic GPU/CPU fallback.
"""

import logging
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)


def _detect_cuda() -> bool:
    """Detect CUDA availability using CTranslate2 directly.

    Does NOT require PyTorch. Uses ctranslate2's built-in CUDA check.
    """
    try:
        import ctranslate2
        # CTranslate2 exposes CUDA availability
        cuda_supported = ctranslate2.get_cuda_device_count() > 0
        if cuda_supported:
            logger.info(f"CUDA detected via CTranslate2 ({ctranslate2.get_cuda_device_count()} device(s))")
        else:
            logger.info("No CUDA devices found via CTranslate2")
        return cuda_supported
    except ImportError:
        logger.warning("ctranslate2 not available for CUDA detection")
        return False
    except Exception as e:
        logger.warning(f"CUDA detection failed: {e}")
        return False


class WhisperSTT:
    """Speech-to-text using faster-whisper with CUDA/CPU support.

    CUDA detection uses CTranslate2 directly (no PyTorch required).
    """

    def __init__(self, config: dict) -> None:
        self.model_size: str = config.get("model_size", "base")
        self.device: str = config.get("device", "auto")
        self.compute_type: str = config.get("compute_type", "auto")
        self.language: str = config.get("language", "en")
        self.beam_size: int = config.get("beam_size", 5)
        self.sample_rate: int = config.get("sample_rate", 16000)

        self._model = None
        self._load_model()

    def _load_model(self) -> None:
        """Load the faster-whisper model with proper CUDA detection."""
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            logger.error("faster-whisper not installed. Install with: pip install faster-whisper")
            raise

        # Determine device and compute type
        device = self.device
        compute_type = self.compute_type

        if device == "auto":
            # Use CTranslate2 for CUDA detection (no PyTorch needed)
            if _detect_cuda():
                device = "cuda"
                if compute_type == "auto":
                    compute_type = "float16"
                logger.info("Using CUDA GPU acceleration")
            else:
                device = "cpu"
                if compute_type == "auto":
                    compute_type = "int8"
                logger.info("Using CPU (no CUDA available)")
        else:
            # User specified device explicitly
            if compute_type == "auto":
                if device == "cuda":
                    compute_type = "float16"
                else:
                    compute_type = "int8"

        logger.info(f"Loading Whisper model '{self.model_size}' on {device} ({compute_type})")

        try:
            self._model = WhisperModel(
                self.model_size,
                device=device,
                compute_type=compute_type
            )
            logger.info(f"Whisper model loaded successfully on {device}")
        except Exception as e:
            error_msg = str(e)
            # Check if it's a CUDA library error
            if "libcublas" in error_msg or "libcuBLAS" in error_msg or "CUDA" in error_msg or device == "cuda":
                logger.warning(f"CUDA model load failed: {e}")
                logger.info("Falling back to CPU...")
                try:
                    self._model = WhisperModel(
                        self.model_size,
                        device="cpu",
                        compute_type="int8"
                    )
                    logger.info("Whisper model loaded on CPU (fallback)")
                except Exception as e2:
                    logger.error(f"CPU fallback also failed: {e2}")
                    raise
            else:
                raise

    def transcribe(self, audio_: np.ndarray) -> str:
        """Transcribe audio data to text.

        Args:
            audio_ numpy array of audio samples (float32 or int16, mono, 16kHz)

        Returns:
            Transcribed text string.
        """
        if self._model is None:
            raise RuntimeError("Whisper model not loaded")

        try:
            # Ensure audio is float32 normalized to [-1, 1]
            if audio_.dtype == np.int16:
                audio_data = audio_.astype(np.float32) / 32768.0
            elif audio_.dtype == np.float64:
                audio_data = audio_.astype(np.float32)
            elif audio_.dtype != np.float32:
                audio_data = audio_.astype(np.float32)
            else:
                audio_data = audio_

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
            error_msg = str(e)
            # Check if it's a CUDA library error during inference
            if "libcublas" in error_msg or "libcuBLAS" in error_msg or "CUDA" in error_msg:
                logger.warning(f"CUDA inference failed: {e}")
                logger.warning("This is a WSL limitation - CUDA libraries not accessible at runtime")
                logger.info("Please set 'device: cpu' in config.yaml for STT section")
            logger.error(f"Transcription failed: {e}")
            raise

    def unload(self) -> None:
        """Unload the model to free memory."""
        self._model = None
        logger.info("Whisper model unloaded")

    @property
    def is_loaded(self) -> bool:
        return self._model is not None
