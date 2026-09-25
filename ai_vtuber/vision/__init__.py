"""AI VTuber - Screen Vision Module

This module provides live desktop and game screen-watching capabilities for Airi.

Components:
- ScreenCaptureService: Captures screenshots using MSS
- GameCache: Persistent cache for recognized entities and UI state
- VisionAnalyzer: Analyzes screens using Gemma 4 E2B via LM Studio (OpenAI-compatible API)
- VisionManager: Orchestrates all components (incl. the persistent /look target)
- look_command: Single authoritative parser/dispatcher for the /look chat command

Usage:
    from ai_vtuber.vision import VisionManager, VisionConfig

    config = VisionConfig.from_dict(config_yaml['vision'])
    vision = VisionManager(config, llm_client)
    vision.start()

    # Get current visual state
    state = vision.get_current_state()

    # Or use synchronous analysis for direct visual questions
    result = vision.analyze_screen_now()
"""

from .screen_capture import ScreenCaptureService, ScreenCaptureConfig, CapturedFrame
from .game_cache import GameCache, CachedEntity, ScreenState
from .analyzer import VisionAnalyzer, VisionAnalysisResult, SceneInfo, StateInfo, EntityInfo
from .manager import VisionManager, VisionConfig
from .look_command import LookCommand, parse_look_command, handle_look_command
from .windows_app_identifier import (
    get_active_application,
    describe_active_application,
    find_window_by_name,
    get_window_rect,
    Win32Bindings,
)


__all__ = [
    'ScreenCaptureService',
    'ScreenCaptureConfig',
    'CapturedFrame',
    'GameCache',
    'CachedEntity',
    'ScreenState',
    'VisionAnalyzer',
    'VisionAnalysisResult',
    'SceneInfo',
    'StateInfo',
    'EntityInfo',
    'VisionManager',
    'VisionConfig',
    # /look command (single authoritative parser/dispatcher)
    'LookCommand',
    'parse_look_command',
    'handle_look_command',
    # Windows 11 application identifier / target finder (Win32 user32/kernel32)
    'get_active_application',
    'describe_active_application',
    'find_window_by_name',
    'get_window_rect',
    'Win32Bindings',
]
