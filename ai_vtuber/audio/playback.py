"""AI VTuber - Audio Playback Module

Cross-platform audio playback supporting:
- Windows 10/11 (DirectSound via pygame)
- Linux native (ALSA/PulseAudio via pygame)
- WSL (PulseAudio via pygame)
"""

import logging
import numpy as np
import threading
import os
import tempfile
import wave
from typing import Optional, Callable

logger = logging.getLogger(__name__)


def _setup_cuda_library_path():
    """Setup library path for CUDA libraries if they exist in pip packages.
    
    Cross-platform support for Windows, Linux, and WSL.
    """
    import sys
    
    # Detect Python version dynamically
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    
    # Platform-specific library names and paths
    if sys.platform == 'win32':
        # Windows: Add to PATH environment variable
        env_var_name = 'PATH'
        path_sep = ';'
        
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
        logger.debug(f"Updated {env_var_name} for CUDA libraries")


# Setup CUDA library paths at module load
_setup_cuda_library_path()


class AudioPlayer:
    """Audio playback with interruption support using pygame.mixer (better WSL support)."""

    def __init__(self, config: dict) -> None:
        self.sample_rate: int = config.get("sample_rate", 24000)
        self._is_playing: bool = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._current_sound = None
        
        # Initialize pygame mixer
        try:
            import pygame
            if not pygame.get_init():
                pygame.mixer.init(frequency=self.sample_rate, size=-16, channels=1, buffer=512)
            logger.debug(f"Pygame mixer initialized at {self.sample_rate}Hz")
        except Exception as e:
            logger.warning(f"Failed to initialize pygame mixer: {e}")

    def play(self, audio_data: np.ndarray,
             interrupt_check: Optional[Callable[[], bool]] = None,
             check_interval: float = 0.1,
             on_start: Optional[Callable[[], None]] = None,
             on_end: Optional[Callable[[], None]] = None) -> None:
        """Play audio data with optional interruption support and callbacks using pygame.mixer.
        
        Args:
            audio_data: numpy array of audio samples (float32 at sample_rate)
            interrupt_check: Optional callback that returns True to stop playback
            check_interval: How often to check for interruption (seconds)
            on_start: Optional callback called when playback starts
            on_end: Optional callback called when playback ends (normal or interrupted)
        """
        self._stop_event.clear()

        with self._lock:
            self._is_playing = True

        try:
            import pygame
            
            # Convert to appropriate format
            if audio_data.dtype != np.float32:
                audio_data = audio_data.astype(np.float32)

            # Normalize if needed
            max_val = np.max(np.abs(audio_data))
            if max_val > 1.0:
                audio_data = audio_data / max_val
            
            # Convert to int16 for pygame
            audio_int16 = (audio_data * 32767).astype(np.int16)
            
            # Save to temporary WAV file
            temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            temp_path = temp_file.name
            temp_file.close()
            
            try:
                with wave.open(temp_path, 'wb') as wav_file:
                    wav_file.setnchannels(1)  # Mono
                    wav_file.setsampwidth(2)  # 16-bit
                    wav_file.setframerate(self.sample_rate)
                    wav_file.writeframes(audio_int16.tobytes())
                
                # Load and play
                self._current_sound = pygame.mixer.Sound(temp_path)
                self._current_sound.play()
                
                # Call on_start callback after playback begins
                if on_start:
                    on_start()
                
                # Wait for completion or interruption
                total_duration = len(audio_data) / self.sample_rate
                elapsed = 0
                
                while elapsed < total_duration:
                    if self._stop_event.is_set():
                        logger.debug("Playback stopped by stop event")
                        self._current_sound.stop()
                        break
                    
                    if interrupt_check and interrupt_check():
                        logger.info("Playback interrupted by user")
                        self._stop_event.set()
                        self._current_sound.stop()
                        break
                    
                    pygame.time.wait(int(check_interval * 1000))
                    elapsed += check_interval
                    
            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Audio playback failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            with self._lock:
                self._is_playing = False
            self._current_sound = None
            # Call on_end callback when playback finishes
            if on_end:
                on_end()

    def stop(self) -> None:
        """Stop current playback immediately."""
        self._stop_event.set()
        try:
            import pygame
            if self._current_sound:
                self._current_sound.stop()
        except Exception:
            pass
        with self._lock:
            self._is_playing = False
        logger.debug("Audio playback stopped")

    @property
    def is_playing(self) -> bool:
        """Check if audio is currently playing."""
        with self._lock:
            return self._is_playing
