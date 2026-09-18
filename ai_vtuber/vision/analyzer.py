"""AI VTuber - Visual Scene Analysis using Vision-Capable LLM"""

import io
import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class VisionAnalysisResult:
    """Result of visual scene analysis."""
    description: str  # Concise description of what's happening
    game_state: Dict[str, Any]  # Structured game state info
    significant_changes: List[str]  # Notable changes from previous state
    confidence: float  # Overall confidence in analysis
    timestamp: float


class VisionAnalyzer:
    """
    Visual scene understanding using a vision-capable LLM.
    
    Focuses on:
    - What is happening on screen (game state, actions, events)
    - UI elements and their meaning
    - Significant changes or events
    - NOT identifying every anime character
    
    Uses concise prompts to minimize token usage and latency.
    """
    
    def __init__(
        self,
        llm_client,
        model: str,
        max_tokens: int = 300,
        timeout: int = 30
    ):
        """
        Initialize the vision analyzer.
        
        Args:
            llm_client: LLM client instance (must support vision/images)
            model: Vision model name (e.g., 'google/gemma-4-e2b')
            max_tokens: Maximum tokens in response
            timeout: Request timeout in seconds
        """
        self.client = llm_client
        self.model = model
        self.max_tokens = max_tokens
        self.timeout = timeout
        
        self._lock = threading.Lock()
        self._is_analyzing = False
        self._last_analysis_time: float = 0.0
        self._analysis_count: int = 0
        self._error_count: int = 0
        
        # Cache for recent analyses to avoid repetition
        self._recent_descriptions: List[str] = []
        self._max_recent = 5
    
    @property
    def is_available(self) -> bool:
        """Check if vision analyzer is available."""
        return self.client is not None and self.client.is_available()
    
    @property
    def is_busy(self) -> bool:
        """Check if currently analyzing."""
        return self._is_analyzing
    
    @property
    def stats(self) -> dict:
        """Get analysis statistics."""
        return {
            "is_busy": self._is_analyzing,
            "analysis_count": self._analysis_count,
            "error_count": self._error_count,
            "last_analysis": self._last_analysis_time,
            "recent_descriptions": len(self._recent_descriptions)
        }
    
    def analyze(
        self,
        image_bytes: bytes,
        cached_state: Optional[Dict] = None,
        context_hint: Optional[str] = None
    ) -> Optional[VisionAnalysisResult]:
        """
        Analyze a screenshot using vision-capable LLM.
        
        Args:
            image_bytes: JPEG-encoded screenshot
            cached_state: Previously known state for comparison
            context_hint: Optional hint about what to look for
            
        Returns:
            VisionAnalysisResult or None on failure
        """
        if not self.is_available:
            logger.warning("Vision analyzer not available")
            return None
        
        with self._lock:
            if self._is_analyzing:
                logger.debug("Vision analyzer busy, skipping")
                return None
            self._is_analyzing = True
        
        try:
            # Build prompt
            prompt = self._build_prompt(cached_state, context_hint)
            
            # Load image
            img = Image.open(io.BytesIO(image_bytes))
            
            # Send to LLM with image
            response = self._call_vision(img, prompt)
            
            if not response:
                self._error_count += 1
                return None
            
            # Parse response
            result = self._parse_response(response, cached_state)
            
            self._analysis_count += 1
            self._last_analysis_time = time.time()
            
            # Cache description
            self._recent_descriptions.append(result.description)
            if len(self._recent_descriptions) > self._max_recent:
                self._recent_descriptions.pop(0)
            
            return result
            
        except Exception as e:
            self._error_count += 1
            logger.error(f"Vision analysis failed: {e}")
            return None
            
        finally:
            with self._lock:
                self._is_analyzing = False
    
    def _build_prompt(
        self,
        cached_state: Optional[Dict],
        context_hint: Optional[str]
    ) -> str:
        """Build concise prompt for Gemma."""
        
        base_prompt = """Analyze this screen and describe only meaningful changes or important events. Focus on:
- Game state (combat, menu, dialogue, loading, exploration)
- Visible actions or events happening
- UI elements showing important information (health, objectives, notifications)
- Location or scene changes
- Text that indicates story progression or player choices

Do NOT:
- Guess character identities unless clearly labeled
- Describe static background details
- Repeat information already known

Be concise and specific. Format: 2-3 sentences maximum."""

        # Add context hints
        parts = [base_prompt]
        
        if context_hint:
            parts.append(f"\n\nContext: {context_hint}")
        
        if cached_state:
            parts.append("\n\nPreviously known:")
            if cached_state.get('game_name'):
                parts.append(f" Game: {cached_state['game_name']}")
            if cached_state.get('location'):
                parts.append(f" Location: {cached_state['location']}")
            if cached_state.get('in_combat'):
                parts.append(" Currently in combat")
            if cached_state.get('in_menu'):
                parts.append(" Currently in menu")
            
            parts.append("\n\nDescribe what has CHANGED or what is HAPPENING now.")
        
        return "\n".join(parts)
    
    def _call_vision(
        self,
        image: Image.Image,
        prompt: str
    ) -> Optional[str]:
        """
        Call LLM vision API with image.
        
        This method uses the OpenAI-compatible API which supports
        multimodal content (images + text).
        
        Args:
            image: PIL Image object
            prompt: Text prompt
            
        Returns:
            Response text or None on failure
        """
        try:
            import base64
            
            # Convert image to base64
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=85)
            image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            # Build messages for OpenAI-compatible API
            # This format works with LM Studio and other OpenAI-compatible APIs
            # that support vision/multimodal input
            messages = [{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    },
                    {"type": "text", "text": prompt}
                ]
            }]
            
            # Use chat.completions.create with multimodal content
            # The OpenAI Python client handles encoding images properly
            response = self.client._client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                stream=False,
                timeout=self.timeout
            )
            
            content = response.choices[0].message.content
            return content if content else ""
            
        except Exception as e:
            logger.error(f"Vision call failed: {e}")
            return None
    
    def _parse_response(
        self,
        response_text: str,
        cached_state: Optional[Dict]
    ) -> VisionAnalysisResult:
        """Parse LLM response into structured result."""
        
        # Extract game state indicators from text
        game_state = {}
        significant_changes = []
        
        text_lower = response_text.lower()
        
        # Detect state keywords
        if any(w in text_lower for w in ['combat', 'fighting', 'battle', 'attacking']):
            game_state['in_combat'] = True
            significant_changes.append("Combat detected")
        elif cached_state and cached_state.get('in_combat'):
            game_state['in_combat'] = False
            significant_changes.append("Combat ended")
        
        if any(w in text_lower for w in ['menu', 'inventory', 'pause', 'settings']):
            game_state['in_menu'] = True
        else:
            game_state['in_menu'] = False
        
        if any(w in text_lower for w in ['dialogue', 'conversation', 'talking', 'textbox']):
            game_state['in_dialogue'] = True
        else:
            game_state['in_dialogue'] = False
        
        if any(w in text_lower for w in ['loading', 'load screen']):
            game_state['loading'] = True
        else:
            game_state['loading'] = False
        
        if any(w in text_lower for w in ['low health', 'dying', 'critical', 'hp low']):
            game_state['player_health_low'] = True
            significant_changes.append("Low health warning")
        
        # Extract game name - look for patterns like "playing X", "game is X"
        game_name = None
        import re
        
        # Try multiple patterns to extract game name more accurately
        # Pattern 1: "You are playing [Game]" or "Playing [Game]"
        play_match = re.search(r'(?:you\'?re\s+)?playing\s+([A-Z][A-Za-z0-9\s\'\-:]+?)(?:\s+in\s+|\s+at\s+|\.|,|$)', response_text)
        if not play_match:
            # Pattern 2: "The game is [Game]" or "game is [Game]"
            play_match = re.search(r'(?:the\s+)?game\s+is\s+([A-Z][A-Za-z0-9\s\'\-:]+?)(?:\.|,|$)', response_text)
        
        if play_match:
            game_name = play_match.group(1).strip()
            # Clean up common artifacts
            if game_name.lower().startswith('the '):
                game_name = game_name[4:]
            # Remove trailing location markers
            for marker in [' in ', ' at ']:
                if marker in game_name:
                    game_name = game_name.split(marker)[0].strip()
            if game_name:
                game_state['game_name'] = game_name
        
        # Extract location - look for patterns like "in [Location]", "at [Location]", "Location: [Location]"
        location = None
        # Pattern 1: "Location: X" or "location: X"
        loc_match = re.search(r'location:\s*([A-Z][A-Za-z0-9\s\'\-:]+?)(?:\.|,|$)', response_text, re.IGNORECASE)
        if not loc_match:
            # Pattern 2: "in [Location]" (but not "in combat", "in menu", etc.)
            loc_match = re.search(r'\s+in\s+([A-Z][A-Za-z0-9\s\'\-:]+?)(?:\.|,|$)', response_text)
            if loc_match:
                potential_loc = loc_match.group(1).strip().lower()
                # Filter out non-location matches
                if potential_loc in ['combat', 'menu', 'dialogue', 'a', 'an', 'the']:
                    loc_match = None
        if not loc_match:
            # Pattern 3: "at [Location]"
            loc_match = re.search(r'\s+at\s+([A-Z][A-Za-z0-9\s\'\-:]+?)(?:\.|,|$)', response_text)
        
        if loc_match:
            location = loc_match.group(1).strip()
            # Avoid false positives
            if location.lower() not in ['the', 'a', 'an', 'this', 'that', 'combat', 'menu', 'dialogue']:
                game_state['location'] = location
        
        # Estimate confidence based on response clarity
        confidence = 0.7  # Base confidence
        if len(response_text) < 20:
            confidence = 0.5  # Very short response
        elif 'unclear' in text_lower or 'cannot' in text_lower:
            confidence = 0.4
        elif len(response_text) > 100:
            confidence = 0.85  # Detailed response
        
        return VisionAnalysisResult(
            description=response_text.strip(),
            game_state=game_state,
            significant_changes=significant_changes,
            confidence=confidence,
            timestamp=time.time()
        )
    
    def extract_entities_from_analysis(
        self,
        result: VisionAnalysisResult
    ) -> Dict[str, List[str]]:
        """
        Extract entity mentions from analysis result.
        
        This is a simple heuristic extractor. For more accurate extraction,
        use a dedicated NER model or ask the LLM explicitly.
        
        Returns:
            Dict mapping entity types to lists of names
        """
        entities = {
            'characters': [],
            'enemies': [],
            'locations': [],
            'ui_elements': []
        }
        
        # Simple keyword-based extraction
        # In production, you'd use proper NLP or ask LLM to structure output
        
        text = result.description
        
        # Look for location indicators
        if ' in ' in text:
            # Potential location mentions after "in"
            pass  # Would need more sophisticated parsing
        
        return entities
