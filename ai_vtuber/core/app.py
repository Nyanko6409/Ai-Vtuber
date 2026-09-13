"""AI VTuber - Main Application Controller"""

import logging
import threading
from pathlib import Path
from typing import Optional

from .state import State, StateMachine
from .conversation import ConversationHistory
from ..llm.lmstudio import LMStudioClient
from ..stt.whisper import WhisperSTT
from ..tts.kitten import KittenTTS
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

        # Initialize conversation history with system prompt and soul
        self.conversation = ConversationHistory(
            max_messages=config["llm"]["max_history"],
            system_prompt=config["llm"]["system_prompt"],
            soul_prompt=self.memory_manager.get_full_context()
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

            # Generate response
            self.state_machine.force_state(State.THINKING)
            response_text, emotion = self._generate_response()

            if not response_text:
                self.state_machine.force_state(State.IDLE)
                return

            with self._lock:
                self.current_response = response_text
                self.current_emotion = emotion

            logger.debug(f"Response emotion: {emotion}")

            # Update avatar expression
            if self._avatar:
                self.avatar.set_expression(emotion)

            # Speak
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

    def _generate_response(self) -> tuple[str, str]:
        """Generate LLM response and extract emotion/topic using analyzer.
        
        Returns (response_text, emotion).
        The topic is extracted but not currently used - stored for future features.
        """
        try:
            messages = self.conversation.get_messages_for_llm()
            raw_response = self.llm.chat(messages)

            if not raw_response:
                return ("I'm not sure what to say.", "neutral")

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
            return ("Sorry, I had trouble thinking of a response.", "sad")

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

    def _check_interruption(self) -> bool:
        """Check if user is speaking (for interruption).
        
        Returns True if we should stop speaking.
        """
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
            
            # Generate response
            response_text, emotion = self._generate_response()
            
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
