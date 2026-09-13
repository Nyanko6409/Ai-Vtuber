"""AI VTuber - __init__ for tts module"""

from .normalizer import TextNormalizer, get_normalizer, normalize_text
from .kitten import KittenTTS, split_text_into_chunks

__all__ = ['TextNormalizer', 'get_normalizer', 'normalize_text', 'KittenTTS', 'split_text_into_chunks']
