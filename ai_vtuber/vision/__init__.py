"""AI VTuber - Screen Vision Module

This module provides live desktop and game screen-watching capabilities for Airi.

Components:
- ScreenCaptureService: Captures screenshots using MSS
- FrameProcessor: Detects significant changes and filters duplicates  
- GameCache: Persistent cache for recognized entities and UI state
- VisionAnalyzer: Analyzes screens using Gemma 4 E2B via LM Studio (OpenAI-compatible API)
- VisionManager: Orchestrates all components

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
from .frame_processor import FrameProcessor, FrameProcessingConfig, ProcessedFrame
from .game_cache import GameCache, CachedEntity, ScreenState
from .analyzer import VisionAnalyzer, VisionAnalysisResult, SceneInfo, StateInfo, EntityInfo
from .manager import VisionManager, VisionConfig


__all__ = [
    'ScreenCaptureService',
    'ScreenCaptureConfig', 
    'CapturedFrame',
    'FrameProcessor',
    'FrameProcessingConfig',
    'ProcessedFrame',
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
]
