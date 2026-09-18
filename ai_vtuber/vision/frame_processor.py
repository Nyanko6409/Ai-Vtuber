"""AI VTuber - Frame Processing and Change Detection"""

import hashlib
import io
import logging
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Callable, Deque, List, Tuple

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class FrameProcessingConfig:
    """Configuration for frame processing."""
    analysis_interval: float = 5.0  # Minimum seconds between analyses
    change_threshold: float = 0.15  # Fraction of pixels that must change
    enable_change_detection: bool = True
    max_queue_size: int = 5  # Prevent unbounded growth
    resize_width: int = 320  # Resize for change detection
    resize_height: int = 180
    hash_bins: int = 16  # For perceptual hashing
    max_history_size: int = 5  # Maximum number of frames in history


@dataclass
class ProcessedFrame:
    """A frame ready for analysis."""
    image_bytes: bytes
    timestamp: float
    change_score: float  # 0.0-1.0, how much changed from previous
    is_significant: bool  # Whether to send for analysis
    frame_hash: str
    width: int = 0
    height: int = 0


class FrameProcessor:
    """
    Intelligent frame processing pipeline.
    
    Features:
    - Detects significant screen changes
    - Avoids duplicate frames
    - Configurable analysis interval
    - Prevents concurrent vision requests
    - Queue-based handling
    - Resource-efficient processing
    """
    
    def __init__(self, config: FrameProcessingConfig):
        self.config = config
        self._running = False
        self._lock = threading.Lock()
        self._analysis_lock = threading.Lock()
        self._is_analyzing = False
        
        # Frame history for change detection (bounded)
        # Stores tuples of (numpy_array, timestamp, hash)
        self._frame_history: Deque[Tuple[np.ndarray, float, str]] = deque(
            maxlen=config.max_history_size
        )
        self._last_hash: Optional[str] = None
        self._last_analysis_time: float = 0.0
        self._frames_since_analysis: int = 0
        
        # Bounded queue for pending frames (latest-frame strategy)
        self._frame_queue: queue.Queue[ProcessedFrame] = queue.Queue(
            maxsize=config.max_queue_size
        )
        
        # Statistics
        self._total_frames: int = 0
        self._significant_frames: int = 0
        self._duplicate_frames: int = 0
        self._dropped_frames: int = 0
        self._invalid_frames: int = 0
        
        # Callback for frames ready for analysis
        self._analysis_callback: Optional[Callable[[ProcessedFrame], None]] = None
        
    def set_analysis_callback(
        self, callback: Callable[[ProcessedFrame], None]
    ) -> None:
        """Set callback for frames ready for LLM analysis."""
        self._analysis_callback = callback
        
    def start(self) -> None:
        """Start the frame processor."""
        self._running = True
        logger.info("Frame processor started")
    
    def stop(self) -> None:
        """Stop the frame processor."""
        self._running = False
        # Clear queue on stop
        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                break
        logger.info("Frame processor stopped")
    
    def process_frame(
        self, image_bytes: bytes, timestamp: Optional[float] = None
    ) -> Optional[ProcessedFrame]:
        """
        Process a captured frame and determine if it should be analyzed.
        
        Args:
            image_bytes: JPEG or PNG encoded image data
            timestamp: Frame timestamp (uses current time if None)
            
        Returns:
            ProcessedFrame if significant, None if skipped or invalid
        """
        if not self._running:
            return None
            
        self._total_frames += 1
        
        if timestamp is None:
            timestamp = time.time()
        
        # Decode image safely
        img = self._decode_image(image_bytes)
        if img is None:
            self._invalid_frames += 1
            logger.warning(f"Invalid/empty image data received (frame #{self._total_frames})")
            return None
        
        # Compute perceptual hash
        frame_hash = self._compute_hash(img)
        
        # Check for duplicate (cheap comparison first)
        if self._last_hash == frame_hash:
            self._duplicate_frames += 1
            logger.debug("Duplicate frame detected (hash match), skipping")
            return None
        
        # Compute change score (more expensive comparison)
        change_score = self._compute_change(img)
        
        # Determine if significant
        is_significant = self._should_analyze(change_score, timestamp)
        
        processed = ProcessedFrame(
            image_bytes=image_bytes,
            timestamp=timestamp,
            change_score=change_score,
            is_significant=is_significant,
            frame_hash=frame_hash,
            width=img.width,
            height=img.height
        )
        
        if is_significant:
            self._significant_frames += 1
            self._last_hash = frame_hash
            
            # Update frame history when submitting for analysis
            self._update_frame_history(img, timestamp, frame_hash)
            self._frames_since_analysis += 1
            
            # Add to queue (non-blocking, drops oldest if full via replacement strategy)
            try:
                self._frame_queue.put_nowait(processed)
                
                # Notify callback
                if self._analysis_callback:
                    try:
                        self._analysis_callback(processed)
                    except Exception as e:
                        logger.error(f"Analysis callback error: {e}")
                        
            except queue.Full:
                self._dropped_frames += 1
                logger.warning("Frame queue full, dropping frame")
        else:
            logger.debug(
                f"Frame not significant (change={change_score:.2f}), skipping"
            )
        
        return processed
    
    def _decode_image(self, image_bytes: bytes) -> Optional[Image.Image]:
        """
        Safely decode image bytes to PIL Image.
        
        Handles JPEG, PNG, and other common formats.
        Returns None for invalid/empty data.
        """
        if not image_bytes or len(image_bytes) < 16:
            return None
        
        try:
            # Use proper byte-stream decoding
            img = Image.open(io.BytesIO(image_bytes))
            img.load()  # Force load to detect truncated images
            return img.convert("RGB")  # Normalize to RGB
        except Exception as e:
            logger.debug(f"Image decode failed: {type(e).__name__}: {e}")
            return None
    
    def _compute_hash(self, img: Image.Image) -> str:
        """Compute a perceptual hash of the image."""
        # Resize to small size for hash computation
        small = img.resize(
            (self.config.hash_bins, self.config.hash_bins),
            Image.Resampling.LANCZOS
        ).convert("L")
        
        # Compute hash based on pixel values
        pixels = list(small.getdata())
        avg = sum(pixels) / len(pixels)
        
        # Create binary hash
        bits = ''.join('1' if p > avg else '0' for p in pixels)
        
        # Convert to hex string
        hash_int = int(bits, 2)
        return format(hash_int, f'0{self.config.hash_bins * self.config.hash_bins // 4}x')
    
    def _compute_change(self, img: Image.Image) -> float:
        """
        Compute change score compared to recent frames.
        
        Returns:
            Float 0.0-1.0 representing fraction of changed pixels
        """
        if not self.config.enable_change_detection:
            return 1.0  # Always consider significant
            
        if len(self._frame_history) == 0:
            return 1.0  # First frame is always significant
        
        # Resize for comparison
        small = img.resize(
            (self.config.resize_width, self.config.resize_height),
            Image.Resampling.LANCZOS
        ).convert("L")
        
        current = np.array(small, dtype=np.float32)
        
        # Compare with most recent frame in history
        previous = self._frame_history[-1][0]  # Get numpy array from tuple
        
        # Compute difference
        diff = np.abs(current - previous) / 255.0
        change_score = np.mean(diff)
        
        return float(change_score)
    
    def _should_analyze(
        self, change_score: float, timestamp: float
    ) -> bool:
        """Determine if frame should be sent for analysis."""
        now = time.time()
        
        # Enforce minimum analysis interval
        elapsed = now - self._last_analysis_time
        if elapsed < self.config.analysis_interval:
            return False
        
        # Require minimum change threshold
        if change_score < self.config.change_threshold:
            return False
        
        return True
    
    def _update_frame_history(
        self, img: Image.Image, timestamp: float, frame_hash: str
    ) -> None:
        """Update frame history with new frame (called when submitting for analysis)."""
        # Resize for storage in history
        small = img.resize(
            (self.config.resize_width, self.config.resize_height),
            Image.Resampling.LANCZOS
        ).convert("L")
        arr = np.array(small, dtype=np.float32)
        self._frame_history.append((arr, timestamp, frame_hash))
    
    def mark_analysis_complete(self) -> None:
        """Call this when LLM analysis completes."""
        with self._lock:
            self._is_analyzing = False
            self._last_analysis_time = time.time()
            self._frames_since_analysis = 0
    
    def is_busy(self) -> bool:
        """Check if currently analyzing a frame."""
        return self._is_analyzing
    
    def set_analyzing(self, value: bool) -> None:
        """Set the analyzing state (thread-safe)."""
        with self._lock:
            self._is_analyzing = value
    
    @property
    def stats(self) -> dict:
        """Get processing statistics."""
        return {
            "total_frames": self._total_frames,
            "significant_frames": self._significant_frames,
            "duplicate_frames": self._duplicate_frames,
            "dropped_frames": self._dropped_frames,
            "invalid_frames": self._invalid_frames,
            "queue_size": self._frame_queue.qsize(),
            "history_size": len(self._frame_history),
            "is_analyzing": self._is_analyzing
        }
