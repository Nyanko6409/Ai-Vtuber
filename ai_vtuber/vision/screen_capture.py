"""AI VTuber - Screen Capture Service using MSS"""

import io
import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional, Callable
from PIL import Image

import mss
import mss.tools

logger = logging.getLogger(__name__)


@dataclass
class ScreenCaptureConfig:
    """Configuration for screen capture."""
    monitor_index: int = 0  # -1 for all monitors, 0+ for specific monitor
    capture_interval: float = 0.5  # Seconds between captures
    enabled: bool = False
    max_width: int = 1920  # Full HD resolution for better analysis
    max_height: int = 1080
    jpeg_quality: int = 85  # JPEG compression quality (1-100)


@dataclass
class CapturedFrame:
    """A captured screen frame."""
    image_bytes: bytes  # JPEG-encoded image
    timestamp: float  # Unix timestamp
    monitor_index: int
    width: int
    height: int


class ScreenCaptureService:
    """
    Modular screen capture service using MSS.
    
    Features:
    - Capture desktop or configurable monitor
    - Configurable capture intervals
    - Enable/disable control
    - No permanent screenshot storage
    - Proper resource cleanup
    """
    
    def __init__(self, config: ScreenCaptureConfig):
        self.config = config
        self._running = False
        self._enabled = config.enabled
        self._sct: Optional[mss.mss] = None
        self._capture_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._frame_callback: Optional[Callable[[CapturedFrame], None]] = None
        self._last_capture_time: float = 0.0
        self._capture_count: int = 0
        self._error_count: int = 0
        
    def set_frame_callback(self, callback: Callable[[CapturedFrame], None]) -> None:
        """Set callback to receive captured frames."""
        self._frame_callback = callback
        
    def start(self) -> bool:
        """Start the screen capture service."""
        if not self._enabled:
            logger.info("Screen capture service disabled in config")
            return False
            
        if self._running:
            logger.warning("Screen capture service already running")
            return True
            
        try:
            self._sct = mss.mss()
            
            # Validate monitor index
            monitors = self._sct.monitors
            if self.config.monitor_index >= len(monitors):
                logger.warning(
                    f"Monitor index {self.config.monitor_index} out of range, "
                    f"using monitor 0. Available: {len(monitors)}"
                )
                self.config.monitor_index = 0
                
            self._running = True
            self._capture_thread = threading.Thread(
                target=self._capture_loop,
                daemon=True,
                name="ScreenCapture"
            )
            self._capture_thread.start()
            
            logger.info(
                f"Screen capture started on monitor {self.config.monitor_index}, "
                f"interval {self.config.capture_interval}s"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to start screen capture: {e}")
            self._cleanup()
            return False
    
    def stop(self) -> None:
        """Stop the screen capture service and release resources."""
        logger.info("Stopping screen capture service...")
        self._running = False
        self._enabled = False
        
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=2.0)
            
        self._cleanup()
        logger.info("Screen capture service stopped")
    
    def _cleanup(self) -> None:
        """Release MSS resources."""
        if self._sct:
            try:
                self._sct.close()
            except Exception:
                pass
            self._sct = None
    
    def enable(self) -> None:
        """Enable screen capture (will start capturing if already running)."""
        with self._lock:
            self._enabled = True
        logger.info("Screen capture enabled")
    
    def disable(self) -> None:
        """Disable screen capture (stops capturing but keeps service ready)."""
        with self._lock:
            self._enabled = False
        logger.info("Screen capture disabled")
    
    @property
    def is_running(self) -> bool:
        """Check if capture service is running."""
        return self._running
    
    @property
    def is_enabled(self) -> bool:
        """Check if capture is enabled."""
        return self._enabled
    
    @property
    def stats(self) -> dict:
        """Get capture statistics."""
        return {
            "running": self._running,
            "enabled": self._enabled,
            "capture_count": self._capture_count,
            "error_count": self._error_count,
            "last_capture": self._last_capture_time
        }
    
    def _capture_loop(self) -> None:
        """Main capture loop running in background thread."""
        while self._running:
            try:
                if not self._enabled:
                    time.sleep(0.5)
                    continue
                
                self._capture_frame()
                
                # Sleep until next capture interval
                elapsed = time.time() - self._last_capture_time
                sleep_time = max(0.01, self.config.capture_interval - elapsed)
                time.sleep(sleep_time)
                
            except Exception as e:
                self._error_count += 1
                logger.error(f"Screen capture error: {e}")
                time.sleep(1.0)  # Back off on errors
    
    def _capture_frame(self) -> None:
        """Capture a single frame and notify callback."""
        if not self._sct:
            return
            
        with self._lock:
            # Get monitor bounds
            monitors = self._sct.monitors
            if self.config.monitor_index >= len(monitors):
                logger.warning(f"Monitor {self.config.monitor_index} unavailable")
                return
                
            monitor = monitors[self.config.monitor_index]
            
            # Capture screen
            screenshot = self._sct.grab(monitor)
            
            # Convert to RGB
            img = Image.frombytes(
                "RGB",
                (screenshot.width, screenshot.height),
                screenshot.bgra,
                "raw",
                "BGRX"
            )
            
            # Resize if needed
            if (img.width > self.config.max_width or 
                img.height > self.config.max_height):
                img.thumbnail(
                    (self.config.max_width, self.config.max_height),
                    Image.Resampling.LANCZOS
                )
            
            # Encode as JPEG
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=self.config.jpeg_quality)
            image_bytes = buffer.getvalue()
            
            # Create frame
            frame = CapturedFrame(
                image_bytes=image_bytes,
                timestamp=time.time(),
                monitor_index=self.config.monitor_index,
                width=img.width,
                height=img.height
            )
            
            self._last_capture_time = frame.timestamp
            self._capture_count += 1
            
            # Notify callback
            if self._frame_callback:
                try:
                    self._frame_callback(frame)
                except Exception as e:
                    logger.error(f"Frame callback error: {e}")
