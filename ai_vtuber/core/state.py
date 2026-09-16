"""AI VTuber - State Machine Module"""

from enum import Enum, auto
from typing import Callable, Optional
import threading


class State(Enum):
    """Application states."""
    IDLE = auto()
    LISTENING = auto()
    TRANSCRIBING = auto()
    THINKING = auto()
    SPEAKING = auto()
    ERROR = auto()


class StateMachine:
    """Thread-safe state machine for the VTuber pipeline.
    
    FIX: Removed VALID_TRANSITIONS and transition() since all call sites
    use force_state(). The validation table was dead code providing no protection.
    """

    def __init__(self) -> None:
        self._state: State = State.IDLE
        self._lock = threading.Lock()
        self._callbacks: list[Callable[[State, State], None]] = []
        self._error_message: Optional[str] = None

    @property
    def state(self) -> State:
        """Get current state."""
        with self._lock:
            return self._state

    @property
    def error_message(self) -> Optional[str]:
        """Get current error message."""
        with self._lock:
            return self._error_message

    def force_state(self, new_state: State) -> None:
        """Force a state transition.
        
        All call sites use this method, so VALID_TRANSITIONS was removed.
        State changes are intentional and tracked via callbacks.
        """
        with self._lock:
            old_state = self._state
            self._state = new_state
            if new_state != State.ERROR:
                self._error_message = None

        for callback in self._callbacks:
            try:
                callback(old_state, new_state)
            except Exception as e:
                logger.debug(f"State transition callback raised: {e}")

    def set_error(self, message: str) -> None:
        """Set error state with message."""
        with self._lock:
            self._error_message = message
            old_state = self._state
            self._state = State.ERROR

        for callback in self._callbacks:
            try:
                callback(old_state, State.ERROR)
            except Exception as e:
                logger.debug(f"Error state transition callback raised: {e}")

    def on_transition(self, callback: Callable[[State, State], None]) -> None:
        """Register a state transition callback."""
        self._callbacks.append(callback)

    def is_active(self) -> bool:
        """Check if the system is actively processing (not idle or error)."""
        with self._lock:
            return self._state not in (State.IDLE, State.ERROR)

    def __repr__(self) -> str:
        return f"StateMachine(state={self._state.name})"
