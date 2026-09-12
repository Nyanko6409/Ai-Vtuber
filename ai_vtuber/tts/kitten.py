"""AI VTuber - KittenTTS Module

Supports both:
- Official KittenML package (0.8.x from GitHub wheel): KittenTTS("model_name")
- PyPI kittentts package (0.1.x): KittenTTS()

Auto-detects which version is installed and adapts API calls.
"""

import logging
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)

# Voice names for official 0.8.x package
OFFICIAL_VOICES = ["Bella", "Jasper", "Luna", "Bruno", "Rosie", "Hugo", "Kiki", "Leo"]

# Voice names for PyPI 0.1.x package
PYPI_VOICES = [
    "expr-voice-1-f", "expr-voice-2-m", "expr-voice-3-f",
    "expr-voice-4-m", "expr-voice-5-f", "expr-voice-6-m",
]


class KittenTTS:
    """Text-to-speech using KittenTTS.

    Auto-detects installed version and adapts API.
    """

    def __init__(self, config: dict) -> None:
        self.config_model: str = config.get("model", "KittenML/kitten-tts-mini-0.8")
        self.config_voice: str = config.get("voice", "Bella")
        self.config_speed: float = config.get("speed", 1.0)
        self.config_backend: str = config.get("backend", "cpu")
        self.sample_rate: int = config.get("sample_rate", 24000)

        self._model = None
        self._is_official: bool = False  # True = 0.8.x, False = 0.1.x
        self._voice: str = self.config_voice

        self._load_model()

    def _load_model(self) -> None:
        """Load the KittenTTS model, auto-detecting version."""
        try:
            from kittentts import KittenTTS as KittenModel
        except ImportError:
            logger.error(
                "kittentts not installed.\n"
                "  Option 1 (Official 0.8.x, recommended):\n"
                "    pip install https://github.com/KittenML/KittenTTS/releases/download/0.8.1/kittentts-0.8.1-py3-none-any.whl\n"
                "  Option 2 (PyPI 0.1.x):\n"
                "    pip install kittentts"
            )
            raise

        # Detect version by trying the official API
        try:
            # Official 0.8.x: KittenTTS("model_name")
            logger.info(f"Loading KittenTTS (official 0.8.x) model: {self.config_model}")
            if self.config_backend == "cuda":
                self._model = KittenModel(self.config_model, backend="cuda")
            else:
                self._model = KittenModel(self.config_model)
            self._is_official = True

            # Validate voice
            available = self._model.available_voices
            if self._voice not in available:
                logger.warning(
                    f"Voice '{self._voice}' not available. "
                    f"Available: {available}. Using '{available[0]}'."
                )
                self._voice = available[0]

            logger.info(f"KittenTTS 0.8.x loaded. Voice: {self._voice}, Speed: {self.config_speed}")
            return

        except (TypeError, AttributeError):
            # Not the official version, try PyPI 0.1.x API
            pass
        except Exception as e:
            # Official version failed to load, try fallback
            logger.warning(f"Official KittenTTS load failed: {e}, trying PyPI version...")

        # PyPI 0.1.x: KittenTTS() with no args
        try:
            logger.info("Loading KittenTTS (PyPI 0.1.x)")
            self._model = KittenModel()
            self._is_official = False

            # Map voice names
            if self._voice in OFFICIAL_VOICES:
                # Map official voice names to PyPI equivalents
                voice_map = {
                    "Bella": "expr-voice-1-f",
                    "Jasper": "expr-voice-2-m",
                    "Luna": "expr-voice-3-f",
                    "Bruno": "expr-voice-4-m",
                    "Rosie": "expr-voice-5-f",
                    "Hugo": "expr-voice-6-m",
                }
                self._voice = voice_map.get(self._voice, "expr-voice-2-m")
                logger.info(f"Mapped voice to PyPI format: {self._voice}")

            logger.info(f"KittenTTS 0.1.x loaded. Voice: {self._voice}, Speed: {self.config_speed}")

        except Exception as e:
            logger.error(f"Failed to load KittenTTS: {e}")
            raise

    def generate(self, text: str) -> Optional[np.ndarray]:
        """Generate speech audio from text.

        Args:
            text: Text to synthesize.

        Returns:
            numpy array of audio samples (float32 at 24kHz), or None on error.
        """
        if self._model is None:
            logger.error("KittenTTS model not loaded")
            return None

        if not text or not text.strip():
            return None

        try:
            logger.debug(f"Generating TTS for: {text[:50]}...")

            if self._is_official:
                # Official 0.8.x API
                audio = self._model.generate(
                    text=text,
                    voice=self._voice,
                    speed=self.config_speed,
                    clean_text=True
                )
            else:
                # PyPI 0.1.x API
                audio = self._model.generate(
                    text=text,
                    voice=self._voice,
                    speed=self.config_speed
                )

            logger.debug(f"TTS generated: {len(audio)} samples")
            return audio

        except Exception as e:
            logger.error(f"TTS generation failed: {e}")
            return None

    def generate_to_file(self, text: str, output_path: str) -> bool:
        """Generate speech and save to file."""
        if self._model is None:
            return False

        try:
            if self._is_official:
                self._model.generate_to_file(
                    text=text,
                    output_path=output_path,
                    voice=self._voice,
                    speed=self.config_speed,
                    sample_rate=self.sample_rate,
                    clean_text=True
                )
            else:
                # PyPI 0.1.x: generate and save manually
                import soundfile as sf
                audio = self.generate(text)
                if audio is not None:
                    sf.write(output_path, audio, self.sample_rate)
                    return True
                return False
            return True
        except Exception as e:
            logger.error(f"TTS file generation failed: {e}")
            return False

    @property
    def available_voices(self) -> list[str]:
        """Get list of available voices."""
        if self._model and self._is_official:
            return self._model.available_voices
        elif self._is_official:
            return OFFICIAL_VOICES
        else:
            return PYPI_VOICES

    def unload(self) -> None:
        """Unload the model to free memory."""
        self._model = None
        logger.info("KittenTTS model unloaded")

    @property
    def is_loaded(self) -> bool:
        return self._model is not None
