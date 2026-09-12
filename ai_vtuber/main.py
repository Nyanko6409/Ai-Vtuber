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
import pygame

# Setup CUDA library paths before importing any CUDA-dependent modules
def _setup_cuda_library_path():
    """Setup library path for CUDA libraries if they exist in pip packages."""
    # Detect Python version dynamically
    import sys
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    
    cuda_lib_paths = [
        f"/usr/local/lib/python{python_version}/site-packages/nvidia/cublas/lib",
        f"/usr/local/lib/python{python_version}/site-packages/nvidia/cudnn/lib",
        f"/usr/local/lib/python{python_version}/site-packages/nvidia/nvjitlink/lib",
        f"/usr/local/lib/python{python_version}/site-packages/nvidia/cuda_cupti/lib",
        f"/usr/local/lib/python{python_version}/site-packages/nvidia/cufft/lib",
        f"/usr/local/lib/python{python_version}/site-packages/nvidia/cuda_nvrtc/lib",
        f"/usr/local/lib/python{python_version}/site-packages/nvidia/cuda_runtime/lib",
        f"/usr/local/lib/python{python_version}/site-packages/nvidia/curand/lib",
        f"/usr/local/lib/python{python_version}/site-packages/nvidia/cusparse/lib",
        f"/usr/local/lib/python{python_version}/site-packages/nvidia/cusolver/lib",
        f"/usr/local/lib/python{python_version}/site-packages/nvidia/nccl/lib",
        f"/usr/local/lib/python{python_version}/site-packages/nvidia/nvtx/lib",
        f"/usr/local/lib/python{python_version}/site-packages/nvidia/cufile/lib",
    ]
    
    ld_path = os.environ.get('LD_LIBRARY_PATH', '')
    for path in cuda_lib_paths:
        if os.path.isdir(path) and path not in ld_path:
            ld_path = path + ':' + ld_path if ld_path else path
    
    if ld_path:
        os.environ['LD_LIBRARY_PATH'] = ld_path

# Setup CUDA paths early
_setup_cuda_library_path()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.app import App
from core.state import State
from ui.pygame_ui import PygameUI
from ui.chat_ui import ChatUI

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
    chat_ui = ChatUI(config["avatar"]["window_width"], config["avatar"]["window_height"], config["ui"]["font_size"])

    try:
        # Initialize UI (creates window + OpenGL context)
        ui.init()
        chat_ui.init_fonts()
        
        # Set up chat callback
        def on_chat_message(text: str):
            """Handle chat message from text input."""
            logger.info(f"Chat message: {text}")
            app.process_chat_message(text)
        
        chat_ui.on_send_message = on_chat_message

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
            # Get all events once
            events = pygame.event.get()
            
            # Handle UI events (window close, resize, etc.)
            for event in events:
                if event.type == pygame.QUIT:
                    running = False
                    break
                elif event.type == pygame.VIDEORESIZE:
                    ui.width = event.w
                    ui.height = event.h
                    ui._screen = pygame.display.set_mode(
                        (ui.width, ui.height),
                        pygame.DOUBLEBUF | pygame.OPENGL | pygame.RESIZABLE
                    )
                elif event.type == pygame.KEYDOWN:
                    # Handle special keys first (always work, even when chat is active)
                    if event.key == pygame.K_ESCAPE:
                        running = False
                        break
                    elif event.key == pygame.K_TAB:
                        # Toggle chat visibility with Tab
                        chat_ui.toggle_chat()
                        continue  # Don't pass Tab to chat input
                    elif event.key == pygame.K_f:
                        ui.show_fps = not ui.show_fps
                        continue  # Don't pass F to chat input
                    elif event.key == pygame.K_d:
                        ui.show_debug = not ui.show_debug
                        continue  # Don't pass D to chat input
                    
                    # Let chat UI handle typing keys (if input is active)
                    if chat_ui.input_active:
                        message = chat_ui.handle_event(event)
                        if message:
                            # Message was sent via chat
                            logger.info(f"Chat input: {message}")
                            app.process_chat_message(message)
                
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # Left click
                        mouse_pos = event.pos
                        if chat_ui.chat_visible and chat_ui.input_active:
                            # Click on input box to focus it
                            input_y = chat_ui.height - chat_ui.input_box_height - 10
                            if mouse_pos[1] >= input_y:
                                chat_ui.input_active = True

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
            
            # Update chat UI with current response for typewriter effect
            delta_time = 1.0 / config["avatar"]["fps"]
            status = app.get_status()
            current_response = status.get("response", "")
            chat_ui.update(delta_time, current_response)

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
            
            # Draw chat UI (on top of everything)
            chat_ui.draw(ui._screen)

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
