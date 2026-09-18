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
        timeout: int = 60  # Increased timeout for vision analysis
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
        """Build concise prompt for Gemma - focuses on ANY screen content."""
        
        base_prompt = """Analyze this screen and describe what you see. Focus on:
- What application or window is active (browser, game, video player, code editor, document, social media, etc.)
- Visible content: websites, videos, images, documents, code, chat messages, etc.
- Important text: titles, headings, visible paragraphs, captions, subtitles
- Visual elements: colors, layouts, thumbnails, UI components
- General activity: browsing, watching, coding, reading, chatting, gaming, etc.

Be specific and descriptive. If you see text, quote some of it. If you see an image or video, describe its content.
Don't assume it's a game - describe whatever is actually visible.

Be concise but informative. Format: 2-4 sentences."""

        # Add context hints
        parts = [base_prompt]
        
        if context_hint:
            parts.append(f"\n\nContext hint: {context_hint}")
        
        if cached_state:
            parts.append("\n\nPreviously seen context:")
            if cached_state.get('game_name'):
                parts.append(f" Game/Application: {cached_state['game_name']}")
            if cached_state.get('location'):
                parts.append(f" Location/Area: {cached_state['location']}")
            
            parts.append("\n\nDescribe what you see NOW and any changes from before.")
        
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
        """Parse LLM response into structured result - generic for any screen content."""
        
        # Extract general state indicators from text
        game_state = {}
        significant_changes = []
        
        text_lower = response_text.lower()
        
        # Detect application types
        app_indicators = {
            'browser': ['browser', 'chrome', 'firefox', 'website', 'webpage', 'url'],
            'video': ['video', 'youtube', 'netflix', 'playing', 'watching'],
            'code': ['code', 'editor', 'vs code', 'programming', 'IDE'],
            'document': ['document', 'word', 'text', 'paragraph'],
            'game': ['game', 'gaming', 'playing'],
            'social': ['discord', 'twitter', 'reddit', 'social media', 'chat'],
            'image': ['image', 'photo', 'picture', 'thumbnail']
        }
        
        for app_type, keywords in app_indicators.items():
            if any(kw in text_lower for kw in keywords):
                game_state[f'is_{app_type}'] = True
        
        # Try to extract application/window name
        app_name = None
        import re
        
        # Look for patterns like "You are viewing [X]", "Showing [X]", "[X] is open"
        view_patterns = [
            r'(?:you\'?re\s+)?(?:viewing|seeing|looking\s+at)\s+([A-Z][A-Za-z0-9\s\'\-:]+?)(?:\.|,|$)',
            r'(?:the\s+)?(?:website|page|application|app|window)\s+(?:is|shows?)\s+([A-Z][A-Za-z0-9\s\'\-:]+?)(?:\.|,|$)',
            r'([A-Z][A-Za-z0-9\s\'\-:]+?)\s+(?:is\s+)?(?:open|displayed|visible)',
        ]
        
        for pattern in view_patterns:
            match = re.search(pattern, response_text)
            if match:
                app_name = match.group(1).strip()
                # Clean up common artifacts
                if app_name.lower().startswith('the '):
                    app_name = app_name[4:]
                break
        
        if app_name and len(app_name) > 2:
            game_state['app_name'] = app_name
        
        # Extract visible text snippets (look for quoted text)
        quoted_text = re.findall(r'"([^"]{10,100})"', response_text)
        if quoted_text:
            game_state['visible_text'] = quoted_text[0][:100]  # First snippet
        
        # Estimate confidence based on response clarity
        confidence = 0.7  # Base confidence
        if len(response_text) < 20:
            confidence = 0.5  # Very short response
        elif 'unclear' in text_lower or 'cannot' in text_lower or 'blurry' in text_lower:
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
