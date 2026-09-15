"""AI VTuber - Ollama LLM Client (Fallback)"""

import logging
from typing import Optional
from openai import OpenAI

logger = logging.getLogger(__name__)


class OllamaClient:
    """Client for Ollama's OpenAI-compatible API."""

    def __init__(self, config: dict) -> None:
        self.base_url: str = config.get("base_url", "http://localhost:11434/v1")
        self.model: str = config.get("model", "gemma2:2b")
        self.temperature: float = config.get("temperature", 0.8)
        self.max_tokens: int = config.get("max_tokens", 2000)
        # No hard timeout - wait for LLM reply indefinitely
        self.timeout: Optional[int] = config.get("timeout", None)

        self._client: Optional[OpenAI] = None
        self._connect()

    def _connect(self) -> None:
        """Establish connection to Ollama."""
        try:
            self._client = OpenAI(
                base_url=self.base_url,
                api_key="ollama"  # Ollama doesn't require a real API key
            )
            # Test connection by listing models
            self._client.models.list()
            logger.info(f"Connected to Ollama at {self.base_url}")
        except Exception as e:
            logger.warning(f"Cannot connect to Ollama: {e}")
            logger.warning("Ollama fallback unavailable.")
            self._client = None

    def chat(self, messages: list[dict[str, str]], timeout: Optional[int] = None) -> str:
        """Send messages to LLM and get response.
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            timeout: Optional timeout in seconds for this request (overrides config).
            
        Returns:
            The assistant's response text.
        """
        if self._client is None:
            # Try to reconnect
            self._connect()
            if self._client is None:
                raise ConnectionError("Cannot connect to Ollama")

        # Use provided timeout or fall back to configured timeout
        request_timeout = timeout if timeout is not None else self.timeout

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=False,
                timeout=request_timeout
            )
            content = response.choices[0].message.content
            return content if content else ""
        except Exception as e:
            logger.error(f"Ollama request failed: {e}")
            raise

    def chat_stream(self, messages: list[dict[str, str]], timeout: Optional[int] = None):
        """Stream LLM response token by token.
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            timeout: Optional timeout in seconds for this request (overrides config).
            
        Yields:
            Text deltas as they arrive from the LLM.
        """
        if self._client is None:
            # Try to reconnect
            self._connect()
            if self._client is None:
                raise ConnectionError("Cannot connect to Ollama")

        # Use provided timeout or fall back to configured timeout
        request_timeout = timeout if timeout is not None else self.timeout

        try:
            stream = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=True,
                timeout=request_timeout
            )
            
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta is not None:
                    yield delta
                    
        except Exception as e:
            logger.error(f"Ollama streaming request failed: {e}")
            raise

    def is_available(self) -> bool:
        """Check if Ollama is available."""
        return self._client is not None
