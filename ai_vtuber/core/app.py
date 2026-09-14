"""AI VTuber - Main Application Controller"""

import logging
import queue
import re
import threading
import time
from pathlib import Path
from typing import Optional, Iterator

import numpy as np

from .state import State, StateMachine
from .conversation import ConversationHistory
from ..llm.lmstudio import LMStudioClient
from ..stt.whisper import WhisperSTT
from ..tts.kitten import KittenTTS, split_text_into_chunks
from ..avatar.live2d import Live2DAvatar
from ..audio.microphone import Microphone
from ..audio.vad import VoiceActivityDetector
from ..audio.playback import AudioPlayer
from ..memory.manager import MemoryManager
from ..emotion.analyzer import analyze_response

logger = logging.getLogger(__name__)


class App:
    """Main application controller - orchestrates the VTuber pipeline."""

    def __init__(self, config: dict) -> None:
        self.config = config
        self.state_machine = StateMachine()
        self.running = False

        # Initialize memory manager (loads soul, user facts, bot memories)
        self.memory_manager = MemoryManager()

        # No LLM timeout - wait indefinitely for response
        self.llm_timeout: Optional[int] = None

        # Initialize conversation history with system prompt and soul
        self.conversation = ConversationHistory(
            max_messages=config["llm"]["max_history"],
            system_prompt=config["llm"]["system_prompt"],
            soul_prompt=self.memory_manager.get_full_context(),
            max_context=config["llm"]["max_context"],
            reserved_output_tokens=config["llm"]["max_tokens"]
        )

        # Current state for UI
        self.current_transcription: str = ""
        self.current_response: str = ""
        self.current_emotion: str = "neutral"

        # Components (initialized lazily)
        self._llm: Optional[LMStudioClient] = None
        self._stt: Optional[WhisperSTT] = None
        self._tts: Optional[KittenTTS] = None
        self._avatar: Optional[Live2DAvatar] = None
        self._microphone: Optional[Microphone] = None
        self._vad: Optional[VoiceActivityDetector] = None
        self._player: Optional[AudioPlayer] = None
        
        # Filler audio data loaded at startup
        self._fillers: list[tuple[np.ndarray, int]] = []  # (audio_array, duration_ms)
        self._fillers_loaded: bool = False

        # Threading
        self._pipeline_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # Avatar drag state for mouse controls
        self._avatar_start_drag: bool = False

    @property
    def llm(self) -> LMStudioClient:
        if self._llm is None:
            self._llm = LMStudioClient(self.config["llm"])
        return self._llm

    @property
    def stt(self) -> WhisperSTT:
        if self._stt is None:
            self._stt = WhisperSTT(self.config["stt"])
        return self._stt

    @property
    def tts(self) -> KittenTTS:
        if self._tts is None:
            self._tts = KittenTTS(self.config["tts"])
        return self._tts

    @property
    def avatar(self) -> Live2DAvatar:
        if self._avatar is None:
            self._avatar = Live2DAvatar(self.config["avatar"])
        return self._avatar

    @property
    def microphone(self) -> Microphone:
        if self._microphone is None:
            self._microphone = Microphone(self.config["audio"])
        return self._microphone

    @property
    def vad(self) -> VoiceActivityDetector:
        if self._vad is None:
            self._vad = VoiceActivityDetector(self.config["stt"])
        return self._vad

    @property
    def player(self) -> AudioPlayer:
        if self._player is None:
            self._player = AudioPlayer(self.config["tts"])
        return self._player

    def start(self) -> None:
        """Start the VTuber application."""
        logger.info("Starting AI VTuber...")
        self.running = True

        # Initialize components
        try:
            _ = self.llm
            logger.info("LLM client initialized")
        except Exception as e:
            logger.warning(f"LLM not available: {e}")

        try:
            _ = self.stt
            logger.info("STT model loaded")
        except Exception as e:
            logger.error(f"STT failed to load: {e}")
            self.state_machine.set_error(f"STT Error: {e}")
            return

        try:
            _ = self.tts
            logger.info("TTS model loaded")
        except Exception as e:
            logger.error(f"TTS failed to load: {e}")
            self.state_machine.set_error(f"TTS Error: {e}")
            return

        try:
            _ = self.avatar
            logger.info("Avatar module loaded (model will load after OpenGL context)")
        except Exception as e:
            logger.warning(f"Avatar not available: {e}")
            self._avatar = None  # Ensure it's None so main.py can check

        # Start microphone
        try:
            self.microphone.start()
            logger.info("Microphone started")
        except Exception as e:
            logger.error(f"Microphone failed: {e}")
            self.state_machine.set_error(f"Microphone Error: {e}")
            return

        self.state_machine.force_state(State.IDLE)
        logger.info("AI VTuber started successfully")
    
    def toggle_microphone(self) -> None:
        """Toggle microphone on/off."""
        if self._microphone is None:
            logger.warning("Microphone not initialized")
            return
        
        if self.microphone.is_muted():
            self.microphone.unmute()
            logger.info("Microphone unmuted")
        else:
            self.microphone.mute()
            logger.info("Microphone muted")
        
        # Load filler audio data after TTS is initialized
        self._load_fillers()

    def _load_fillers(self) -> None:
        """Load pre-rendered filler audio files from disk.
        
        Fills self._fillers with (audio_array, duration_ms) tuples.
        Logs a warning and disables fillers if folder is empty/missing.
        """
        if not self.config.get("fillers", {}).get("enabled", True):
            logger.info("Filler system disabled in config")
            self._fillers_loaded = False
            return
        
        try:
            fillers_dir = Path(__file__).parent.parent / "data" / "fillers"
            
            if not fillers_dir.exists():
                logger.warning(f"Fillers directory not found: {fillers_dir}, disabling filler system")
                self._fillers_loaded = False
                return
            
            filler_files = sorted(fillers_dir.glob("filler_*.npy"))
            
            if not filler_files:
                logger.warning(f"No filler files found in {fillers_dir}, disabling filler system")
                self._fillers_loaded = False
                return
            
            loaded_count = 0
            for filler_path in filler_files:
                try:
                    # Parse duration from filename: filler_XX_NNNms.npy
                    match = re.search(r"_(\d+)ms\.npy$", filler_path.name)
                    if match:
                        duration_ms = int(match.group(1))
                    else:
                        # Estimate duration if not in filename
                        audio_data = np.load(filler_path)
                        duration_ms = int(len(audio_data) / self.tts.sample_rate * 1000)
                    
                    audio_data = np.load(filler_path)
                    self._fillers.append((audio_data, duration_ms))
                    loaded_count += 1
                    
                except Exception as e:
                    logger.warning(f"Failed to load filler {filler_path.name}: {e}")
            
            if loaded_count > 0:
                self._fillers_loaded = True
                logger.info(f"Loaded {loaded_count} filler phrases for latency masking")
            else:
                logger.warning("No filler files could be loaded, disabling filler system")
                self._fillers_loaded = False
                
        except Exception as e:
            logger.warning(f"Error loading fillers: {e}, disabling filler system")
            self._fillers_loaded = False

    def stop(self) -> None:
        """Stop the VTuber application."""
        logger.info("Stopping AI VTuber...")
        self.running = False

        # Stop all components
        if self._microphone:
            self._microphone.stop()
        if self._player:
            self._player.stop()
        if self._stt:
            self._stt.unload()
        if self._tts:
            self._tts.unload()
        if self._avatar:
            self._avatar.dispose()

        logger.info("AI VTuber stopped")

    def process_cycle(self) -> None:
        """Run one processing cycle - called from main loop.
        
        This checks for voice activity and triggers the pipeline.
        The actual speech processing happens in a background thread.
        """
        if not self.running:
            return

        state = self.state_machine.state

        if state == State.IDLE:
            # Check for voice activity
            audio_chunk = self.microphone.read_chunk()
            if audio_chunk is not None:
                is_speech = self.vad.is_speech(audio_chunk)
                if is_speech:
                    logger.debug("Voice activity detected")
                    # Start pipeline thread - it handles all states internally
                    self._start_listening()

        elif state == State.ERROR:
            # Stay in error state, UI should show error
            pass

        # LISTENING, TRANSCRIBING, THINKING, SPEAKING are handled
        # by the background pipeline thread - don't interfere

    def _start_listening(self) -> None:
        """Start the listening pipeline in a background thread."""
        # Transition to LISTENING immediately to prevent re-entry
        self.state_machine.force_state(State.LISTENING)
        self._pipeline_thread = threading.Thread(target=self._listen_and_process, daemon=True)
        self._pipeline_thread.start()

    def _listen_and_process(self) -> None:
        """Full listen -> transcribe -> think -> speak pipeline."""
        try:
            # Reset VAD state for fresh detection
            self.vad.reset()

            # Clear stale audio chunks from queue to prevent memory buildup during idle
            self.microphone.clear_chunk_queue()

            # Mute microphone during future TTS playback to prevent feedback
            # (will be unmuted after speaking is done)

            # Collect speech audio (blocks until silence detected)
            audio_data = self.microphone.collect_speech(
                self.vad,
                silence_duration=self.config["stt"]["silence_duration"],
                min_duration=self.config["stt"]["min_speech_duration"]
            )

            if audio_data is None or len(audio_data) == 0:
                self.state_machine.force_state(State.IDLE)
                return

            # Transcribe
            self.state_machine.force_state(State.TRANSCRIBING)
            text = self.stt.transcribe(audio_data)

            if not text or text.strip() == "":
                logger.debug("Empty transcription, returning to idle")
                self.state_machine.force_state(State.IDLE)
                return

            with self._lock:
                self.current_transcription = text
            logger.info(f"User said: {text}")

            # Add to conversation
            self.conversation.add_message("user", text)

            # Generate response with dynamic timeout
            self.state_machine.force_state(State.THINKING)
            
            # Check if streaming is enabled in config
            stream_enabled = self.config.get("llm", {}).get("stream_enabled", False)
            
            if stream_enabled:
                # Use streaming pipeline for lower latency
                # Note: _generate_response_streaming() handles audio playback internally,
                # including avatar lip sync and mic mute/unmute, so we skip _speak() below
                response_text, emotion = self._generate_response_streaming(timeout=self.llm_timeout)
            else:
                # Use legacy blocking pipeline
                response_text, emotion = self._generate_response(timeout=self.llm_timeout)

            if not response_text:
                # Fallback response when LLM fails - still add to conversation history
                fallback_text = "I'm having trouble thinking clearly right now, but I'd love to hear more about what you were saying! Can you tell me more?"
                self.conversation.add_message("assistant", fallback_text, "neutral")
                with self._lock:
                    self.current_response = fallback_text
                    self.current_emotion = "neutral"
                logger.debug(f"Using fallback response after LLM failure")
                response_text = fallback_text
                emotion = "neutral"

            with self._lock:
                self.current_response = response_text
                self.current_emotion = emotion

            logger.debug(f"Response emotion: {emotion}")

            # Update avatar expression (already done in streaming path, but needed for non-streaming)
            if self._avatar and not stream_enabled:
                self.avatar.set_expression(emotion)

            # Speak (skip for streaming path since audio already played)
            if not stream_enabled:
                self.state_machine.force_state(State.SPEAKING)
                if self._avatar:
                    self.avatar.set_talking(True)
                    logger.debug("Avatar speaking started")

                # Mute mic during playback to prevent feedback
                if self.config["audio"].get("mute_during_playback", True):
                    self.microphone.mute()

                self._speak(response_text)

                # Done speaking
                if self._avatar:
                    self.avatar.set_talking(False)
                    self.avatar.set_expression("neutral")
                    logger.debug("Avatar speaking finished, expression reset to neutral")

                # Unmute microphone for next listening cycle
                self.microphone.unmute()

            # For streaming path, mic was already unmuted in on_playback_end()

            self.state_machine.force_state(State.IDLE)

        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            self.state_machine.set_error(str(e))
            # Reset to idle after a delay
            threading.Timer(3.0, self._recover_from_error).start()

    def _recover_from_error(self) -> None:
        """Attempt to recover from error state."""
        if self.state_machine.state == State.ERROR:
            self.state_machine.force_state(State.IDLE)
            logger.info("Recovered from error state")

    def _generate_response(self, timeout: Optional[int] = None) -> tuple[str, str]:
        """Generate LLM response and extract emotion/topic using analyzer.
        
        Args:
            timeout: Optional timeout in seconds for this request (overrides config).
        
        Returns (response_text, emotion).
        The topic is extracted but not currently used - stored for future features.
        """
        try:
            # FIX: Refresh soul_prompt from memory manager before each turn
            # so any new facts/memories are reflected in the next request
            self.conversation.set_soul_prompt(self.memory_manager.get_full_context())
            
            messages = self.conversation.get_messages_for_llm()
            raw_response = self.llm.chat(messages, timeout=timeout)

            if not raw_response:
                # FIX: Log warning when LLM returns empty response before fallback
                logger.warning("LM Studio returned empty response (request succeeded but content was empty/None)")
                # Fallback with engaging content instead of generic "not sure"
                fallback_responses = [
                    "That's an interesting point! I'd love to explore this topic more with you. What aspects interest you the most?",
                    "Hmm, this gives me a lot to think about! Let me share my perspective on this. What do you think about it?",
                    "Great question! There are so many angles we could discuss here. Where would you like to start?",
                    "I appreciate you bringing this up! It reminds me of how complex and fascinating conversations can be. Tell me more about your thoughts!",
                    "You know, every conversation teaches me something new! This topic seems really intriguing. What made you curious about it?"
                ]
                import random
                return (random.choice(fallback_responses), "neutral")

            # Use the new emotion/topic analyzer
            analysis = analyze_response(raw_response)
            
            # Extract emotion and cleaned text
            emotion = analysis.emotion
            response_text = analysis.cleaned_text
            
            # Topic is available as analysis.topic for future use
            # For now, we just log it for debugging
            logger.debug(f"Detected topic: {analysis.topic}")

            # Add to conversation
            self.conversation.add_message("assistant", response_text, emotion)

            return (response_text, emotion)

        except Exception as e:
            logger.error(f"LLM error: {e}")
            # More engaging fallback responses instead of apologetic ones
            fallbacks = [
                "Let's keep chatting! I'm always excited to hear what you have to say. What else is on your mind?",
                "You know what? Every conversation is a new adventure! Where should we go next in our discussion?",
                "I love our chats! There's always something interesting to talk about. What would you like to explore together?"
            ]
            import random
            return (random.choice(fallbacks), "happy")

    def _generate_response_streaming(self, timeout: Optional[int] = None) -> tuple[str, str]:
        """Generate LLM response with streaming for lower latency.
        
        Streams LLM tokens and starts TTS synthesis as soon as complete sentences
        are available, reducing time-to-first-audio. Audio is played sentence-by-sentence
        within this method, so caller should NOT call _speak() afterwards.
        
        Args:
            timeout: Optional timeout in seconds for this request.
            
        Returns:
            (full_response_text, emotion) tuple after full response is assembled.
        """
        try:
            # Refresh soul prompt before generating
            self.conversation.set_soul_prompt(self.memory_manager.get_full_context())
            messages = self.conversation.get_messages_for_llm()
            
            # Sentence boundary pattern - matches sentence-ending punctuation
            sentence_end_pattern = re.compile(r'([.!?]+)(?:\s+|$)')
            
            # Buffers for accumulating text
            token_buffer = ""  # Raw tokens from LLM
            sentence_buffer = ""  # Complete sentences ready for TTS
            raw_response = ""  # Full raw response for emotion analysis
            
            # Queue for sending sentences to TTS producer
            tts_input_queue: queue.Queue = queue.Queue(maxsize=3)
            
            # Thread control
            producer_stop_event = threading.Event()
            producer_thread: Optional[threading.Thread] = None
            
            # Track first chunk playback start for lip sync
            first_chunk_played = False
            on_start_called = False
            
            # Callbacks for avatar lip sync and mic control
            def on_playback_start():
                """Called when first audio chunk starts playing."""
                nonlocal on_start_called
                if not on_start_called:
                    if self._avatar:
                        logger.debug("TTS playback starting, initiating lip sync")
                        self.avatar.start_lip_sync(None, self.tts.sample_rate)  # Audio passed per-chunk
                    # Mute mic during playback to prevent feedback
                    if self.config["audio"].get("mute_during_playback", True):
                        self.microphone.mute()
                    on_start_called = True
            
            def on_playback_end():
                """Called when last audio chunk finishes playing."""
                if self._avatar:
                    logger.debug("TTS playback finished")
                    self.avatar.set_talking(False)
                    self.avatar.set_expression("neutral")
                # Unmute microphone for next listening cycle
                self.microphone.unmute()
            
            def tts_producer():
                """Producer thread: synthesizes sentences and queues audio chunks."""
                nonlocal first_chunk_played, on_start_called
                
                try:
                    while not producer_stop_event.is_set():
                        try:
                            # Get next sentence from queue (blocking with timeout)
                            sentence = tts_input_queue.get(timeout=0.1)
                            
                            if sentence is None:  # Sentinel value signals end
                                break
                            
                            # Normalize text before TTS
                            from ai_vtuber.tts import normalize_text
                            cleaned = normalize_text(sentence)
                            
                            if not cleaned:
                                continue
                            
                            # Generate audio for this sentence
                            audio = self.tts.generate(cleaned)
                            if audio is not None:
                                # Put audio in playback queue with timeout to avoid blocking forever
                                try:
                                    self._tts_audio_queue.put((audio, cleaned), timeout=5.0)
                                except queue.Full:
                                    logger.warning("TTS audio queue full, dropping chunk")
                                
                        except queue.Empty:
                            continue
                        except Exception as e:
                            logger.error(f"TTS producer error: {e}")
                            break
                finally:
                    logger.debug("TTS producer thread exiting")
            
            def playback_consumer(interrupt_check, on_start, on_end):
                """Consumer: plays audio chunks from TTS producer.
                
                Handles filler injection on stalls and first-chunk special case.
                """
                nonlocal first_chunk_played, on_start_called
                
                stall_threshold = self.config.get("fillers", {}).get("stall_threshold_ms", 400) / 1000.0
                last_chunk_end_time = time.time()
                
                try:
                    while True:
                        # Check for interruption
                        if interrupt_check():
                            logger.info("Playback interrupted")
                            producer_stop_event.set()
                            break
                        
                        # Check for stall (queue empty but producer still running)
                        elapsed_since_last = time.time() - last_chunk_end_time
                        if (self._tts_audio_queue.empty() and 
                            producer_thread and producer_thread.is_alive() and
                            elapsed_since_last > stall_threshold and
                            self._fillers_loaded):
                            # Play a filler while waiting
                            logger.debug(f"Stall detected ({elapsed_since_last:.2f}s), playing filler")
                            self._play_filler(interrupt_check)
                            last_chunk_end_time = time.time()
                        
                        # Get next audio chunk (blocking with timeout)
                        try:
                            audio_data, chunk_text = self._tts_audio_queue.get(timeout=0.1)
                        except queue.Empty:
                            # Check if producer is done
                            if producer_thread and not producer_thread.is_alive():
                                break
                            continue
                        
                        # First chunk special handling: split if too long
                        if not first_chunk_played and len(chunk_text) > 60:
                            # Split at first comma/clause boundary
                            comma_match = re.search(r'[,;:]\s*', chunk_text)
                            if comma_match:
                                split_point = comma_match.end()
                                first_part = chunk_text[:split_point].strip()
                                second_part = chunk_text[split_point:].strip()
                                
                                if first_part and second_part:
                                    # Re-generate first part only
                                    from ai_vtuber.tts import normalize_text
                                    first_cleaned = normalize_text(first_part)
                                    if first_cleaned:
                                        first_audio = self.tts.generate(first_cleaned)
                                        if first_audio is not None:
                                            # Play first part now
                                            self._play_audio_chunk(
                                                first_audio, 
                                                interrupt_check,
                                                on_start if not on_start_called else None,
                                                None  # No on_end for partial chunk
                                            )
                                            if not on_start_called and on_start:
                                                on_start()
                                                on_start_called = True
                                            first_chunk_played = True
                                            last_chunk_end_time = time.time()
                                            
                                            # Put remaining part back for normal playback
                                            self._tts_audio_queue.put((audio_data, chunk_text))
                                            continue
                        
                        # Play the chunk normally
                        def chunk_on_start():
                            nonlocal on_start_called
                            if not on_start_called and on_start:
                                on_start()
                                on_start_called = True
                        
                        def chunk_on_end():
                            nonlocal last_chunk_end_time
                            last_chunk_end_time = time.time()
                        
                        self._play_audio_chunk(
                            audio_data,
                            interrupt_check,
                            chunk_on_start,
                            chunk_on_end
                        )
                        
                        if not on_start_called and on_start:
                            on_start()
                            on_start_called = True
                        first_chunk_played = True
                        
                finally:
                    # Signal end to producer if not already done
                    producer_stop_event.set()
                    
                    # Call on_end if we played anything
                    if on_start_called and on_end:
                        on_end()
                    
                    logger.debug("Playback consumer exiting")
            
            # Start producer thread
            self._tts_audio_queue = queue.Queue(maxsize=3)
            producer_thread = threading.Thread(target=tts_producer, daemon=True)
            producer_thread.start()
            
            # Consumer thread runs in parallel with LLM streaming
            # This allows audio to play sentence-by-sentence as it streams
            interrupt_check = self._check_interruption
            consumer_thread = threading.Thread(
                target=playback_consumer, 
                args=(interrupt_check, on_playback_start, on_playback_end),
                daemon=True
            )
            consumer_thread.start()
            
            # Stream LLM tokens and feed sentences to producer
            for delta in self.llm.chat_stream(messages, timeout=timeout):
                token_buffer += delta
                raw_response += delta
                
                # Check for sentence boundaries
                match = sentence_end_pattern.search(token_buffer)
                if match:
                    # Extract complete sentence(s)
                    end_pos = match.end()
                    sentence = token_buffer[:end_pos].strip()
                    token_buffer = token_buffer[end_pos:].lstrip()
                    
                    if sentence:
                        # Strip emotion tag from first sentence if present
                        # (same logic as non-streaming path via analyze_response/cleaned_text)
                        if raw_response.startswith('['):
                            first_line = raw_response.split('\n')[0]
                            if first_line.startswith('[') and first_line.endswith(']'):
                                # This is the first sentence and has an emotion tag prefix
                                # The tag will be stripped by normalize_text before TTS, same as non-streaming
                                pass  # normalize_text handles tag stripping
                        
                        try:
                            tts_input_queue.put(sentence, block=False)
                        except queue.Full:
                            logger.warning("TTS input queue full, dropping sentence")
            
            # Handle any remaining text in buffer
            if token_buffer.strip():
                try:
                    tts_input_queue.put(token_buffer.strip(), block=False)
                except queue.Full:
                    logger.warning("TTS input queue full, dropping final text")
            
            # Signal producer to finish
            tts_input_queue.put(None)
            
            # Wait for producer and consumer to complete
            if producer_thread:
                producer_thread.join(timeout=5.0)
            if consumer_thread:
                consumer_thread.join(timeout=10.0)  # Allow extra time for final audio to play
            
            # Now run emotion analysis on full response
            analysis = analyze_response(raw_response)
            emotion = analysis.emotion
            response_text = analysis.cleaned_text
            
            # Add to conversation history
            self.conversation.add_message("assistant", response_text, emotion)
            
            logger.debug(f"Detected topic: {analysis.topic}")
            
            return (response_text, emotion)
            
        except Exception as e:
            logger.error(f"Streaming LLM error: {e}")
            # Fallback responses
            fallbacks = [
                "Let's keep chatting! I'm always excited to hear what you have to say. What else is on your mind?",
                "You know what? Every conversation is a new adventure! Where should we go next in our discussion?",
                "I love our chats! There's always something interesting to talk about. What would you like to explore together?"
            ]
            import random
            return (random.choice(fallbacks), "happy")

    def _speak(self, text: str) -> None:
        """Generate and play TTS audio with lip sync."""
        try:
            # Normalize text before TTS (remove markdown, emojis, excessive punctuation, etc.)
            from ai_vtuber.tts import normalize_text
            cleaned_text = normalize_text(text)
            
            if not cleaned_text:
                logger.warning("Text normalization resulted in empty string")
                return
            
            # Generate audio from cleaned text
            audio_data = self.tts.generate(cleaned_text)
            if audio_data is None:
                logger.warning("TTS returned no audio")
                return

            # Play audio (with interruption support and lip sync callback)
            def on_playback_start():
                """Called when playback starts - enable real lip sync."""
                if self._avatar:
                    logger.debug("TTS playback starting, initiating lip sync")
                    self.avatar.start_lip_sync(audio_data, self.tts.sample_rate)
            
            def on_playback_end():
                """Called when playback ends - disable lip sync."""
                if self._avatar:
                    logger.debug("TTS playback finished")
                    self.avatar.set_talking(False)
            
            self.player.play(
                audio_data, 
                interrupt_check=self._check_interruption,
                on_start=on_playback_start,
                on_end=on_playback_end
            )

        except Exception as e:
            logger.error(f"TTS playback error: {e}")
        finally:
            # Always unmute mic after speaking (whether interrupted or not)
            self.microphone.unmute()

    def _play_audio_chunk(self, audio_data: np.ndarray, interrupt_check, on_start=None, on_end=None) -> None:
        """Play a single audio chunk via the audio player.
        
        Thin wrapper around self.player.play() matching the signature used by _speak().
        
        Args:
            audio_data: Numpy array of audio samples (float32).
            interrupt_check: Callable returning True if playback should stop.
            on_start: Optional callback invoked when playback starts.
            on_end: Optional callback invoked when playback ends.
        """
        try:
            self.player.play(
                audio_data,
                interrupt_check=interrupt_check,
                on_start=on_start,
                on_end=on_end
            )
        except Exception as e:
            logger.error(f"Audio chunk playback error: {e}")
    
    def _play_filler(self, interrupt_check) -> None:
        """Play a random filler phrase from the pre-loaded list.
        
        No-ops if fillers are not loaded or list is empty.
        
        Args:
            interrupt_check: Callable returning True if playback should stop.
        """
        if not self._fillers_loaded or not self._fillers:
            return
        
        import random
        filler_audio, duration_ms = random.choice(self._fillers)
        logger.debug(f"Playing filler ({duration_ms}ms)")
        
        # Play filler with interruption support, no special callbacks needed
        self.player.play(
            filler_audio,
            interrupt_check=interrupt_check,
            on_start=None,
            on_end=None
        )

    def _check_interruption(self) -> bool:
        if not self.running:
            return True

        # Check for voice activity while speaking
        audio_chunk = self.microphone.read_chunk()
        if audio_chunk is not None:
            # Only interrupt if there's sustained speech (not just noise)
            is_speech = self.vad.is_speech(audio_chunk)
            if is_speech:
                # Check if it's the TTS output being picked up
                if self.config["audio"].get("mute_during_playback", True):
                    # If we're muting during playback, any speech detected is user
                    logger.info("Interruption detected!")
                    return True
        return False

    def interrupt(self) -> None:
        """Manually interrupt current speech."""
        if self.state_machine.state == State.SPEAKING:
            self.player.stop()
            if self._avatar:
                self.avatar.set_talking(False)
            self.state_machine.force_state(State.IDLE)
            logger.info("Speech interrupted")

    def process_chat_message(self, text: str) -> None:
        """Process a text message from the chat UI.
        
        This is similar to the voice pipeline but triggered by text input.
        Runs in a background thread to avoid blocking the UI.
        """
        if not text or not text.strip():
            return
        
        # Run in background thread
        thread = threading.Thread(target=self._process_chat_message_thread, args=(text,), daemon=True)
        thread.start()

    def _process_chat_message_thread(self, text: str) -> None:
        """Background thread for processing chat messages."""
        try:
            logger.info(f"Processing chat message: {text}")
            
            # Update state
            self.state_machine.force_state(State.THINKING)
            
            # Update transcription display
            with self._lock:
                self.current_transcription = text
            
            # Add to conversation history
            self.conversation.add_message("user", text)
            
            # Generate response with dynamic timeout
            response_text, emotion = self._generate_response(timeout=self.llm_timeout)
            
            if not response_text:
                self.state_machine.force_state(State.IDLE)
                return
            
            # Update UI state
            with self._lock:
                self.current_response = response_text
                self.current_emotion = emotion
            
            logger.info(f"AI response: [{emotion}] {response_text}")
            
            # Update avatar expression
            if self._avatar:
                self.avatar.set_expression(emotion)
                self.avatar.set_talking(True)
            
            # Generate and play TTS
            self.state_machine.force_state(State.SPEAKING)
            self._speak(response_text)
            
            # Done speaking
            if self._avatar:
                self.avatar.set_talking(False)
                self.avatar.set_expression("neutral")
            
            self.state_machine.force_state(State.IDLE)
            
        except Exception as e:
            logger.error(f"Chat message processing error: {e}", exc_info=True)
            self.state_machine.set_error(str(e))
            # Reset to idle after a delay
            threading.Timer(3.0, self._recover_from_error).start()

    def get_status(self) -> dict:
        """Get current status for UI display."""
        with self._lock:
            return {
                "state": self.state_machine.state.name,
                "transcription": self.current_transcription,
                "response": self.current_response,
                "emotion": self.current_emotion,
                "error": self.state_machine.error_message,
            }
