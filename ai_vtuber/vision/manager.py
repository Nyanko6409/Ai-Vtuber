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
    capture_interval: float = 0.5  # Seconds between captures
    analysis_interval: float = 5.0  # Minimum seconds between analyses
    change_detection: bool = True
    change_threshold: float = 0.15
    ocr_enabled: bool = False  # Reserved for future OCR integration
    game_cache_enabled: bool = True
    inject_into_conversation: bool = False  # Don't auto-inject into chat
    max_width: int = 1280
    max_height: int = 720
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'VisionConfig':
        """Create config from dictionary (e.g., YAML)."""
        return cls(
            enabled=data.get('enabled', False),
            source=data.get('source', 'screen'),
            monitor_index=data.get('monitor_index', 0),
            capture_interval=data.get('capture_interval', 0.5),
            analysis_interval=data.get('analysis_interval', 5.0),
            change_detection=data.get('change_detection', True),
            change_threshold=data.get('change_threshold', 0.15),
            ocr_enabled=data.get('ocr_enabled', False),
            game_cache_enabled=data.get('game_cache_enabled', True),
            inject_into_conversation=data.get('inject_into_conversation', False),
            max_width=data.get('max_width', 1280),
            max_height=data.get('max_height', 720)
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
        
        # Initialize components
        self._capture_config = ScreenCaptureConfig(
            monitor_index=config.monitor_index,
            capture_interval=config.capture_interval,
            enabled=config.enabled,
            max_width=config.max_width,
            max_height=config.max_height
        )
        
        self._processor_config = FrameProcessingConfig(
            analysis_interval=config.analysis_interval,
            change_threshold=config.change_threshold,
            enable_change_detection=config.change_detection
        )
        
        self._capture_service = ScreenCaptureService(self._capture_config)
        self._frame_processor = FrameProcessor(self._processor_config)
        
        self._game_cache: Optional[GameCache] = None
        if config.game_cache_enabled:
            self._game_cache = GameCache()
        
        self._analyzer: Optional[VisionAnalyzer] = None
        
        # State tracking
        self._current_state = ScreenState()
        self._last_significant_event: Optional[str] = None
        self._analysis_pending = False
        
        # Statistics
        self._frames_processed = 0
        self._analyses_completed = 0
        self._errors = 0
        
        # Set up callbacks
        self._capture_service.set_frame_callback(self._on_frame_captured)
        self._frame_processor.set_analysis_callback(self._on_frame_ready)
    
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
            
            # Start frame processor
            self._frame_processor.start()
            
            # Start screen capture
            if not self._capture_service.start():
                logger.error("Failed to start screen capture")
                self.stop()
                return False
            
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
        
        self._capture_service.stop()
        self._frame_processor.stop()
        
        logger.info("Vision system stopped")
    
    @property
    def is_running(self) -> bool:
        """Check if vision system is running."""
        return self._running
    
    @property
    def is_analyzing(self) -> bool:
        """Check if currently analyzing a frame."""
        return self._analyzer.is_busy if self._analyzer else False
    
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
        """
        state = self.get_current_state()
        
        parts = []
        
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
        """
        if not self.config.inject_into_conversation:
            return False
        
        if not self._running:
            return False
        
        state = self._current_state
        
        # Inject on significant state changes
        if state.in_combat and not state.in_menu:
            return True
        if state.player_health_low:
            return True
        if state.loading:
            return True
        
        return False
    
    def _on_frame_captured(self, frame: CapturedFrame) -> None:
        """Handle newly captured frame."""
        if not self._running:
            return
        
        try:
            self._frame_processor.process_frame(frame.image_bytes, frame.timestamp)
            
        except Exception as e:
            self._errors += 1
            logger.error(f"Frame processing error: {e}")
    
    def _on_frame_ready(self, processed: ProcessedFrame) -> None:
        """Handle frame ready for analysis."""
        if not self._running or self._analysis_pending:
            return
        
        if not self._analyzer or not self._analyzer.is_available:
            return
        
        if self._analyzer.is_busy:
            logger.debug("Analyzer busy, skipping frame")
            return
        
        self._analysis_pending = True
        self._frames_processed += 1
        
        # Submit for analysis in background thread
        thread = threading.Thread(
            target=self._analyze_frame,
            args=(processed,),
            daemon=True,
            name="VisionAnalysis"
        )
        thread.start()
    
    def _analyze_frame(self, processed: ProcessedFrame) -> None:
        """Perform vision analysis on a frame."""
        try:
            # Get cached state for context
            cached_state = None
            if self._game_cache:
                cached_state = self._game_cache.get_current_state().to_dict()
            
            # Analyze with LLM
            result = self._analyzer.analyze(
                processed.image_bytes,
                cached_state=cached_state
            )
            
            if result:
                self._update_state_from_result(result)
                self._analyses_completed += 1
                
                # Update game cache
                if self._game_cache:
                    self._update_cache_from_result(result)
            
        except Exception as e:
            self._errors += 1
            logger.error(f"Vision analysis error: {e}")
            
        finally:
            self._frame_processor.mark_analysis_complete()
            self._analysis_pending = False
    
    def _update_state_from_result(self, result: VisionAnalysisResult) -> None:
        """Update current state from analysis result."""
        with self._lock:
            gs = result.game_state
            
            if gs.get('in_combat') is not None:
                self._current_state.in_combat = gs['in_combat']
            if gs.get('in_menu') is not None:
                self._current_state.in_menu = gs['in_menu']
            if gs.get('in_dialogue') is not None:
                self._current_state.in_dialogue = gs['in_dialogue']
            if gs.get('loading') is not None:
                self._current_state.loading = gs['loading']
            if gs.get('player_health_low') is not None:
                self._current_state.player_health_low = gs['player_health_low']
            
            # Track significant events
            if result.significant_changes:
                event = "; ".join(result.significant_changes)
                if event != self._last_significant_event:
                    self._current_state.last_significant_event = event
                    self._last_significant_event = event
                    logger.info(f"Visual event: {event}")
            
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
