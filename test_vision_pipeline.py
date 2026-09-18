"""Tests for the synchronous vision analysis pipeline."""

import unittest
from unittest.mock import Mock, PropertyMock, patch
from ai_vtuber.vision.manager import VisionManager, VisionConfig
from ai_vtuber.vision.analyzer import VisionAnalysisResult, SceneInfo, StateInfo


class TestSynchronousVisionAnalysis(unittest.TestCase):
    """Test the analyze_screen_now() synchronous API."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_client = Mock()
        self.mock_client.is_available = Mock(return_value=True)
        
        self.config = VisionConfig(
            enabled=True,
            on_demand_only=True,
            monitor_index=0,
            max_width=1920,
            max_height=1080
        )
        
        self.manager = VisionManager(
            self.config,
            llm_client=self.mock_client,
            vision_model='google/gemma-4-e2b'
        )
        
        # Mock capture service
        self.manager._capture_service = Mock()
        self.manager._capture_service.capture_once = Mock(return_value=b'fake_image_bytes')
        
        # Mock analyzer
        self.mock_analyzer = Mock()
        self.mock_result = VisionAnalysisResult(
            scene=SceneInfo(
                application='VS Code',
                application_type='code',
                game_name=None,
                location=None
            ),
            state=StateInfo(
                in_combat=False,
                in_menu=False,
                in_dialogue=False,
                loading=False,
                player_health_low=False
            ),
            observations=['Code editor open', 'Python file visible'],
            visible_text=['def main():', 'print("Hello")'],
            entities=[],
            events=[],
            confidence=0.85,
            description='VS Code with Python file open',
            significant_changes=[],
            timestamp=123456.0
        )
        self.mock_analyzer.analyze = Mock(return_value=self.mock_result)
        type(self.mock_analyzer).is_available = PropertyMock(return_value=True)
        self.manager._analyzer = self.mock_analyzer
        self.manager._running = True
        self.manager._game_cache = None  # Disable cache for tests
    
    def test_analyze_screen_now_returns_result(self):
        """Test that analyze_screen_now returns VisionAnalysisResult."""
        result = self.manager.analyze_screen_now()
        
        self.assertIsNotNone(result)
        self.assertIsInstance(result, VisionAnalysisResult)
        self.assertEqual(result.description, 'VS Code with Python file open')
        self.assertEqual(result.scene.application, 'VS Code')
    
    def test_analyze_screen_now_stores_result(self):
        """Test that result is stored in _latest_result."""
        result = self.manager.analyze_screen_now()
        
        self.assertIsNotNone(result)
        self.assertIs(self.manager._latest_result, result)
    
    def test_analyze_screen_now_calls_capture(self):
        """Test that capture_once is called."""
        self.manager.analyze_screen_now()
        
        self.manager._capture_service.capture_once.assert_called_once()
    
    def test_analyze_screen_now_calls_analyzer(self):
        """Test that analyzer.analyze is called with image bytes."""
        self.manager.analyze_screen_now()
        
        self.mock_analyzer.analyze.assert_called_once()
        call_args = self.mock_analyzer.analyze.call_args
        self.assertEqual(call_args[0][0], b'fake_image_bytes')  # First arg is image_bytes
    
    def test_analyze_screen_now_updates_state(self):
        """Test that state is updated from result."""
        self.manager.analyze_screen_now()
        
        self.assertEqual(self.manager._current_state.app_name, 'VS Code')
        self.assertEqual(self.manager._current_state.visible_text, 'def main():')
    
    def test_analyze_screen_now_when_not_running(self):
        """Test that analyze_screen_now returns None when not running."""
        self.manager._running = False
        
        result = self.manager.analyze_screen_now()
        
        self.assertIsNone(result)
    
    def test_analyze_screen_now_when_analyzer_unavailable(self):
        """Test that analyze_screen_now returns None when analyzer unavailable."""
        type(self.mock_analyzer).is_available = PropertyMock(return_value=False)
        
        result = self.manager.analyze_screen_now()
        
        self.assertIsNone(result)
    
    def test_analyze_screen_now_when_already_pending(self):
        """Test that analyze_screen_now returns None when analysis pending."""
        self.manager._analysis_pending = True
        
        result = self.manager.analyze_screen_now()
        
        self.assertIsNone(result)
    
    def test_analyze_screen_now_handles_capture_failure(self):
        """Test that analyze_screen_now handles capture failure."""
        self.manager._capture_service.capture_once = Mock(return_value=None)
        
        result = self.manager.analyze_screen_now()
        
        self.assertIsNone(result)
    
    def test_analyze_screen_now_handles_analysis_failure(self):
        """Test that analyze_screen_now handles analysis failure."""
        self.mock_analyzer.analyze = Mock(return_value=None)
        
        result = self.manager.analyze_screen_now()
        
        self.assertIsNone(result)
    
    def test_get_latest_result(self):
        """Test get_latest_result returns stored result."""
        self.manager.analyze_screen_now()
        
        retrieved = self.manager.get_latest_result()
        
        self.assertIsNotNone(retrieved)
        self.assertIs(retrieved, self.mock_result)
    
    def test_duplicate_detection(self):
        """Test that duplicate observations are detected."""
        # First analysis
        result1 = self.manager.analyze_screen_now()
        self.assertIsNotNone(result1)
        
        # Second identical analysis should be detected as duplicate
        result2 = self.manager.analyze_screen_now()
        self.assertIsNotNone(result2)
        # But state should not be updated twice for same observation


class TestAppVisionTrigger(unittest.TestCase):
    """Test App._trigger_vision_if_needed uses synchronous API."""
    
    def test_trigger_uses_analyze_screen_now(self):
        """Verify _trigger_vision_if_needed calls analyze_screen_now."""
        from ai_vtuber.core.app import App
        import inspect
        
        source = inspect.getsource(App._trigger_vision_if_needed)
        
        # Should use synchronous API
        self.assertIn('analyze_screen_now', source)
        
        # Should NOT use old background thread API
        self.assertNotIn('request_screen_analysis', source)
        
        # Should NOT have polling loop
        self.assertNotIn('while wait_time', source)
        self.assertNotIn('time.sleep', source)


if __name__ == '__main__':
    unittest.main()
