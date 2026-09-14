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

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction

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

# Add project root (parent of ai_vtuber) to path so ai_vtuber is the top-level package
# This allows relative imports like `from ..llm.lmstudio` to work correctly
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from ai_vtuber.core.app import App
from ai_vtuber.core.state import State
from ai_vtuber.ui.qt_main_window import QtMainWindow
from ai_vtuber.ui.pyside_settings import show_settings_dialog

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
        """Handle config changes - reload affected components."""
        logger.info("Config saved, reloading components...")
        # Update config reference in main window
        main_window.config = new_config
        # Apply UI settings (background color, text color, font)
        main_window.apply_ui_settings(new_config.get("ui", {}))
        # Force reload of components by setting them to None
        # They will be re-initialized lazily with new config
        app._stt = None
        app._tts = None
        app._microphone = None
        app._player = None
        logger.info("Components will reload with new config on next use")
    
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
