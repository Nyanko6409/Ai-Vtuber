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
    
Platform Support:
    - Linux (native & WSL)
    - Windows 10/11
    - macOS (experimental)
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
    """Setup library path for CUDA libraries if they exist in pip packages.
    
    Works on:
    - Linux: Uses LD_LIBRARY_PATH
    - Windows: Adds to PATH
    - WSL: Uses LD_LIBRARY_PATH
    """
    import sys
    
    # Detect Python version dynamically
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    
    # Platform-specific library names and paths
    if sys.platform == 'win32':
        # Windows: Add to PATH environment variable
        env_var_name = 'PATH'
        path_sep = ';'
        
        # Windows-specific CUDA paths
        cuda_paths = [
            os.path.join(sys.prefix, f"Lib\\site-packages\\nvidia\\cublas\\bin"),
            os.path.join(sys.prefix, f"Lib\\site-packages\\nvidia\\cudnn\\bin"),
            os.path.join(sys.prefix, f"Lib\\site-packages\\nvidia\\nvjitlink\\bin"),
            os.path.join(sys.prefix, f"Lib\\site-packages\\nvidia\\cuda_cupti\\bin"),
            os.path.join(sys.prefix, f"Lib\\site-packages\\nvidia\\cufft\\bin"),
            os.path.join(sys.prefix, f"Lib\\site-packages\\nvidia\\cuda_nvrtc\\bin"),
            os.path.join(sys.prefix, f"Lib\\site-packages\\nvidia\\cuda_runtime\\bin"),
            os.path.join(sys.prefix, f"Lib\\site-packages\\nvidia\\curand\\bin"),
            os.path.join(sys.prefix, f"Lib\\site-packages\\nvidia\\cusparse\\bin"),
            os.path.join(sys.prefix, f"Lib\\site-packages\\nvidia\\cusolver\\bin"),
            os.path.join(sys.prefix, f"Lib\\site-packages\\nvidia\\nccl\\bin"),
            os.path.join(sys.prefix, f"Lib\\site-packages\\nvidia\\nvtx\\bin"),
            os.path.join(sys.prefix, f"Lib\\site-packages\\nvidia\\cufile\\bin"),
            # Standard CUDA installation paths
            r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6\bin",
            r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.5\bin",
            r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.4\bin",
            r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.3\bin",
            r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.2\bin",
            r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin",
            r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.0\bin",
            r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8\bin",
        ]
    else:
        # Linux/WSL/macOS: Use LD_LIBRARY_PATH
        env_var_name = 'LD_LIBRARY_PATH'
        path_sep = ':'
        
        cuda_paths = [
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
    
    current_path = os.environ.get(env_var_name, '')
    
    for path in cuda_paths:
        if os.path.isdir(path) and path not in current_path:
            current_path = path + path_sep + current_path if current_path else path
    
    if current_path:
        os.environ[env_var_name] = current_path
        logging.getLogger("ai_vtuber").debug(f"Updated {env_var_name} for CUDA libraries")

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
                    # AVATAR CONTROL KEYS HAVE PRIORITY OVER CHAT INPUT
                    # These keys always control the avatar, never go to chat input
                    
                    # Handle special keys first (always work regardless of chat focus)
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
                    # Zoom controls (+/= zoom in, - zoom out, R reset)
                    elif event.key in (pygame.K_PLUS, pygame.K_EQUALS):
                        if app._avatar and app._avatar.is_initialized:
                            app.avatar.zoom_in(0.2)
                        continue  # Don't pass to chat input
                    elif event.key == pygame.K_MINUS:
                        if app._avatar and app._avatar.is_initialized:
                            app.avatar.zoom_out(0.2)
                        continue  # Don't pass to chat input
                    elif event.key == pygame.K_r:
                        if app._avatar and app._avatar.is_initialized:
                            app.avatar.reset_zoom()
                        continue  # Don't pass to chat input
                    # Movement controls (arrow keys or WASD)
                    elif event.key in (pygame.K_UP, pygame.K_w):
                        if app._avatar and app._avatar.is_initialized:
                            app.avatar.move_up(20.0)
                        continue  # Don't pass to chat input
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        if app._avatar and app._avatar.is_initialized:
                            app.avatar.move_down(20.0)
                        continue  # Don't pass to chat input
                    elif event.key in (pygame.K_LEFT, pygame.K_a):
                        if app._avatar and app._avatar.is_initialized:
                            app.avatar.move_left(20.0)
                        continue  # Don't pass to chat input
                    elif event.key in (pygame.K_RIGHT, pygame.K_d):
                        if app._avatar and app._avatar.is_initialized:
                            app.avatar.move_right(20.0)
                        continue  # Don't pass to chat input
                    
                    # Non-control keys: pass to chat input if active
                    if chat_ui.input_active:
                        message = chat_ui.handle_event(event)
                        if message:
                            # Message was sent via chat
                            logger.info(f"Chat input: {message}")
                            app.process_chat_message(message)
                
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    mouse_pos = event.pos
                    input_y = chat_ui.height - chat_ui.input_box_height - 10
                    
                    # Check if clicking inside chat input box using proper rect collision
                    chat_input_rect = pygame.Rect(
                        20, input_y,
                        chat_ui.width - 40, chat_ui.input_box_height
                    )
                    clicked_chat_input = (
                        chat_ui.chat_visible and
                        chat_input_rect.collidepoint(mouse_pos)
                    )
                    
                    if event.button == 1:  # Left click
                        if clicked_chat_input:
                            # Focus chat input, do NOT start dragging
                            chat_ui.input_active = True
                        else:
                            # Start avatar dragging (unless chat is already focused)
                            if not chat_ui.input_active:
                                app._avatar_start_drag = True
                            else:
                                # Chat is focused but clicked outside - unfocus it
                                chat_ui.input_active = False
                    elif event.button == 4:  # Scroll up - zoom in
                        if app._avatar and app._avatar.is_initialized:
                            app.avatar.zoom_in(0.2)
                    elif event.button == 5:  # Scroll down - zoom out
                        if app._avatar and app._avatar.is_initialized:
                            app.avatar.zoom_out(0.2)

                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1:  # Left click released
                        app._avatar_start_drag = False

                elif event.type == pygame.MOUSEMOTION:
                    # Handle avatar dragging with left mouse button
                    # Only drag if not over chat input area
                    if app._avatar_start_drag and app._avatar and app._avatar.is_initialized:
                        dx, dy = event.rel
                        app.avatar.move_by(-dx, -dy)

            if not running:
                break

            # Forward mouse position to avatar for eye tracking
            # Only do eye tracking when NOT dragging the avatar
            if app._avatar and app._avatar.is_initialized and not app._avatar_start_drag:
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
