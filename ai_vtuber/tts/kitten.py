"""AI VTuber - KittenTTS Module"""

import logging
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)


class KittenTTS:
    """Text-to-speech using KittenTTS with configurable voice and speed."""

    def __init__(self, config: dict) -> None:
        self.model_name: str = config.get("model", "KittenML/kitten-tts-mini-0.8")
        self.voice: str = config.get("voice", "Bella")
        self.speed: float = config.get("speed", 1.0)
        self.backend: str = config.get("backend", "cpu")
        self.sample_rate: int = config.get("sample_rate", 24000)

        self._model = None
        self._load_model()

    def _load_model(self) -> None:
        """Load the KittenTTS model."""
        try:
            from kittentts import KittenTTS as KittenModel

            logger.info(f"Loading KittenTTS model '{self.model_name}' (backend: {self.backend})")

            if self.backend == "cuda":
                self._model = KittenModel(self.model_name, backend="cuda")
            else:
                self._model = KittenModel(self.model_name)

            # Validate voice
            available = self._model.available_voices
            if self.voice not in available:
                logger.warning(
                    f"Voice '{self.voice}' not available. "
                    f"Available: {available}. Using '{available[0]}'."
                )
                self.voice = available[0]

            logger.info(f"KittenTTS loaded. Voice: {self.voice}, Speed: {self.speed}")

        except ImportError:
            logger.error("kittentts not installed. Install with: pip install kittentts")
            raise
        except Exception as e:
            logger.error(f"Failed to load KittenTTS: {e}")
            raise

    def generate(self, text: str) -> Optional[np.ndarray]:
        """Generate speech audio from text.
        
        Args:
            text: Text to synthesize.
            
        Returns:
            numpy array of audio samples (float32 at sample_rate), or None on error.
        """
        if self._model is None:
            logger.error("KittenTTS model not loaded")
            return None

        if not text or not text.strip():
            return None

        try:
            logger.debug(f"Generating TTS for: {text[:50]}...")
            audio = self._model.generate(
                text=text,
                voice=self.voice,
                speed=self.speed,
                clean_text=True
            )
            logger.debug(f"TTS generated: {len(audio)} samples")
            return audio

        except Exception as e:
            logger.error(f"TTS generation failed: {e}")
            return None

    def generate_to_file(self, text: str, output_path: str) -> bool:
        """Generate speech and save to file.
        
        Args:
            text: Text to synthesize.
            output_path: Path to save the audio file.
            
        Returns:
            True if successful, False otherwise.
        """
        if self._model is None:
            return False

        try:
            self._model.generate_to_file(
                text=text,
                output_path=output_path,
                voice=self.voice,
                speed=self.speed,
                sample_rate=self.sample_rate,
                clean_text=True
            )
            return True
        except Exception as e:
            logger.error(f"TTS file generation failed: {e}")
            return False

    @property
    def available_voices(self) -> list[str]:
        """Get list of available voices."""
        if self._model:
            return self._model.available_voices
        return []

    def unload(self) -> None:
        """Unload the model to free memory."""
        self._model = None
        logger.info("KittenTTS model unloaded")

    @property
    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._model is not None
