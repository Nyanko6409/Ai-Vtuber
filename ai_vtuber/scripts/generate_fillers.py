"""Generate filler audio phrases for latency masking.

This script pre-renders filler phrases using KittenTTS and saves them
as .npy files for quick loading at runtime.

Usage:
    python scripts/generate_fillers.py

Filler phrases are loaded from ai_vtuber/personality/fillers.md
Output: ai_vtuber/data/fillers/filler_XX_NNNms.npy
"""

import logging
import sys
from pathlib import Path

import numpy as np

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_vtuber.tts.kitten import KittenTTS


def _load_yaml_config(config_path: Path) -> dict:
    """Load configuration from YAML file."""
    import yaml
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def load_filler_phrases(config: dict) -> list[str]:
    """Load filler phrases from configured path.
    
    Args:
        config: Full configuration dictionary containing fillers.phrases_file
        
    Returns:
        List of filler phrase strings.
    """
    # Use config value with fallback to default
    phrases_file = config.get("fillers", {}).get("phrases_file", "personality/fillers.md")
    fillers_path = Path(__file__).parent.parent / phrases_file
    
    if not fillers_path.exists():
        logger.warning(f"Fillers file not found at {fillers_path}, using defaults")
        return [
            "Hmm, let me think...",
            "That's a good point!",
            "You know,",
            "Well,",
            "I see.",
        ]
    
    phrases = []
    with open(fillers_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if line and not line.startswith("#"):
                phrases.append(line)
    
    if not phrases:
        logger.warning("Fillers file is empty, using defaults")
        return [
            "Hmm, let me think...",
            "That's a good point!",
            "You know,",
            "Well,",
            "I see.",
        ]
    
    return phrases


def main():
    """Generate and save filler audio files."""
    logger.info("Starting filler generation...")
    
    # Load config for TTS settings - config.yaml is in project root (parent of ai_vtuber)
    config_path = Path(__file__).parent.parent.parent / "config.yaml"
    config = _load_yaml_config(config_path)
    tts_config = config["tts"]
    
    # Initialize TTS
    logger.info(f"Initializing KittenTTS with model: {tts_config['model']}")
    tts = KittenTTS(tts_config)
    
    # Load filler phrases using config
    phrases = load_filler_phrases(config)
    logger.info(f"Loaded {len(phrases)} filler phrases from: {config.get('fillers', {}).get('phrases_file', 'personality/fillers.md')}")
    
    # Output directory
    output_dir = Path(__file__).parent.parent / "data" / "fillers"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Clear existing filler files
    for old_file in output_dir.glob("filler_*.npy"):
        old_file.unlink()
        logger.debug(f"Removed old filler: {old_file}")
    
    # Generate and save each filler
    generated = 0
    for i, phrase in enumerate(phrases):
        logger.info(f"Generating filler {i+1}/{len(phrases)}: '{phrase}'")
        
        try:
            audio = tts.generate(phrase)
            if audio is None:
                logger.warning(f"TTS returned None for phrase {i+1}, skipping")
                continue
            
            # Calculate duration in milliseconds
            duration_ms = int(len(audio) / tts.sample_rate * 1000)
            
            # Save as .npy file with duration in filename
            filename = f"filler_{i:02d}_{duration_ms}ms.npy"
            output_path = output_dir / filename
            
            np.save(output_path, audio)
            logger.info(f"  Saved: {filename} ({duration_ms}ms, {len(audio)} samples)")
            generated += 1
            
        except Exception as e:
            logger.error(f"Failed to generate filler {i+1}: {e}")
    
    logger.info(f"Generated {generated}/{len(phrases)} filler files to {output_dir}")


if __name__ == "__main__":
    main()
