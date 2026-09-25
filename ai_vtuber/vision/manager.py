"""AI VTuber - Vision Manager (Orchestrator)"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any, Callable

from .screen_capture import ScreenCaptureService, ScreenCaptureConfig, CapturedFrame
from .game_cache import GameCache, ScreenState
from .analyzer import VisionAnalyzer, VisionAnalysisResult
from .look_command import LookCommand, parse_look_command
from .windows_app_identifier import (
    find_window_by_name,
    get_active_application,
    get_window_rect,
    describe_active_application,
    Win32Bindings,
)

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
    debug_save_captures: bool = False  # TEMPORARY: Save captured images for debugging
    debug_folder: str = "debug_captures"  # Folder for debug captures
    
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
            inject_into_conversation=data.get('inject_into_conversation', True),
            debug_save_captures=data.get('debug_save_captures', False),
            debug_folder=data.get('debug_folder', 'debug_captures')
        )


class VisionManager:
    """
    Orchestrates screen vision components.
    
    Responsibilities:
    - Start/stop all vision services
    - Manage analysis requests to LLM
    - Maintain current visual state
    - Provide thread-safe access to visual context
    - Support on-demand capture (only when asked)
    
    Architecture:
    VisionManager (single source of truth)
        ↓ uses on-demand
    ScreenCaptureService.capture_once()
        ↓
    VisionAnalyzer.analyze()
        ↓
    GameCache (optional persistence)
        ↓
    Airi Context (via get_context_summary)
    """
    
    def __init__(
        self,
        config: VisionConfig,
        llm_client=None,
        vision_model: str = "google/gemma-4-e2b",
        active_app_provider=None,
    ):
        """
        Initialize vision manager.
        
        Args:
            config: Vision configuration
            llm_client: LLM client instance for vision analysis (must support images)
            vision_model: Model name for vision analysis (from config)
            active_app_provider: Optional callable returning the foreground
                Windows application info dict (injectable for tests). Defaults
                to windows_app_identifier.get_active_application().
        """
        self.config = config
        self._llm_client = llm_client
        self._vision_model = vision_model
        # Windows 11 foreground-application identifier (native Win32 APIs).
        # Injectable so unit tests never depend on real desktop state.
        self._active_app_provider = active_app_provider or get_active_application
        
        self._running = False
        self._lock = threading.RLock()  # Reentrant lock for nested calls
        
        # On-demand mode: don't auto-capture, wait for explicit requests
        self._on_demand_mode = config.on_demand_only
        
        # Single capture service instance for on-demand use
        self._capture_service: Optional[ScreenCaptureService] = None
        
        self._game_cache: Optional[GameCache] = None
        if config.game_cache_enabled:
            self._game_cache = GameCache()
        
        self._analyzer: Optional[VisionAnalyzer] = None
        
        # State tracking - protected by _lock
        self._current_state = ScreenState()
        self._last_significant_event: Optional[str] = None
        self._analysis_pending = False
        self._last_capture_time: float = 0.0
        self._last_context_injection_time: float = 0.0
        self._last_observation_id: Optional[str] = None  # Deduplication
        
        # Windows 11 foreground application captured at analysis time.
        # Populated by the native Win32 identifier BEFORE each capture;
        # exposed to the LLM via get_current_state()/get_context_summary().
        self._active_application: Optional[Dict[str, Any]] = None
        
        # Store latest analysis result for retrieval
        self._latest_result: Optional[VisionAnalysisResult] = None
        self._latest_result_lock = threading.Lock()
        
        # Worker thread management
        self._worker_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        
        # Statistics
        self._frames_processed = 0
        self._analyses_completed = 0
        self._errors = 0

        # ------------------------------------------------------------------
        # /look vision target (persistent, independent of the foreground app)
        # ------------------------------------------------------------------
        # Once the user types "/look Discord" the vision system locks onto
        # that application's window: every subsequent capture grabs the
        # target window's rectangle instead of the full screen, even when a
        # different application is in the foreground.  The target REMAINS
        # locked even while it cannot be found on screen (status
        # "NOT FOUND") and is re-resolved automatically on each capture, so
        # the window only has to exist at capture time - not at set time.
        # Protected by ``self._lock``.
        self._vision_target_name: Optional[str] = None   # display name typed by user
        self._vision_target_query: Optional[str] = None  # normalized lowercase query
        self._vision_target_status: str = ""             # "Found" | "NOT FOUND" | ""
        self._vision_target_info: Optional[Dict[str, Any]] = None  # last successful match
        self._vision_target_window_provider: Callable[[str], Optional[Dict[str, Any]]] = \
            find_window_by_name  # injectable for tests

    # ------------------------------------------------------------------
    # /look command execution (parsing lives ONLY in look_command.py)
    # ------------------------------------------------------------------

    def execute_look_command(self, text: str) -> str:
        """Execute a parsed ``/look`` chat command against this manager.

        This is the single authoritative executor for ``/look``; both the
        UI submit path and the core App message path call it through
        :func:`handle_look_command` (which itself delegates here).

        Returns the human-readable response for the existing status/chat
        UI, e.g.::

            "\U0001F50E Vision target: Discord\nStatus: Found"
            "\U0001F50E Vision target: Discord\nStatus: NOT FOUND"
            "\U0001F50E Vision target cleared."

        Raises ``ValueError`` if ``text`` is not a ``/look`` command.
        """
        cmd = parse_look_command(text)
        if cmd is None:
            raise ValueError(f"Not a /look command: {text!r}")

        if cmd.action == "clear":
            self.clear_vision_target()
            return "\U0001F50E Vision target cleared."

        if cmd.action == "status":
            with self._lock:
                name = self._vision_target_name
                query = self._vision_target_query
            if not name:
                return "\U0001F50E No vision target set. Use \"/look <app>\" (e.g. \"/look Discord\") or \"/look off\"."
            # Re-check current availability without changing the lock.
            info = self._find_target_window(query)
            with self._lock:
                self._vision_target_status = "Found" if info else "NOT FOUND"
                if info:
                    self._vision_target_info = info
                status = self._vision_target_status
            return f"\U0001F50E Vision target: {name}\nStatus: {status}\nWindow: {name}"

        # action == "set"
        display_name, status = self.set_vision_target(cmd.query)
        return f"\U0001F50E Vision target: {display_name}\nStatus: {status}"

    def set_vision_target(self, query: str) -> tuple:
        """Lock vision capture onto the window matching ``query``.

        The query must already be normalized (lowercase, whitespace
        collapsed) - :func:`ai_vtuber.vision.look_command.parse_look_command`
        does that.  Matching is case-insensitive and resolves through
        ``APP_ALIASES`` (``discord`` -> Discord.exe, ``vs code`` ->
        Code.exe, ``genshin impact`` -> GenshinImpact.exe, ...).

        IMPORTANT: the target persists independently of the foreground
        application and stays locked even when the window is currently
        missing (status ``NOT FOUND``); it is re-resolved on every capture.
        There is NO fallback to whatever happens to be in front.

        Returns ``(display_name, status)`` where status is ``"Found"`` or
        ``"NOT FOUND"``.
        """
        norm = " ".join((query or "").split()).lower()
        if not norm:
            raise ValueError("Vision target query must not be empty")

        info = self._find_target_window(norm)
        display_name = (info.get("application") if info else None) or norm.title()

        with self._lock:
            self._vision_target_name = display_name
            self._vision_target_query = norm
            self._vision_target_status = "Found" if info else "NOT FOUND"
            self._vision_target_info = info

        logger.info(
            f"Vision target set: {display_name!r} (query={norm!r}) -> "
            f"{self._vision_target_status}"
        )
        return display_name, self._vision_target_status

    def get_vision_target(self) -> Optional[Dict[str, Any]]:
        """Return the current vision target state (or ``None`` when unset).

        Keys: ``name``, ``query``, ``status`` ("Found"/"NOT FOUND"),
        ``window_title``, ``process_name``, ``hwnd``, ``rect`` (last known).
        """
        with self._lock:
            if not self._vision_target_name:
                return None
            info = self._vision_target_info or {}
            return {
                "name": self._vision_target_name,
                "query": self._vision_target_query,
                "status": self._vision_target_status,
                "window_title": info.get("window_title"),
                "process_name": info.get("process_name"),
                "hwnd": info.get("hwnd"),
                "rect": info.get("rect"),
            }

    def clear_vision_target(self) -> None:
        """Clear the vision target; capture returns to the full screen."""
        with self._lock:
            had = self._vision_target_name
            self._vision_target_name = None
            self._vision_target_query = None
            self._vision_target_status = ""
            self._vision_target_info = None
        if had:
            logger.info(f"Vision target cleared (was {had!r})")

    def _find_target_window(self, norm_query: Optional[str]) -> Optional[Dict[str, Any]]:
        """Resolve a normalized query to a live window dict (never raises)."""
        if not norm_query:
            return None
        try:
            return self._vision_target_window_provider(norm_query)
        except Exception as e:
            logger.debug(f"Vision target window lookup failed for {norm_query!r}: {e}")
            return None

    @staticmethod
    def _describe_vision_target(target: Dict[str, Any]) -> str:
        """Format vision-target metadata as a line suitable for LLM context.

        Example::

            'Vision Target: Discord | Window: Discord | Process: Discord.exe | '
            'Window Title: #general - Discord | Status: Found'
        """
        name = target.get("name") or "Unknown"
        parts = [f"Vision Target: {name}"]
        parts.append(f"Window: {name}")
        if target.get("process_name"):
            parts.append(f"Process: {target['process_name']}")
        if target.get("window_title"):
            parts.append(f'Window Title: "{target["window_title"][:120]}"')
        if target.get("status"):
            parts.append(f"Status: {target['status']}")
        return " | ".join(parts)

    def _resolve_target_for_capture(self) -> Optional[Dict[str, Any]]:
        """Re-resolve the locked target right before a capture.

        Returns the fresh window info when the target window currently
        exists (updating status to ``Found``), otherwise ``None`` (status
        updated to ``NOT FOUND``).  When no target is set at all this also
        returns ``None`` and leaves the status untouched.  A disappearing
        or minimized window between resolution and capture is handled
        safely downstream (the region-limited capture validates the rect
        against the monitor bounds; an out-of-bounds frame falls back to
        nothing rather than capturing the wrong area).
        """
        with self._lock:
            query = self._vision_target_query
        if not query:
            return None

        info = self._find_target_window(query)
        with self._lock:
            if not self._vision_target_query:  # cleared concurrently
                return None
            self._vision_target_status = "Found" if info else "NOT FOUND"
            if info:
                self._vision_target_info = info
        return info

    def _capture_image_bytes(self) -> Optional[bytes]:
        """Capture one JPEG frame honoring the persistent /look target.

        - No target set           -> full-screen capture (existing path).
        - Target found            -> capture exactly the target window's
                                     rectangle via the existing
                                     ScreenCaptureService region support.
        - Target locked but NOT FOUND -> capture NOTHING (returns None).
                                     Never falls back to the foreground
                                     application or the full screen.
        """
        target_info = self._resolve_target_for_capture()

        with self._lock:
            has_target = bool(self._vision_target_query)

        if has_target and target_info is None:
            name = self._vision_target_name or self._vision_target_query
            logger.info(
                f"Vision target {name!r} window not found; skipping capture "
                "(no fallback to foreground app)"
            )
            return None

        service = self._capture_service
        if service is None:
            logger.error("Capture service not initialized")
            return None

        if target_info is None:
            # Un-targeted: original full-monitor capture path.
            if service.config.region is not None:
                service.config.region = None
            return service.capture_once()

        rect = target_info.get("rect") or get_window_rect(target_info.get("hwnd"))
        if not rect:
            # Window vanished/minimized between resolve and rect read.
            with self._lock:
                self._vision_target_status = "NOT FOUND"
            logger.info("Vision target window rectangle unavailable; skipping capture")
            return None

        old_region = service.config.region
        service.config.region = tuple(int(v) for v in rect)
        try:
            image_bytes = service.capture_once()
        finally:
            service.config.region = old_region
        if not image_bytes:
            with self._lock:
                self._vision_target_status = "NOT FOUND"
            logger.info("Region capture of vision target returned no data")
        return image_bytes

    def start(self) -> bool:
        """Start all vision services."""
        if not self.config.enabled:
            logger.info("Vision system disabled in config")
            return False
        
        with self._lock:
            if self._running:
                logger.warning("Vision system already running")
                return True
            
            logger.info("Starting vision system...")
            
            try:
                # Initialize capture service for on-demand use
                capture_config = ScreenCaptureConfig(
                    monitor_index=self.config.monitor_index,
                    max_width=self.config.max_width,
                    max_height=self.config.max_height,
                    jpeg_quality=85,
                    enabled=False,  # Disabled by default, only used on-demand
                    debug_save_captures=self.config.debug_save_captures,
                    debug_folder=self.config.debug_folder
                )
                self._capture_service = ScreenCaptureService(capture_config)
                
                # Initialize analyzer if LLM client available
                if self._llm_client and self._llm_client.is_available():
                    self._analyzer = VisionAnalyzer(
                        self._llm_client,
                        model=self._vision_model
                    )
                    logger.info(f"Vision analyzer initialized with {self._vision_model}")
                else:
                    logger.warning("LLM client not available, vision analysis disabled")
                
                self._running = True
                self._shutdown_event.clear()
                logger.info("Vision system started successfully in ON-DEMAND mode")
                return True
                
            except Exception as e:
                logger.error(f"Failed to start vision system: {e}")
                self._cleanup_services()
                return False
    
    def _cleanup_services(self) -> None:
        """Clean up internal services."""
        if self._capture_service:
            try:
                self._capture_service.stop()
            except Exception:
                pass
            self._capture_service = None
    
    def stop(self) -> None:
        """Stop all vision services and clean up resources."""
        logger.info("Stopping vision system...")
        
        with self._lock:
            if not self._running:
                return  # Already stopped (idempotent)
            
            self._running = False
            self._shutdown_event.set()
        
        # Wait for worker thread to finish
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=3.0)
        
        # Clean up services
        self._cleanup_services()
        
        # Clear state
        with self._lock:
            self._analysis_pending = False
            self._worker_thread = None
        
        logger.info("Vision system stopped")
    
    def _refresh_active_application(self, request_id: str = "unknown") -> Optional[Dict[str, Any]]:
        """
        Detect the Windows 11 foreground application via native Win32 APIs.

        Must be called BEFORE each screen capture so the identifier reflects
        the application that was actually in front when the frame was taken.
        The vision model / LLM is never asked to identify the application -
        it is resolved from the real process executable.

        Never raises: on any failure (no foreground window, inaccessible
        process, permission error) the stored value becomes None and analysis
        continues normally.
        """
        try:
            info = self._active_app_provider()
        except Exception as e:
            logger.debug(f"[VISION {request_id}] Active app detection failed: {e}")
            info = None

        with self._lock:
            self._active_application = info

        if info:
            logger.info(
                f"[VISION {request_id}] Foreground app: "
                f"{info.get('application')} ({info.get('process_name')}, "
                f"PID {info.get('pid')})"
            )
        return info

    def get_active_application_info(self) -> Optional[Dict[str, Any]]:
        """
        Thread-safe access to the Windows foreground application info
        captured during the most recent screen analysis.

        Returns dict with keys: application, process_name, window_title,
        pid, hwnd - or None if unavailable.
        """
        with self._lock:
            return self._active_application

    def analyze_screen_now(self) -> Optional[VisionAnalysisResult]:
        """
        Synchronous screen capture and analysis.
        
        This method captures the screen immediately, analyzes it with the vision model,
        updates internal state and cache, and returns the actual VisionAnalysisResult.
        
        Use this for direct visual questions like "What do you see?" where you need
        the actual result synchronously rather than triggering background analysis.
        
        Returns:
            VisionAnalysisResult if successful, None if failed or unavailable
            
        Thread Safety:
            - Uses lock to prevent concurrent analysis
            - Safe to call from any thread
        """
        if not self._running:
            logger.warning("Vision system not running, cannot analyze screen")
            return None
        
        if not self._analyzer or not self._analyzer.is_available:
            logger.warning("Vision analyzer not available")
            return None
        
        # Check if already analyzing (prevent reentrant calls)
        if self._analysis_pending:
            logger.debug("Analysis already pending, skipping synchronous request")
            return None
        
        request_id = f"sync_{int(time.time() * 1000)}"
        observation_id = f"obs_{int(time.time() * 1000)}"
        
        logger.info(f"[VISION {request_id}] Starting synchronous screen analysis...")
        
        try:
            # Set pending flag
            self._analysis_pending = True
            
            # Capture screen using ScreenCaptureService
            if not self._capture_service:
                logger.error(f"[VISION {request_id}] Capture service not initialized")
                return None
            
            # Detect the Windows 11 foreground application BEFORE capture so
            # each analysis knows which app was active when the frame was taken.
            self._refresh_active_application(request_id=request_id)

            # Capture honoring the persistent /look vision target (window
            # region capture, or no capture at all while the locked target
            # window is missing - never a fallback to the foreground app).
            image_bytes = self._capture_image_bytes()
            
            if not image_bytes:
                logger.error(f"[VISION {request_id}] Capture failed: no image data")
                return None
            
            logger.debug(f"[VISION {request_id}] Captured {len(image_bytes)} bytes")
            
            # Get cached state for context (defensive copy)
            cached_state = None
            if self._game_cache:
                cached_state = self._game_cache.get_current_state().to_dict()
            
            # Analyze with LLM (synchronous, blocking call)
            result = self._analyzer.analyze(
                image_bytes,
                cached_state=cached_state
            )
            
            if not result:
                logger.error(f"[VISION {request_id}] Analysis returned no result")
                return None
            
            logger.info(f"[VISION {request_id}] Analysis completed successfully")
            
            # Store the result for later retrieval (thread-safe)
            with self._latest_result_lock:
                self._latest_result = result
            
            # Check for duplicate observations before updating state
            obs_hash = self._compute_observation_hash(result)
            if obs_hash != self._last_observation_id:
                self._last_observation_id = obs_hash
                self._update_state_from_result(result, request_id=request_id, observation_id=observation_id)
                self._analyses_completed += 1
                
                # Update game cache
                if self._game_cache:
                    self._update_cache_from_result(result)
            else:
                logger.debug(f"[VISION {request_id}] Duplicate observation detected")
            
            self._frames_processed += 1
            self._last_capture_time = time.time()
            
            return result
            
        except Exception as e:
            self._errors += 1
            logger.error(f"[VISION {request_id}] Synchronous analysis error: {e}")
            return None
            
        finally:
            with self._lock:
                self._analysis_pending = False
    
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
        
        # Clear any previous result before starting new analysis
        with self._latest_result_lock:
            self._latest_result = None
        
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
    
    def get_latest_result(self) -> Optional[VisionAnalysisResult]:
        """
        Get the most recent vision analysis result.
        
        Thread-safe access to the latest VisionAnalysisResult.
        Returns None if no analysis has been completed yet.
        
        Returns:
            Latest VisionAnalysisResult or None
        """
        with self._latest_result_lock:
            return self._latest_result
    
    def _on_demand_capture_and_analyze(self) -> None:
        """Capture screen and analyze immediately (on-demand mode) using ScreenCaptureService."""
        request_id = f"req_{int(time.time() * 1000)}"
        observation_id = f"obs_{int(time.time() * 1000)}"
        logger.debug(f"[VISION {request_id}] Starting on-demand capture...")
        
        try:
            self._last_capture_time = time.time()
            
            # Use the pre-initialized capture service (unified capture path)
            if not self._capture_service:
                logger.error(f"[VISION {request_id}] Capture service not initialized")
                self._errors += 1
                return
            
            # Detect the Windows 11 foreground application BEFORE capture so
            # each analysis knows which app was active when the frame was taken.
            self._refresh_active_application(request_id=request_id)

            # Capture honoring the persistent /look vision target (window
            # region capture, or no capture at all while the locked target
            # window is missing - never a fallback to the foreground app).
            image_bytes = self._capture_image_bytes()
            
            if not image_bytes:
                logger.error(f"[VISION {request_id}] Capture failed: no image data")
                self._errors += 1
                return
            
            logger.debug(f"[VISION {request_id}] Captured {len(image_bytes)} bytes, sending to LLM...")
            
            # Get cached state for context (defensive copy)
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
                # Store the latest result for retrieval (thread-safe)
                with self._latest_result_lock:
                    self._latest_result = result
                
                # Check for duplicate observations before updating state
                obs_hash = self._compute_observation_hash(result)
                if obs_hash == self._last_observation_id:
                    logger.debug(f"[VISION {request_id}] Duplicate observation detected, skipping state update")
                else:
                    self._last_observation_id = obs_hash
                    self._update_state_from_result(result, request_id=request_id, observation_id=observation_id)
                    self._analyses_completed += 1
                    
                    # Update game cache
                    if self._game_cache:
                        self._update_cache_from_result(result)
            
            self._frames_processed += 1
            
        except Exception as e:
            self._errors += 1
            logger.error(f"[VISION {request_id}] On-demand vision analysis error: {e}")
            
        finally:
            with self._lock:
                self._analysis_pending = False
            logger.debug(f"[VISION {request_id}] Vision analysis cycle complete")
    
    def _compute_observation_hash(self, result: VisionAnalysisResult) -> str:
        """Compute a hash of the observation for deduplication."""
        import hashlib
        
        # Create a signature from key fields
        parts = []
        if result.scene:
            parts.append(f"scene:{result.scene.application}:{result.scene.game_name}:{result.scene.location}")
        if result.state:
            parts.append(f"state:{result.state.in_combat}:{result.state.in_menu}:{result.state.in_dialogue}")
        if result.observations:
            parts.append(f"obs:{len(result.observations)}")
        
        signature = "|".join(parts)
        return hashlib.sha256(signature.encode()).hexdigest()[:16]
    
    @property
    def is_running(self) -> bool:
        """Check if vision system is running."""
        return self._running
    
    @property
    def is_analyzing(self) -> bool:
        """Check if currently analyzing a frame.
        
        This property correctly reflects the analysis state from the moment
        request_screen_analysis() sets _analysis_pending=True until the 
        background thread completes and resets it to False.
        
        This covers the entire capture+analyze pipeline, including:
        - Screen capture via mss
        - Image resize and JPEG encoding  
        - LLM API call
        - Response parsing
        
        Returns True if any analysis is in progress, False otherwise.
        """
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
            
            # Windows 11 foreground application captured with this analysis
            # (resolved from the real process executable, not the vision model)
            if self._active_application:
                state['active_application'] = dict(self._active_application)

            # /look vision target (persistent; independent of the foreground app)
            if self._vision_target_name:
                info = self._vision_target_info or {}
                state['vision_target'] = {
                    'name': self._vision_target_name,
                    'query': self._vision_target_query,
                    'status': self._vision_target_status,
                    'window_title': info.get('window_title'),
                    'process_name': info.get('process_name'),
                }

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

        # /look vision target metadata (locked window; independent of which
        # application happens to be in the foreground). Listed FIRST so the
        # LLM always knows exactly which window the captured frame shows.
        vision_target = state.get('vision_target')
        if vision_target:
            parts.append(self._describe_vision_target(vision_target))

        # Windows 11 foreground application (native Win32 identifier, resolved
        # from the actual process executable). Listed first so Airi always
        # knows which app was active when the screen was captured.
        active_app = state.get('active_application')
        if active_app:
            app_line = describe_active_application(active_app)
            if app_line:
                parts.append(app_line)
        
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
        
        # Generic application/screen content - show app_name first if available
        if state.get('app_name'):
            parts.append(f"Viewing: {state['app_name']}")
        
        # Add type flags only if they provide additional info beyond app_name
        # (avoid redundancy like "Viewing: Chrome | Browser window active")
        has_type_flag = False
        if state.get('is_browser') and not state.get('app_name'):
            parts.append("- Browser window active")
            has_type_flag = True
        elif state.get('is_video') and not state.get('app_name'):
            parts.append("- Video playing")
            has_type_flag = True
        elif state.get('is_code') and not state.get('app_name'):
            parts.append("- Code editor open")
            has_type_flag = True
        elif state.get('is_document') and not state.get('app_name'):
            parts.append("- Document visible")
            has_type_flag = True
        elif state.get('is_social') and not state.get('app_name'):
            parts.append("- Social media/chat app")
            has_type_flag = True
        elif state.get('is_image') and not state.get('app_name'):
            parts.append("- Image/photo displayed")
            has_type_flag = True
        
        # If we have both app_name and a type, add the type as extra context
        if state.get('app_name') and has_type_flag:
            # Remove the redundant type-only entry, it's implied by app_name
            pass  # The type flag was already skipped above since app_name exists
        
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
        request_id: str = "unknown",
        observation_id: Optional[str] = None
    ) -> None:
        """
        Update current state from analysis result.
        
        Args:
            result: Vision analysis result
            request_id: Request tracking ID for logging
            observation_id: Unique ID for this observation (for provenance)
        """
        with self._lock:
            # Prefer the NATIVE Windows 11 foreground-application identifier
            # (resolved from the actual process executable via Win32 APIs)
            # over whatever the vision model guessed from the screenshot.
            # This does not change the vision prompt or model - it only
            # overrides the app name in our internal state when we know the
            # real answer from the OS.
            native_app = None
            if self._active_application:
                native_app = self._active_application.get('application')

            # Use structured scene and state from new JSON output
            if result.scene:
                if result.scene.game_name:
                    self._current_state.game_name = result.scene.game_name
                if native_app:
                    self._current_state.app_name = native_app
                elif result.scene.application:
                    self._current_state.app_name = result.scene.application
                if result.scene.location:
                    self._current_state.location = result.scene.location
                
                # Map application_type to boolean flags for context summary
                app_type = result.scene.application_type
                if app_type:
                    self._current_state.is_browser = (app_type == 'browser')
                    self._current_state.is_video = (app_type == 'video')
                    self._current_state.is_code = (app_type == 'code')
                    self._current_state.is_document = (app_type == 'document')
                    self._current_state.is_social = (app_type == 'social')
                    self._current_state.is_image = (app_type == 'image')
                    # Don't set any flag for 'game' (use game_name) or 'other'
            
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
            
            # Store observation ID for provenance tracking
            if observation_id:
                logger.debug(f"[VISION {request_id}] Observation ID: {observation_id}")
    
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
        
        if self._analyzer:
            stats['analysis'] = self._analyzer.stats
        
        if self._game_cache:
            stats['cache'] = self._game_cache.stats
        
        return stats
