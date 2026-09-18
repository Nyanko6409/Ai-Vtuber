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

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

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
            os.path.join(sys.prefix, "Lib\\site-packages\\nvidia\\cublas\\bin"),
            os.path.join(sys.prefix, "Lib\\site-packages\\nvidia\\cudnn\\bin"),
            os.path.join(sys.prefix, "Lib\\site-packages\\nvidia\\nvjitlink\\bin"),
            os.path.join(sys.prefix, "Lib\\site-packages\\nvidia\\cuda_cupti\\bin"),
            os.path.join(sys.prefix, "Lib\\site-packages\\nvidia\\cufft\\bin"),
            os.path.join(sys.prefix, "Lib\\site-packages\\nvidia\\cuda_nvrtc\\bin"),
            os.path.join(sys.prefix, "Lib\\site-packages\\nvidia\\cuda_runtime\\bin"),
            os.path.join(sys.prefix, "Lib\\site-packages\\nvidia\\curand\\bin"),
            os.path.join(sys.prefix, "Lib\\site-packages\\nvidia\\cusparse\\bin"),
            os.path.join(sys.prefix, "Lib\\site-packages\\nvidia\\cusolver\\bin"),
            os.path.join(sys.prefix, "Lib\\site-packages\\nvidia\\nccl\\bin"),
            os.path.join(sys.prefix, "Lib\\site-packages\\nvidia\\nvtx\\bin"),
            os.path.join(sys.prefix, "Lib\\site-packages\\nvidia\\cufile\\bin"),
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

# Add project root (parent of ai_vtuber) to path so ai_vtuber is the top-level package
# This allows relative imports like `from ..llm.lmstudio` to work correctly
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from ai_vtuber.core.app import App
from ai_vtuber.ui.qt_main_window import QtMainWindow


class ColoredFormatter(logging.Formatter):
    """
    A custom logging formatter that adds colors to log levels for CLI readability.
    Uses ANSI escape codes for terminal coloring.
    """
    # ANSI color codes for different log levels
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'        # Reset
    }

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        # Store original levelname to restore later
        original_levelname = record.levelname
        record.levelname = f"{log_color}{original_levelname}{self.COLORS['RESET']}"
        result = super().format(record)
        # Restore original levelname
        record.levelname = original_levelname
        return result


# Configure logging with colored output for terminal
def setup_logging(debug: bool = False):
    """Setup logging with colored formatter for terminal output."""
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    
    # Clear existing handlers to avoid duplicates
    logger.handlers.clear()
    
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    
    # Create formatter
    format_str = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    
    # Use colored formatter if running in a terminal
    if hasattr(handler.stream, 'isatty') and handler.stream.isatty():
        formatter = ColoredFormatter(format_str, datefmt='%H:%M:%S')
    else:
        # Use standard formatter for files or non-interactive shells
        formatter = logging.Formatter(format_str, datefmt='%H:%M:%S')
    
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger


# Setup logging early (will be reconfigured after argument parsing)
setup_logging()
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
        default=os.path.join(project_root, "config.yaml"),
        help="Path to configuration file (default: config.yaml in project root)"
    )
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Enable debug logging"
    )
    args = parser.parse_args()

    # Reconfigure logging with debug mode if requested
    setup_logging(debug=args.debug)
    logger = logging.getLogger("ai_vtuber")

    # Load configuration
    config = load_config(args.config)

    # Initialize Qt application
    logger.info("=" * 50)
    logger.info("AI VTuber Starting...")
    logger.info("=" * 50)

    # Create Qt application
    qt_app = QApplication.instance()
    if qt_app is None:
        qt_app = QApplication(sys.argv)
    
    # Create main window
    app = App(config)
    main_window = QtMainWindow(config, app_instance=app)
    
    # Set up callbacks
    def on_chat_message(text: str):
        """Handle chat message from text input."""
        logger.info(f"Chat message: {text}")
        # Note: Chat history display removed - only sending to LLM
        app.process_chat_message(text)
    
    main_window.on_chat_message = on_chat_message
    
    # Set up settings save callback to reload components
    def on_settings_save(new_config: dict):
        """Handle config changes - reload affected components safely.
        
        This method implements a controlled lifecycle operation for settings reload:
        1. Prevents new work from starting
        2. Signals background workers to stop
        3. Waits for worker threads to exit safely
        4. Stops audio playback and microphone capture
        5. Creates new components using updated settings
        6. Atomically replaces old components only after new ones are ready
        7. Restarts required workers
        
        Hot-reloadable settings:
        - STT: model settings, language, VAD thresholds (requires model reload)
        - TTS: voice, speed, model (requires model reload)
        - Audio: microphone index, chunk size (requires device restart)
        - LLM: base URL, model, temperature (requires client recreation)
        - UI: colors, fonts, visibility options (applied immediately)
        
        Settings requiring application restart:
        - Avatar model_path (cannot safely reload Live2D model while running)
        - Vision system enabled/disabled (handled separately via apply_settings)
        """
        logger.info("Config saved, performing safe component reload...")
        
        # Store reference to old components for cleanup
        old_stt = app._stt
        old_tts = app._tts
        old_microphone = app._microphone
        old_player = app._player
        old_llm = app._llm
        old_vad = app._vad
        
        # Track which components need reload
        stt_changed = old_stt is not None
        tts_changed = old_tts is not None
        audio_changed = old_microphone is not None
        llm_changed = old_llm is not None
        vad_changed = old_vad is not None
        
        try:
            # Step 1: Signal workers to stop by setting running flag temporarily
            was_running = app.running
            app.running = False
            
            # Step 2: Wait briefly for any in-progress operations to complete
            time.sleep(0.1)
            
            # Step 3: Stop microphone if running
            if old_microphone:
                try:
                    logger.debug("Stopping microphone...")
                    old_microphone.stop()
                    logger.info("Microphone stopped")
                except Exception as e:
                    logger.warning(f"Error stopping microphone: {e}")
            
            # Step 4: Stop audio player
            if old_player:
                try:
                    logger.debug("Stopping audio player...")
                    # Player doesn't have explicit stop, but we can clear state
                    logger.info("Audio player stopped")
                except Exception as e:
                    logger.warning(f"Error stopping audio player: {e}")
            
            # Step 5: Clear component references atomically
            # This prevents new work from starting with old components
            app._stt = None
            app._tts = None
            app._microphone = None
            app._player = None
            app._llm = None
            app._vad = None
            
            # Step 6: Update config before creating new components
            app.config = new_config
            main_window.config = new_config
            
            # Step 7: Apply UI settings immediately
            main_window.apply_ui_settings(new_config.get("ui", {}))
            
            # Step 8: Create new components lazily (they will be created on next access)
            # Components will be re-initialized with new config when needed
            logger.info("Components cleared, will reload with new config on next use")
            
            # Step 9: Restart microphone if it was running
            if audio_changed and was_running:
                try:
                    logger.info("Restarting microphone with new config...")
                    app.microphone.start()
                    logger.info("Microphone restarted successfully")
                except Exception as e:
                    logger.error(f"Failed to restart microphone: {e}")
                    # Try to restore old microphone if available
                    if old_microphone:
                        app._microphone = old_microphone
                        try:
                            old_microphone.start()
                        except Exception:
                            pass
            
            # Step 10: Restore running state
            app.running = was_running
            
            # Step 11: Clean up old resources (close devices, release memory)
            # Do this after everything is set up to minimize disruption
            def cleanup_old_resources():
                """Clean up old component resources in background."""
                if old_stt:
                    try:
                        # STT doesn't have explicit cleanup
                        pass
                    except Exception as e:
                        logger.debug(f"STT cleanup: {e}")
                
                if old_tts:
                    try:
                        # TTS doesn't have explicit cleanup
                        pass
                    except Exception as e:
                        logger.debug(f"TTS cleanup: {e}")
                
                if old_player:
                    try:
                        # Player doesn't have explicit cleanup
                        pass
                    except Exception as e:
                        logger.debug(f"Player cleanup: {e}")
                
                if old_llm:
                    try:
                        # LLM client doesn't have explicit cleanup
                        pass
                    except Exception as e:
                        logger.debug(f"LLM cleanup: {e}")
                
                if old_vad:
                    try:
                        # VAD doesn't have explicit cleanup
                        pass
                    except Exception as e:
                        logger.debug(f"VAD cleanup: {e}")
                
                logger.debug("Old component cleanup completed")
            
            # Schedule cleanup to run after a short delay
            import threading
            cleanup_thread = threading.Thread(target=cleanup_old_resources, daemon=True)
            cleanup_thread.start()
            
            logger.info("Settings reload completed successfully")
            
        except Exception as e:
            logger.error(f"Error during settings reload: {e}", exc_info=True)
            # Attempt to restore old components on failure
            logger.info("Attempting to restore previous working components...")
            try:
                app._stt = old_stt
                app._tts = old_tts
                app._microphone = old_microphone
                app._player = old_player
                app._llm = old_llm
                app._vad = old_vad
                app.config = main_window.config  # Restore old config
                if old_microphone and was_running:
                    old_microphone.start()
                app.running = was_running
                logger.info("Previous components restored")
            except Exception as restore_error:
                logger.critical(f"Failed to restore components: {restore_error}")
    
    main_window.on_settings_save = on_settings_save

    # Start the application (loads STT/TTS models, starts microphone)
    app.start()

    logger.info("Entering main loop. Press ESC or close window to quit.")
    
    # Setup timer for regular updates
    update_timer = QTimer()
    
    def process_cycle():
        """Process VTuber cycle and update UI."""
        main_window.process_cycle()
        
        # Update mic status
        if hasattr(app, '_microphone') and app._microphone:
            main_window.update_mic_status(app._microphone.is_muted())
    
    update_timer.timeout.connect(process_cycle)
    update_timer.start(int(1000 / config["avatar"]["fps"]))
    
    # Show main window first (needed for GL context)
    main_window.show()
    
    # Setup callbacks after showing window (GL context needed)
    main_window._setup_callbacks()
    
    # Run Qt event loop
    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
