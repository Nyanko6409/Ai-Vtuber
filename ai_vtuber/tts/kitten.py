"""AI VTuber - KittenTTS Module

Supports both:
- Official KittenML package (0.8.x from GitHub wheel): KittenTTS("model_name")
- PyPI kittentts package (0.1.x): KittenTTS()

Auto-detects which version is installed and adapts API calls.
"""

import logging
import re
import numpy as np
from typing import Optional, Iterator

logger = logging.getLogger(__name__)

# Voice names for official 0.8.x package
OFFICIAL_VOICES = ["Bella", "Jasper", "Luna", "Bruno", "Rosie", "Hugo", "Kiki", "Leo"]

# Voice names for PyPI 0.1.x package
PYPI_VOICES = [
    "expr-voice-1-f", "expr-voice-2-m", "expr-voice-3-f",
    "expr-voice-4-m", "expr-voice-5-f", "expr-voice-6-m",
]


def split_text_into_chunks(text: str, max_chunk_length: int = 200) -> list[str]:
    """Split text into smaller chunks for streaming TTS.
    
    Splits on sentence boundaries (., !, ?, ;, newline) when possible,
    while respecting the max chunk length. Each chunk will be at most
    max_chunk_length characters unless a single sentence exceeds it.
    
    Args:
        text: Text to split.
        max_chunk_length: Maximum characters per chunk (default 200).
    
    Returns:
        List of text chunks.
    """
    if not text or not text.strip():
        return []
    
    # Clean up whitespace
    text = ' '.join(text.split())
    
    # Split on sentence boundaries: . ! ? ; \n followed by space or end
    # Keep the delimiter with the sentence
    sentence_pattern = r'([.!?;]+|\n+)(?:\s+|$)'
    
    # Find all split points
    parts = re.split(sentence_pattern, text)
    
    # Reconstruct sentences with their delimiters
    sentences = []
    i = 0
    while i < len(parts):
        if i + 1 < len(parts):
            # Part + delimiter
            sentence = parts[i] + parts[i + 1]
            sentences.append(sentence.strip())
            i += 2
        else:
            # Last part without delimiter
            if parts[i].strip():
                sentences.append(parts[i].strip())
            i += 1
    
    # If no sentences found, treat whole text as one
    if not sentences:
        sentences = [text]
    
    # Group sentences into chunks respecting max length
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        if not sentence.strip():
            continue
            
        # If single sentence is longer than max, split it by length
        if len(sentence) > max_chunk_length:
            # First, finish any existing chunk
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
            
            # Split long sentence into smaller pieces
            words = sentence.split()
            current_word_chunk = ""
            for word in words:
                if len(current_word_chunk) + len(word) + 1 <= max_chunk_length:
                    if current_word_chunk:
                        current_word_chunk += " " + word
                    else:
                        current_word_chunk = word
                else:
                    if current_word_chunk:
                        chunks.append(current_word_chunk)
                    current_word_chunk = word
            if current_word_chunk:
                chunks.append(current_word_chunk)
        elif len(current_chunk) + len(sentence) + 1 <= max_chunk_length:
            # Add to current chunk
            if current_chunk:
                current_chunk += " " + sentence
            else:
                current_chunk = sentence
        else:
            # Start new chunk
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = sentence
    
    # Don't forget the last chunk
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks


class KittenTTS:
    """Text-to-speech using KittenTTS.

    Auto-detects installed version and adapts API.
    """

    def __init__(self, config: dict) -> None:
        self.config_model: str = config.get("model", "KittenML/kitten-tts-nano-0.8-int8")
        self.config_voice: str = config.get("voice", "Bella")
        self.config_speed: float = config.get("speed", 1.25)
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

    def generate_streaming(self, text: str, max_chunk_length: int = 200) -> Iterator[Optional[np.ndarray]]:
        """Generate speech audio from text in chunks for streaming playback.
        
        This splits long text into smaller chunks and yields audio for each chunk
        sequentially, allowing playback to start before the entire text is processed.
        
        Args:
            text: Text to synthesize.
            max_chunk_length: Maximum characters per chunk (default 200).
        
        Yields:
            numpy array of audio samples for each chunk, or None on error/skip.
        """
        if self._model is None:
            logger.error("KittenTTS model not loaded")
            return
        
        if not text or not text.strip():
            return
        
        # Split text into manageable chunks
        chunks = split_text_into_chunks(text, max_chunk_length)
        
        if not chunks:
            return
        
        logger.info(f"Streaming TTS: {len(chunks)} chunks from {len(text)} chars")
        
        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
                
            try:
                logger.debug(f"Chunk {i+1}/{len(chunks)}: {chunk[:50]}...")
                
                if self._is_official:
                    # Official 0.8.x API
                    audio = self._model.generate(
                        text=chunk,
                        voice=self._voice,
                        speed=self.config_speed,
                        clean_text=True
                    )
                else:
                    # PyPI 0.1.x API
                    audio = self._model.generate(
                        text=chunk,
                        voice=self._voice,
                        speed=self.config_speed
                    )
                
                logger.debug(f"Chunk {i+1} generated: {len(audio) if audio else 0} samples")
                yield audio
                
            except Exception as e:
                logger.error(f"TTS chunk {i+1} failed: {e}")
                yield None

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
