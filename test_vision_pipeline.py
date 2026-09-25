"""Tests for the synchronous vision analysis pipeline."""

import inspect
import threading
import time
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


def _make_pipeline_app(stream_enabled: bool, vision_delay: float = 0.3):
    """Build a minimal App-like object wired to run the real voice pipeline.

    Uses the real ConversationHistory so we can inspect exactly what visual
    context ends up in the LLM request. All heavy subsystems (mic, STT, TTS,
    avatar, memory) are replaced with mocks.
    """
    from ai_vtuber.core.app import App
    from ai_vtuber.core.conversation import ConversationHistory
    from ai_vtuber.core.state import State

    app = App.__new__(App)
    # Pre-seed all lazily-created subsystems with mocks so the read-only
    # properties (llm, stt, microphone, vad, ...) never touch real hardware.
    app._stt = None
    app._tts = None
    app._player = None
    app._microphone = Mock()
    app._vad = None
    app._avatar_controller = None
    app._pipeline_thread = None
    app.running = True
    app._fillers_loaded = False
    app._tts_audio_queue = __import__("queue").Queue(maxsize=8)
    app._lock = threading.Lock()
    app._vision_trigger_lock = threading.Lock()
    app._vision_context_ready = False
    app.config = {
        "llm": {"stream_enabled": stream_enabled},
        "audio": {},
        "stt": {"silence_duration": 0.5, "min_speech_duration": 0.2},
    }
    app.llm_timeout = None
    app._last_user_text = "what do you see on my screen?"
    app._avatar = None
    app.current_transcription = ""
    app.current_response = ""
    app.current_emotion = "neutral"

    app.conversation = ConversationHistory(
        max_messages=10, system_prompt="You are Airi.", soul_prompt="",
    )

    # Vision manager mock: analysis takes `vision_delay` seconds to simulate
    # capture + VLM round-trip.
    mock_result = Mock()
    mock_result.description = "A code editor is open."
    vision_manager = Mock()
    type(vision_manager).is_running = PropertyMock(return_value=True)
    type(vision_manager).is_analyzing = PropertyMock(return_value=False)
    vision_manager.config = VisionConfig(enabled=True, on_demand_only=True)
    vision_manager.analyze_screen_now = Mock(
        side_effect=lambda: (time.sleep(vision_delay), mock_result)[1]
    )
    vision_manager.get_context_summary = Mock(
        return_value="Screen shows a code editor with a Python file open."
    )
    vision_manager.should_inject_context = Mock(return_value=False)
    app._vision_manager = vision_manager

    # Memory manager mock
    app.memory_manager = Mock()
    app.memory_manager.build_context = Mock(return_value={"historical_context": ""})
    app.memory_manager.get_full_context = Mock(return_value="soul")

    # Mic / STT mocks: one utterance then stop the pipeline loop
    app._vad = Mock()          # backing field for the read-only `vad` property
    app._microphone.collect_speech = Mock(return_value=b"\x00" * 1024)
    app._stt = Mock()          # backing field for the read-only `stt` property
    app._stt.transcribe = Mock(side_effect=["what do you see on my screen?", ""])

    # State machine mock: record state transitions
    states = []
    app.state_machine = Mock()
    app.state_machine.force_state = Mock(
        side_effect=lambda s: states.append(s)
    )

    # LLM mock: records messages and whether vision was still running at call time
    llm_calls = []

    def fake_chat_stream(messages, timeout=None):
        llm_calls.append({
            "messages": messages,
            "vision_analyzing_at_call": vision_manager.is_analyzing,
        })
        yield "I see a code editor."
        app._pipeline_stop = True

    mock_llm = Mock()
    mock_llm.chat = Mock(side_effect=lambda messages, timeout=None: (
        llm_calls.append({"messages": messages,
                          "vision_analyzing_at_call": vision_manager.is_analyzing}),
        "I see a code editor.",
    )[1])
    mock_llm.chat_stream = fake_chat_stream
    app._llm = mock_llm  # backing field for the read-only `llm` property

    app._states = states
    app._llm_calls = llm_calls
    return app


class TestVisionLLMRaceCondition(unittest.TestCase):
    """Regression tests: streaming LLM must not start before vision context is ready."""

    def test_streaming_waits_for_vision_before_llm(self):
        """With stream_enabled=True, chat_stream must only be called AFTER
        analyze_screen_now finished, and the request must contain the visual context."""
        from ai_vtuber.core.state import State

        app = _make_pipeline_app(stream_enabled=True, vision_delay=0.3)
        events = []
        app._vision_manager.analyze_screen_now = Mock(
            side_effect=lambda: (events.append("vision_done"),
                                 time.sleep(0.3),
                                 Mock(description="code editor"))[2]
        )

        def patched_streaming(self_, timeout=None):
            events.append("llm_start")
            return orig_streaming(self_, timeout=timeout)

        orig_streaming = type(app)._generate_response_streaming
        with patch.object(type(app), "_generate_response_streaming",
                          new=patched_streaming):
            thread = threading.Thread(target=app._listen_and_process, daemon=True)
            thread.start()
            thread.join(timeout=10.0)

        self.assertFalse(thread.is_alive(), "pipeline thread did not finish")
        # The core ordering guarantee: vision completes BEFORE the LLM starts.
        self.assertEqual(events, ["vision_done", "llm_start"],
                         f"vision/LLM race: event order was {events}")
        # And the built LLM request actually contains the injected visual context.
        self.assertEqual(len(app._llm_calls), 1)
        call = app._llm_calls[0]
        system_msg = call["messages"][0]["content"]
        self.assertIn("CURRENT SCREEN CONTEXT", system_msg)
        self.assertIn("code editor", system_msg)
        self.assertFalse(call["vision_analyzing_at_call"],
                         "vision analysis was still running when the LLM request was sent")

    def test_nonstreaming_waits_for_vision_before_llm(self):
        """Same guarantee for the legacy blocking path."""
        app = _make_pipeline_app(stream_enabled=False, vision_delay=0.3)
        events = []
        original = app._vision_manager.analyze_screen_now

        def slow_analysis():
            result = original()
            events.append("vision_done")
            return result

        app._vision_manager.analyze_screen_now = Mock(side_effect=slow_analysis)

        def patched_generate(self_, timeout=None):
            events.append("llm_start")
            return orig_generate(self_, timeout=timeout)

        orig_generate = type(app)._generate_response
        with patch.object(type(app), "_generate_response",
                          new=patched_generate):
            thread = threading.Thread(target=app._listen_and_process, daemon=True)
            thread.start()
            thread.join(timeout=10.0)

        self.assertFalse(thread.is_alive(), "pipeline thread did not finish")
        self.assertEqual(events, ["vision_done", "llm_start"],
                         f"vision/LLM race: event order was {events}")
        call = app._llm_calls[0]
        system_msg = call["messages"][0]["content"]
        self.assertIn("CURRENT SCREEN CONTEXT", system_msg)

    def test_no_parallel_async_vision_trigger_left(self):
        """The racy parallel-vision helpers must no longer exist, and the
        pipeline must use the synchronous trigger for both modes."""
        from ai_vtuber.core.app import App

        self.assertFalse(hasattr(App, "_trigger_vision_async_if_needed"),
                         "async vision trigger reintroduces the streaming race")
        self.assertFalse(hasattr(App, "_run_async_vision_analysis"))

        source = inspect.getsource(App._listen_and_process)
        self.assertIn("_trigger_vision_if_needed", source)
        self.assertNotIn("_trigger_vision_async_if_needed", source)
        # Streaming must no longer skip the vision wait.
        self.assertNotIn("Starting LLM streaming while vision analyzes in parallel", source)


if __name__ == '__main__':
    unittest.main()
