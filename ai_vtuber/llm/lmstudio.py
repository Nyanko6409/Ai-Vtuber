"""AI VTuber - LM Studio LLM Client"""

import logging
from typing import Optional
from openai import OpenAI

logger = logging.getLogger(__name__)


class LMStudioClient:
    """Client for LM Studio's OpenAI-compatible API."""

    def __init__(self, config: dict) -> None:
        self.base_url: str = config["base_url"]
        self.model: str = config["model"]
        self.temperature: float = config["temperature"]
        self.max_tokens: int = config["max_tokens"]

        self._client: Optional[OpenAI] = None
        self._connect()

    def _connect(self) -> None:
        """Establish connection to LM Studio."""
        try:
            self._client = OpenAI(
                base_url=self.base_url,
                api_key="not-needed"  # LM Studio doesn't require API key
            )
            # Test connection
            self._client.models.list()
            logger.info(f"Connected to LM Studio at {self.base_url}")
        except Exception as e:
            logger.warning(f"Cannot connect to LM Studio: {e}")
            logger.warning("LLM will be unavailable. Start LM Studio server to enable chat.")
            self._client = None

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Send messages to LLM and get response.
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            
        Returns:
            The assistant's response text.
        """
        if self._client is None:
            # Try to reconnect
            self._connect()
            if self._client is None:
                raise ConnectionError("Cannot connect to LM Studio")

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=False
            )
            content = response.choices[0].message.content
            return content if content else ""
        except Exception as e:
            logger.error(f"LLM request failed: {e}")
            raise

    def is_available(self) -> bool:
        """Check if LM Studio is available."""
        return self._client is not None
