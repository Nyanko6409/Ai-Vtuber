#!/usr/bin/env python3
"""AI VTuber - Main Entry Point

A local AI VTuber application that runs entirely on your machine.

Pipeline:
    Microphone → VAD → faster-whisper → Gemma 4 via LM Studio → 
    emotion parser → Live2D expression → KittenTTS → audio playback

Requirements:
    - LM Studio running with a model loaded (OpenAI-compatible API)
    - A Live2D model file (.model3.json)
    - Python 3.11+ with dependencies from requirements.txt

Usage:
    python main.py [--config config.yaml]
"""

import sys
import os
import logging
import argparse
import time
import yaml

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.app import App
from core.state import State
from ui.pygame_ui import PygameUI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("ai_vtuber")


def load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    if not os.path.exists(config_path):
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    logger.info(f"Configuration loaded from: {config_path}")
    return config


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="AI VTuber - Local AI Virtual YouTuber")
    parser.add_argument(
        "--config", "-c",
        default=os.path.join(os.path.dirname(__file__), "config.yaml"),
        help="Path to configuration file (default: config.yaml)"
    )
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Enable debug logging"
    )
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load configuration
    config = load_config(args.config)

    # Initialize application
    logger.info("=" * 50)
    logger.info("AI VTuber Starting...")
    logger.info("=" * 50)

    app = App(config)
    ui = PygameUI(config)

    try:
        # Initialize UI (creates window + OpenGL context)
        ui.init()

        # Start the application (loads STT/TTS models, starts microphone)
        # NOTE: Live2D model is NOT loaded yet - it needs the OpenGL context
        app.start()

        # NOW initialize Live2D (OpenGL context exists)
        live2d_error = None
        if app._avatar:
            success = app.avatar.init_gl()
            if success:
                app.avatar.resize(ui.width, ui.height)
                logger.info("Live2D avatar initialized with OpenGL context")
            else:
                live2d_error = app.avatar.error_message or "Live2D initialization failed"
                logger.warning(f"Live2D avatar failed to initialize: {live2d_error}")
                logger.warning("UI will work without avatar")

        # Main loop
        logger.info("Entering main loop. Press ESC or close window to quit.")
        running = True

        while running:
            # Handle events
            running = ui.handle_events()

            if not running:
                break

            # Forward mouse position to avatar for eye tracking
            if app._avatar and app._avatar.is_initialized:
                try:
                    mx, my = ui.get_mouse_pos()
                    app.avatar.drag(mx, my)
                except Exception:
                    pass

            # Process VTuber pipeline
            app.process_cycle()

            # Begin rendering frame
            ui.begin_frame()

            # Draw Live2D avatar (if initialized)
            if app._avatar and app._avatar.is_initialized:
                try:
                    delta_time = 1.0 / config["avatar"]["fps"]
                    app.avatar.update(delta_time)
                    app.avatar.draw()
                except Exception as e:
                    if config.get("ui", {}).get("show_debug", False):
                        logger.debug(f"Avatar render error: {e}")

            # Draw UI overlay
            status = app.get_status()
            # Show Live2D error if avatar failed to initialize
            error_msg = status.get("error") or live2d_error
            ui.draw_overlay(status, error_msg)

            # End frame
            ui.end_frame()

            # Small sleep to prevent CPU spinning
            time.sleep(0.001)

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        # Cleanup
        logger.info("Shutting down...")
        app.stop()
        ui.cleanup()
        logger.info("Goodbye!")


if __name__ == "__main__":
    main()
