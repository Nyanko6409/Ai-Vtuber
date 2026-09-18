"""AI VTuber - Frame Processing and Change Detection"""

import hashlib
import logging
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Callable, Deque, List

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


@dataclass
class ProcessedFrame:
    """A frame ready for analysis."""
    image_bytes: bytes
    timestamp: float
    change_score: float  # 0.0-1.0, how much changed from previous
    is_significant: bool  # Whether to send for analysis
    frame_hash: str


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
        
        # Frame history for change detection
        self._frame_history: Deque[np.ndarray] = deque(maxlen=5)
        self._last_hash: Optional[str] = None
        self._last_analysis_time: float = 0.0
        self._frames_since_analysis: int = 0
        
        # Queue for pending frames
        self._frame_queue: queue.Queue[ProcessedFrame] = queue.Queue(
            maxsize=config.max_queue_size
        )
        
        # Statistics
        self._total_frames: int = 0
        self._significant_frames: int = 0
        self._duplicate_frames: int = 0
        self._dropped_frames: int = 0
        
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
        logger.info("Frame processor stopped")
    
    def process_frame(self, image_bytes: bytes, timestamp: float) -> Optional[ProcessedFrame]:
        """
        Process a captured frame and determine if it should be analyzed.
        
        Args:
            image_bytes: JPEG-encoded image data
            timestamp: Frame timestamp
            
        Returns:
            ProcessedFrame if significant, None if skipped
        """
        if not self._running:
            return None
            
        self._total_frames += 1
        
        try:
            # Decode image
            img = Image.frombytes(
                "RGB",
                (image_bytes[0:4], image_bytes[4:8]),  # Placeholder
                image_bytes,
                "raw",
                "JPEG"
            )
        except Exception:
            # Fallback: load from bytes
            img = Image.open(io.BytesIO(image_bytes))
        
        # Compute perceptual hash
        frame_hash = self._compute_hash(img)
        
        # Check for duplicate
        if self._last_hash == frame_hash:
            self._duplicate_frames += 1
            logger.debug("Duplicate frame detected, skipping")
            return None
        
        # Compute change score
        change_score = self._compute_change(img)
        
        # Determine if significant
        is_significant = self._should_analyze(change_score, timestamp)
        
        processed = ProcessedFrame(
            image_bytes=image_bytes,
            timestamp=timestamp,
            change_score=change_score,
            is_significant=is_significant,
            frame_hash=frame_hash
        )
        
        if is_significant:
            self._significant_frames += 1
            self._last_hash = frame_hash
            self._frames_since_analysis += 1
            
            # Add to queue
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
    
    def _compute_hash(self, img: Image.Image) -> str:
        """Compute a perceptual hash of the image."""
        # Resize to small size
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
        
        # Compare with most recent frame
        previous = self._frame_history[-1]
        
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
    
    def mark_analysis_complete(self) -> None:
        """Call this when LLM analysis completes."""
        with self._lock:
            self._is_analyzing = False
            self._last_analysis_time = time.time()
            self._frames_since_analysis = 0
            
            # Update frame history
            # (done when frame is submitted for analysis)
    
    def is_busy(self) -> bool:
        """Check if currently analyzing a frame."""
        return self._is_analyzing
    
    def mark_frame_submitted(self, img: Image.Image) -> None:
        """Call when frame is submitted for LLM analysis."""
        # Update frame history for change detection
        small = img.resize(
            (self.config.resize_width, self.config.resize_height),
            Image.Resampling.LANCZOS
        ).convert("L")
        arr = np.array(small, dtype=np.float32)
        self._frame_history.append(arr)
    
    @property
    def stats(self) -> dict:
        """Get processing statistics."""
        return {
            "total_frames": self._total_frames,
            "significant_frames": self._significant_frames,
            "duplicate_frames": self._duplicate_frames,
            "dropped_frames": self._dropped_frames,
            "queue_size": self._frame_queue.qsize(),
            "is_analyzing": self._is_analyzing
        }


# Import io at module level for the fallback in process_frame
import io
