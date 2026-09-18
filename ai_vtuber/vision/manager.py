"""AI VTuber - Vision Manager (Orchestrator)"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any, Callable

from .screen_capture import ScreenCaptureService, ScreenCaptureConfig, CapturedFrame
from .frame_processor import FrameProcessor, FrameProcessingConfig, ProcessedFrame
from .game_cache import GameCache, ScreenState
from .analyzer import VisionAnalyzer, VisionAnalysisResult

logger = logging.getLogger(__name__)


@dataclass
class VisionConfig:
    """Configuration for the vision system."""
    enabled: bool = False
    source: str = "screen"  # 'screen' or 'window'
    monitor_index: int = 0
    on_demand_only: bool = True  # Only capture when explicitly requested (SIMPLIFIED)
    max_width: int = 1920  # Full HD resolution for better analysis
    max_height: int = 1080
    game_cache_enabled: bool = True
    inject_into_conversation: bool = True  # Whether to inject visual context into conversation
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'VisionConfig':
        """Create config from dictionary (e.g., YAML)."""
        return cls(
            enabled=data.get('enabled', False),
            source=data.get('source', 'screen'),
            monitor_index=data.get('monitor_index', 0),
            on_demand_only=data.get('on_demand_only', True),
            max_width=data.get('max_width', 1920),
            max_height=data.get('max_height', 1080),
            game_cache_enabled=data.get('game_cache_enabled', True),
            inject_into_conversation=data.get('inject_into_conversation', True)
        )


class VisionManager:
    """
    Orchestrates screen vision components.
    
    Responsibilities:
    - Start/stop all vision services
    - Route frames through processing pipeline
    - Manage analysis requests to LLM
    - Maintain current visual state
    - Provide thread-safe access to visual context
    - Support on-demand capture (only when asked)
    """
    
    def __init__(
        self,
        config: VisionConfig,
        llm_client=None,
        vision_model: str = "google/gemma-4-e2b"
    ):
        """
        Initialize vision manager.
        
        Args:
            config: Vision configuration
            llm_client: LLM client instance for vision analysis (must support images)
            vision_model: Model name for vision analysis (from config)
        """
        self.config = config
        self._llm_client = llm_client
        self._vision_model = vision_model
        
        self._running = False
        self._lock = threading.Lock()
        
        # On-demand mode: don't auto-capture, wait for explicit requests
        self._on_demand_mode = config.on_demand_only
        self._capture_requested = threading.Event()
        
        # SIMPLIFIED: Only on-demand mode is supported now
        # No continuous background capture - only capture when user asks something
        self._capture_config = None
        self._processor_config = None
        self._capture_service = None
        self._frame_processor = None
        
        self._game_cache: Optional[GameCache] = None
        if config.game_cache_enabled:
            self._game_cache = GameCache()
        
        self._analyzer: Optional[VisionAnalyzer] = None
        
        # State tracking
        self._current_state = ScreenState()
        self._last_significant_event: Optional[str] = None
        self._analysis_pending = False
        self._last_capture_time: float = 0.0
        self._last_context_injection_time: float = 0.0  # Track last context injection
        
        # Statistics
        self._frames_processed = 0
        self._analyses_completed = 0
        self._errors = 0
    
    def start(self) -> bool:
        """Start all vision services."""
        if not self.config.enabled:
            logger.info("Vision system disabled in config")
            return False
        
        if self._running:
            logger.warning("Vision system already running")
            return True
        
        logger.info("Starting vision system...")
        
        try:
            # Initialize analyzer if LLM client available
            if self._llm_client and self._llm_client.is_available():
                self._analyzer = VisionAnalyzer(
                    self._llm_client,
                    model=self._vision_model
                )
                logger.info(f"Vision analyzer initialized with {self._vision_model}")
            else:
                logger.warning("LLM client not available, vision analysis disabled")
            
            # SIMPLIFIED: Always in on-demand mode - no continuous capture
            logger.info("Vision system started in ON-DEMAND mode (only captures when asked)")
            
            self._running = True
            logger.info("Vision system started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start vision system: {e}")
            self.stop()
            return False
    
    def stop(self) -> None:
        """Stop all vision services."""
        logger.info("Stopping vision system...")
        self._running = False
        # No capture_service or frame_processor to stop anymore
        logger.info("Vision system stopped")
    
    def request_screen_analysis(self) -> bool:
        """
        Request an immediate screen capture and analysis.
        
        This is the primary method for on-demand vision.
        Call this when you want Airi to "look at the screen".
        
        Returns:
            True if analysis was initiated, False if busy or unavailable
        """
        if not self._running:
            logger.warning("Vision system not running, cannot capture")
            return False
        
        if not self._analyzer or not self._analyzer.is_available:
            logger.warning("Vision analyzer not available")
            return False
        
        # CRITICAL FIX: Set _analysis_pending BEFORE starting thread (race condition fix)
        if self._analysis_pending:
            logger.debug("[VISION DEBUG] Analysis already pending, skipping request")
            return False
        
        # Check if analyzer is busy using our internal flag instead of analyzer's state
        if self.is_analyzing:
            logger.debug("[VISION DEBUG] Analyzer busy, skipping request")
            return False
        
        # Check minimum time between captures
        now = time.time()
        min_interval = 3.0  # Minimum 3 seconds between on-demand captures
        if now - self._last_capture_time < min_interval:
            logger.debug(f"[VISION DEBUG] Too soon since last capture ({now - self._last_capture_time:.1f}s)")
            return False
        
        logger.info("[VISION DEBUG] On-demand screen capture requested")
        
        # Set pending flag synchronously BEFORE starting thread
        self._analysis_pending = True
        
        # Capture and analyze in background thread
        thread = threading.Thread(
            target=self._on_demand_capture_and_analyze,
            daemon=True,
            name="OnDemandVision"
        )
        thread.start()
        
        return True
    
    def _on_demand_capture_and_analyze(self) -> None:
        """Capture screen and analyze immediately (on-demand mode) using ScreenCaptureService."""
        request_id = f"req_{int(time.time() * 1000)}"
        logger.debug(f"[VISION {request_id}] Starting on-demand capture...")
        
        try:
            self._last_capture_time = time.time()
            self._analysis_pending = True
            
            # Use ScreenCaptureService.capture_once() - single unified capture path
            from .screen_capture import ScreenCaptureConfig
            
            config = ScreenCaptureConfig(
                monitor_index=self.config.monitor_index,
                max_width=self.config.max_width,
                max_height=self.config.max_height,
                jpeg_quality=85
            )
            
            capture_service = ScreenCaptureService(config)
            image_bytes = capture_service.capture_once()
            
            if not image_bytes:
                logger.error(f"[VISION {request_id}] Capture failed: no image data")
                self._errors += 1
                return
            
            logger.debug(f"[VISION {request_id}] Captured {len(image_bytes)} bytes, sending to LLM...")
            
            # Get cached state for context
            cached_state = None
            if self._game_cache:
                cached_state = self._game_cache.get_current_state().to_dict()
            
            # Analyze with LLM
            logger.debug(f"[VISION {request_id}] Calling LLM analyzer...")
            result = self._analyzer.analyze(
                image_bytes,
                cached_state=cached_state
            )
            logger.debug(f"[VISION {request_id}] LLM analysis completed: {result is not None}")
            
            if result:
                self._update_state_from_result(result, request_id=request_id)
                self._analyses_completed += 1
                
                # Update game cache
                if self._game_cache:
                    self._update_cache_from_result(result)
            
            self._frames_processed += 1
            
        except Exception as e:
            self._errors += 1
            logger.error(f"[VISION {request_id}] On-demand vision analysis error: {e}")
            
        finally:
            self._analysis_pending = False
            logger.debug(f"[VISION {request_id}] Vision analysis cycle complete")
            logger.debug("[VISION DEBUG] Vision analysis cycle complete")
    
    @property
    def is_running(self) -> bool:
        """Check if vision system is running."""
        return self._running
    
    @property
    def is_analyzing(self) -> bool:
        """Check if currently analyzing a frame."""
        # Use internal _analysis_pending flag instead of analyzer's busy state
        # This provides more reliable synchronization
        return self._analysis_pending
    
    def get_current_state(self) -> Dict[str, Any]:
        """
        Get current visual state (thread-safe).
        
        Returns dict suitable for LLM context injection.
        """
        with self._lock:
            state = self._current_state.to_dict()
            
            # Add cache info if available
            if self._game_cache:
                cached_entities = self._game_cache.get_cached_entities()
                state['cached_entities'] = len(cached_entities)
                
                # Include high-confidence entities
                important = []
                for entity in cached_entities[:10]:  # Limit to 10
                    if entity.confidence >= 0.8:
                        important.append({
                            'type': entity.entity_type,
                            'name': entity.name
                        })
                state['important_entities'] = important
            
            state['vision_active'] = self._running
            state['last_update'] = self._current_state.last_update
            
            return state
    
    def get_context_summary(self) -> str:
        """
        Get a concise text summary of visual context.
        
        Use this for injecting into LLM conversation when appropriate.
        Records the injection time to avoid repetition.
        """
        state = self.get_current_state()
        
        # Record injection time
        self._last_context_injection_time = time.time()
        
        parts = []
        
        # Game-specific fields (if playing a game)
        if state.get('game_name'):
            parts.append(f"Playing {state['game_name']}")
        
        if state.get('location'):
            parts.append(f"in {state['location']}")
        
        if state.get('in_combat'):
            parts.append("- Combat active")
        
        if state.get('in_menu'):
            parts.append("- In menu")
        
        if state.get('in_dialogue'):
            parts.append("- Dialogue box visible")
        
        if state.get('player_health_low'):
            parts.append("- LOW HEALTH WARNING")
        
        # Generic screen content fields (for any application)
        if state.get('app_name'):
            parts.append(f"Viewing: {state['app_name']}")
        
        if state.get('is_browser'):
            parts.append("- Browser window active")
        
        if state.get('is_video'):
            parts.append("- Video playing")
        
        if state.get('is_code'):
            parts.append("- Code editor open")
        
        if state.get('is_document'):
            parts.append("- Document visible")
        
        if state.get('is_social'):
            parts.append("- Social media/chat app")
        
        if state.get('is_image'):
            parts.append("- Image/photo displayed")
        
        if state.get('visible_text'):
            parts.append(f"Text: \"{state['visible_text'][:80]}...\"")
        
        if state.get('last_significant_event'):
            parts.append(f"- Event: {state['last_significant_event']}")
        
        if not parts:
            return ""
        
        return " | ".join(parts)
    
    def should_inject_context(self) -> bool:
        """
        Determine if visual context should be injected into conversation.
        
        Returns True when there's significant visual information that
        hasn't been shared yet and would enhance the conversation.
        
        In on-demand mode, this ALWAYS returns True after a recent analysis
        so Airi can reference what she just saw.
        """
        if not self._running:
            return False
        
        # In on-demand mode, inject context after any recent analysis
        if self.config.on_demand_only:
            # Check if we have recent visual state (within last 10 seconds)
            if self._current_state.last_update > 0:
                elapsed = time.time() - self._current_state.last_update
                if elapsed < 10.0:  # Recent analysis
                    return True
            return False
        
        # Continuous mode: only inject if explicitly enabled and significant event
        if not self.config.inject_into_conversation:
            return False
        
        state = self._current_state
        
        # Inject on significant state changes
        if state.in_combat and not state.in_menu:
            return True
        if state.player_health_low:
            return True
        if state.loading:
            return True
        if state.last_significant_event:
            return True
        
        return False
    
    # Removed: _on_frame_captured, _on_frame_ready, _analyze_frame - no longer needed for simplified on-demand mode
    
    def _update_state_from_result(
        self, 
        result: VisionAnalysisResult,
        request_id: str = "unknown"
    ) -> None:
        """Update current state from analysis result."""
        with self._lock:
            # Use structured scene and state from new JSON output
            if result.scene:
                if result.scene.game_name:
                    self._current_state.game_name = result.scene.game_name
                if result.scene.application:
                    self._current_state.app_name = result.scene.application
                if result.scene.location:
                    self._current_state.location = result.scene.location
            
            if result.state:
                if result.state.in_combat is not None:
                    self._current_state.in_combat = result.state.in_combat
                if result.state.in_menu is not None:
                    self._current_state.in_menu = result.state.in_menu
                if result.state.in_dialogue is not None:
                    self._current_state.in_dialogue = result.state.in_dialogue
                if result.state.loading is not None:
                    self._current_state.loading = result.state.loading
                if result.state.player_health_low is not None:
                    self._current_state.player_health_low = result.state.player_health_low
            
            # Handle visible text (list of strings)
            if result.visible_text:
                # Join multiple text snippets or take first one
                self._current_state.visible_text = result.visible_text[0][:200] if result.visible_text else None
            
            # Track significant events
            if result.significant_changes:
                event = "; ".join(result.significant_changes)
                if event != self._last_significant_event:
                    self._current_state.last_significant_event = event
                    self._last_significant_event = event
                    logger.info(f"[VISION {request_id}] Visual event: {event}")
            
            self._current_state.last_update = time.time()
    
    def _update_cache_from_result(self, result: VisionAnalysisResult) -> None:
        """Extract and cache entities from analysis result."""
        if not self._game_cache:
            return
        
        # Extract entities using simple heuristics
        # In production, you'd use better NLP or structured LLM output
        
        entities = self._analyzer.extract_entities_from_analysis(result)
        
        # Cache any extracted entities
        for char_name in entities.get('characters', []):
            self._game_cache.add_entity(
                'character', char_name,
                confidence=result.confidence,
                source='llm'
            )
        
        for enemy_name in entities.get('enemies', []):
            self._game_cache.add_entity(
                'enemy', enemy_name,
                confidence=result.confidence,
                source='llm'
            )
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Get vision system statistics."""
        stats = {
            "running": self._running,
            "frames_processed": self._frames_processed,
            "analyses_completed": self._analyses_completed,
            "errors": self._errors,
            "analysis_pending": self._analysis_pending
        }
        
        if self._capture_service:
            stats['capture'] = self._capture_service.stats
        
        if self._frame_processor:
            stats['processing'] = self._frame_processor.stats
        
        if self._analyzer:
            stats['analysis'] = self._analyzer.stats
        
        if self._game_cache:
            stats['cache'] = self._game_cache.stats
        
        return stats
