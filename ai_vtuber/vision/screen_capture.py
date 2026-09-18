"""AI VTuber - Screen Capture Service using MSS"""

import io
import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional, Callable, List

from PIL import Image

import mss
import mss.tools

logger = logging.getLogger(__name__)


@dataclass
class ScreenCaptureConfig:
    """Configuration for screen capture."""
    monitor_index: int = 0  # -1 for all monitors (merged), 0+ for specific monitor
    capture_interval: float = 0.5  # Seconds between captures
    enabled: bool = False
    max_width: int = 1920  # Full HD resolution for better analysis
    max_height: int = 1080
    jpeg_quality: int = 85  # JPEG compression quality (1-100)
    region: Optional[tuple] = None  # (left, top, right, bottom) ROI if set
    debug_save_captures: bool = False  # TEMPORARY: Save captured images to debug folder
    debug_folder: str = "debug_captures"  # Folder for debug captures
    
    def validate(self) -> tuple[bool, str]:
        """Validate configuration values.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if self.capture_interval <= 0:
            return False, f"capture_interval must be positive, got {self.capture_interval}"
        if self.capture_interval > 60:
            return False, f"capture_interval too large ({self.capture_interval}s), max 60s"
        if self.max_width <= 0 or self.max_height <= 0:
            return False, "max_width and max_height must be positive"
        if self.jpeg_quality < 1 or self.jpeg_quality > 100:
            return False, f"jpeg_quality must be 1-100, got {self.jpeg_quality}"
        if self.monitor_index < -1:
            return False, f"monitor_index must be >= -1, got {self.monitor_index}"
        if self.region is not None:
            if len(self.region) != 4:
                return False, "region must be a 4-tuple (left, top, right, bottom)"
            left, top, right, bottom = self.region
            if left >= right or top >= bottom:
                return False, "Invalid region: left must be < right, top must be < bottom"
        return True, ""


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
    - Support for monitor_index=-1 (all monitors merged)
    - Configurable capture intervals
    - Enable/disable control
    - No permanent screenshot storage
    - Proper resource cleanup
    - Thread-safe lifecycle operations
    - Backpressure handling
    """
    
    def __init__(self, config: ScreenCaptureConfig):
        self.config = config
        
        # Validate config
        valid, error = config.validate()
        if not valid:
            raise ValueError(f"Invalid ScreenCaptureConfig: {error}")
        
        self._running = False
        self._enabled = config.enabled
        self._sct: Optional[mss.mss] = None
        self._capture_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._shutdown_event = threading.Event()
        self._frame_callback: Optional[Callable[[CapturedFrame], None]] = None
        self._last_capture_time: float = 0.0
        self._capture_count: int = 0
        self._error_count: int = 0
        
        # Latest frame buffer for backpressure (always keep newest)
        self._latest_frame: Optional[CapturedFrame] = None
        self._latest_frame_lock = threading.Lock()
        
    def set_frame_callback(self, callback: Callable[[CapturedFrame], None]) -> None:
        """Set callback to receive captured frames."""
        self._frame_callback = callback
        
    def start(self) -> bool:
        """Start the screen capture service."""
        if not self._enabled:
            logger.info("Screen capture service disabled in config")
            return False
            
        with self._lock:
            if self._running:
                logger.warning("Screen capture service already running")
                return True
            
            try:
                self._sct = mss.mss()
                
                # Validate monitor index
                monitors = self._sct.monitors
                if self.config.monitor_index == -1:
                    logger.info(f"Capturing all monitors (merged), total monitors: {len(monitors)-1}")
                elif self.config.monitor_index >= len(monitors):
                    logger.warning(
                        f"Monitor index {self.config.monitor_index} out of range, "
                        f"using monitor 0. Available: {len(monitors)}"
                    )
                    self.config.monitor_index = 0
                
                self._running = True
                self._shutdown_event.clear()
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
        
        with self._lock:
            if not self._running:
                return  # Already stopped (idempotent)
            
            self._running = False
            self._enabled = False
        
        # Signal shutdown and wait for thread
        self._shutdown_event.set()
        
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
        with self._latest_frame_lock:
            last_frame_time = (
                self._latest_frame.timestamp if self._latest_frame else 0.0
            )
        
        return {
            "running": self._running,
            "enabled": self._enabled,
            "capture_count": self._capture_count,
            "error_count": self._error_count,
            "last_capture": self._last_capture_time,
            "last_frame_time": last_frame_time
        }
    
    def capture_once(self) -> Optional[bytes]:
        """
        Capture a single frame synchronously.
        
        This is useful for on-demand capture without starting
        the continuous capture loop.
        
        Returns:
            JPEG-encoded image bytes, or None on failure
        """
        sct = None
        try:
            sct = mss.mss()
            monitors = sct.monitors
            
            # Handle monitor_index = -1 (all monitors)
            if self.config.monitor_index == -1:
                # Get bounding box of all monitors
                if len(monitors) < 2:
                    logger.warning("No monitors available for capture")
                    return None
                
                # Monitor 0 in MSS is the virtual "all monitors" screen
                monitor = monitors[0]
                logger.debug(f"Capturing all monitors: {monitor}")
            else:
                if self.config.monitor_index >= len(monitors):
                    logger.warning(f"Monitor {self.config.monitor_index} unavailable")
                    return None
                monitor = monitors[self.config.monitor_index]
            
            # Apply region if specified
            if self.config.region:
                left, top, right, bottom = self.config.region
                monitor = {
                    'left': left,
                    'top': top,
                    'width': right - left,
                    'height': bottom - top
                }
            
            # Capture screen
            screenshot = sct.grab(monitor)
            
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
            
            # TEMPORARY DEBUG: Save captured image to file
            if self.config.debug_save_captures:
                import os
                from datetime import datetime
                os.makedirs(self.config.debug_folder, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"capture_{timestamp}_mon{self.config.monitor_index}_{img.width}x{img.height}.jpg"
                filepath = os.path.join(self.config.debug_folder, filename)
                img.save(filepath, format="JPEG", quality=self.config.jpeg_quality)
                logger.info(f"[DEBUG CAPTURE] Saved screenshot to: {filepath}")
                logger.info(f"[DEBUG CAPTURE] Monitor index: {self.config.monitor_index}, Dimensions: {img.width}x{img.height}, Size: {len(image_bytes)} bytes")
                if self.config.region:
                    logger.info(f"[DEBUG CAPTURE] Region: {self.config.region}")
                else:
                    logger.info(f"[DEBUG CAPTURE] Full monitor capture")
            
            logger.debug(f"capture_once: captured {img.width}x{img.height}, {len(image_bytes)} bytes")
            return image_bytes
            
        except Exception as e:
            logger.error(f"capture_once failed: {e}")
            return None
        finally:
            if sct:
                try:
                    sct.close()
                except Exception:
                    pass
    
    def get_latest_frame(self) -> Optional[CapturedFrame]:
        """
        Get the most recently captured frame.
        
        Returns:
            Latest CapturedFrame or None if no frames captured yet
        """
        with self._latest_frame_lock:
            return self._latest_frame
    
    def _capture_loop(self) -> None:
        """Main capture loop running in background thread."""
        while self._running and not self._shutdown_event.is_set():
            try:
                if not self._enabled:
                    # Sleep in small increments to allow quick shutdown
                    self._shutdown_event.wait(timeout=0.5)
                    continue
                
                self._capture_frame()
                
                # Sleep until next capture interval
                elapsed = time.time() - self._last_capture_time
                sleep_time = max(0.01, self.config.capture_interval - elapsed)
                self._shutdown_event.wait(timeout=sleep_time)
                
            except Exception as e:
                self._error_count += 1
                logger.error(f"Screen capture error: {e}")
                # Back off on errors
                self._shutdown_event.wait(timeout=1.0)
    
    def _capture_frame(self) -> None:
        """Capture a single frame and notify callback."""
        if not self._sct:
            return
            
        with self._lock:
            # Get monitor bounds
            monitors = self._sct.monitors
            
            # Handle monitor_index = -1 (all monitors merged)
            if self.config.monitor_index == -1:
                # Monitor 0 in MSS is the virtual "all monitors" screen
                if len(monitors) < 1:
                    logger.warning("No monitors available")
                    return
                monitor = monitors[0]  # Virtual screen covering all monitors
            else:
                if self.config.monitor_index >= len(monitors):
                    logger.warning(f"Monitor {self.config.monitor_index} unavailable")
                    return
                monitor = monitors[self.config.monitor_index]
            
            # Apply region if specified
            if self.config.region:
                left, top, right, bottom = self.config.region
                monitor = {
                    'left': left,
                    'top': top,
                    'width': right - left,
                    'height': bottom - top
                }
            
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
            
            # Update latest frame buffer (for backpressure)
            with self._latest_frame_lock:
                self._latest_frame = frame
            
            # Notify callback
            if self._frame_callback:
                try:
                    self._frame_callback(frame)
                except Exception as e:
                    logger.error(f"Frame callback error: {e}")
