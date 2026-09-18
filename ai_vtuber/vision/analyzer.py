"""AI VTuber - Visual Scene Analysis using Vision-Capable LLM"""

import io
import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class SceneInfo:
    """Structured scene information from vision analysis."""
    application: Optional[str] = None
    application_type: Optional[str] = None  # 'game', 'browser', 'video', 'code', etc.
    activity: Optional[str] = None
    game_name: Optional[str] = None
    location: Optional[str] = None


@dataclass
class StateInfo:
    """Structured state information from vision analysis."""
    in_combat: Optional[bool] = None
    in_menu: Optional[bool] = None
    in_dialogue: Optional[bool] = None
    loading: Optional[bool] = None
    player_health_low: Optional[bool] = None


@dataclass
class EntityInfo:
    """Entity extracted from vision analysis."""
    entity_type: str  # 'character', 'enemy', 'npc', 'item', 'location', 'ui_element'
    name: str
    confidence: float = 0.7
    description: Optional[str] = None


@dataclass
class VisionAnalysisResult:
    """Result of visual scene analysis with structured JSON output."""
    # Structured scene info
    scene: Optional[SceneInfo] = None
    # Structured state info  
    state: Optional[StateInfo] = None
    # List of observations about the scene
    observations: List[str] = field(default_factory=list)
    # Visible text (OCR-like)
    visible_text: List[str] = field(default_factory=list)
    # Extracted entities
    entities: List[EntityInfo] = field(default_factory=list)
    # Detected events/changes
    events: List[str] = field(default_factory=list)
    # Model confidence (if provided by model, else None)
    confidence: Optional[float] = None
    # Raw description for fallback
    description: str = ""
    # Significant changes from previous state
    significant_changes: List[str] = field(default_factory=list)
    # Timestamp
    timestamp: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "observations": self.observations,
            "visible_text": self.visible_text,
            "entities": [
                {"type": e.entity_type, "name": e.name, "confidence": e.confidence}
                for e in self.entities
            ],
            "events": self.events,
            "significant_changes": self.significant_changes,
            "description": self.description,
            "timestamp": self.timestamp
        }
        
        if self.scene:
            result["scene"] = {
                "application": self.scene.application,
                "application_type": self.scene.application_type,
                "activity": self.scene.activity,
                "game_name": self.scene.game_name,
                "location": self.scene.location
            }
        
        if self.state:
            result["state"] = {
                "in_combat": self.state.in_combat,
                "in_menu": self.state.in_menu,
                "in_dialogue": self.state.in_dialogue,
                "loading": self.state.loading,
                "player_health_low": self.state.player_health_low
            }
        
        if self.confidence is not None:
            result["confidence"] = self.confidence
            
        return result


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
        """Build structured JSON prompt for Gemma vision analysis."""
        
        base_prompt = """You are analyzing a screen image for an AI VTuber assistant. Return your analysis as VALID JSON only, no markdown, no explanations.

Required JSON structure:
{
  "scene": {
    "application": "<app/window name or null>",
    "application_type": "<game|browser|video|code|document|social|image|other or null>",
    "activity": "<what user is doing or null>",
    "game_name": "<game name if playing, else null>",
    "location": "<in-game location or null>"
  },
  "state": {
    "in_combat": <boolean or null>,
    "in_menu": <boolean or null>,
    "in_dialogue": <boolean or null>,
    "loading": <boolean or null>,
    "player_health_low": <boolean or null>
  },
  "observations": ["<short observation 1>", "<short observation 2>"],
  "visible_text": ["<text snippet 1>", "<text snippet 2>"],
  "entities": [
    {"type": "<character|enemy|npc|item|location|ui_element>", "name": "<name>", "confidence": <0.0-1.0>}
  ],
  "events": ["<event 1>", "<event 2>"],
  "confidence": <0.0-1.0 overall confidence>
}

Rules:
- Use null for unknown/unsure values, do not invent information
- Keep observations concise (5-10 words each)
- Only include entities you are confident about (confidence >= 0.6)
- For state booleans, use null if cannot determine from image
- application_type must be exactly one of: game, browser, video, code, document, social, image, other
- Return ONLY valid JSON, no markdown formatting"""

        parts = [base_prompt]
        
        if context_hint:
            parts.append(f"\n\nContext hint: {context_hint}")
        
        if cached_state:
            parts.append("\n\nPrevious context (note any changes):")
            prev_parts = []
            if cached_state.get('game_name'):
                prev_parts.append(f"Game/App: {cached_state['game_name']}")
            if cached_state.get('location'):
                prev_parts.append(f"Location: {cached_state['location']}")
            if cached_state.get('in_combat'):
                prev_parts.append("Was in combat")
            if cached_state.get('in_menu'):
                prev_parts.append("Was in menu")
            if prev_parts:
                parts.append(" | ".join(prev_parts))
        
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
            
            logger.debug(f"[VISION_CALL] Model: {self.model}, Image size: {len(image_base64)} bytes (base64)")
            
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
            
            logger.debug("[VISION_CALL] Sending multimodal request with image_url content block...")
            
            # Use chat.completions.create with multimodal content
            # The OpenAI Python client handles encoding images properly
            response = self.client._client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                stream=False,
                timeout=self.timeout
            )
            
            # Log response structure for debugging
            logger.debug(f"[VISION_CALL] Response status: HTTP 200 OK")
            logger.debug(f"[VISION_CALL] Response object keys: {dir(response)}")
            logger.debug(f"[VISION_CALL] Choices count: {len(response.choices) if hasattr(response, 'choices') else 0}")
            
            if not hasattr(response, 'choices') or len(response.choices) == 0:
                logger.error("[VISION_CALL] Response has no choices - model may not support vision")
                return None
            
            choice = response.choices[0]
            logger.debug(f"[VISION_CALL] Choice object keys: {dir(choice)}")
            
            if not hasattr(choice, 'message'):
                logger.error("[VISION_CALL] Choice has no message attribute")
                return None
            
            message = choice.message
            logger.debug(f"[VISION_CALL] Message object keys: {dir(message)}")
            
            content = getattr(message, 'content', None)
            
            # Log raw response for debugging (truncated)
            if content:
                preview = content[:200] + "..." if len(content) > 200 else content
                logger.debug(f"[VISION_CALL] Raw response (truncated): {preview}")
            else:
                logger.warning("[VISION_CALL] Response content is None or empty")
                # Check if there's a refusal or error in other fields
                if hasattr(message, 'refusal'):
                    logger.warning(f"[VISION_CALL] Model refusal: {message.refusal}")
                if hasattr(choice, 'finish_reason'):
                    logger.warning(f"[VISION_CALL] Finish reason: {choice.finish_reason}")
            
            return content if content else ""
            
        except Exception as e:
            logger.error(f"[VISION_CALL] Vision call failed with exception: {type(e).__name__}: {e}")
            return None
    
    def _parse_response(
        self,
        response_text: str,
        cached_state: Optional[Dict]
    ) -> VisionAnalysisResult:
        """Parse LLM JSON response into structured result."""
        
        # Try to extract JSON from response (handle markdown wrapping)
        json_str = self._extract_json_from_response(response_text)
        
        if not json_str:
            # Fallback: create minimal result from raw text
            logger.warning("No valid JSON found in response, using fallback")
            return self._fallback_parse(response_text, cached_state)
        
        # Parse JSON
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed: {e}, using fallback")
            return self._fallback_parse(response_text, cached_state)
        
        # Extract scene info
        scene = None
        if 'scene' in data and isinstance(data['scene'], dict):
            scene_data = data['scene']
            scene = SceneInfo(
                application=scene_data.get('application'),
                application_type=scene_data.get('application_type'),
                activity=scene_data.get('activity'),
                game_name=scene_data.get('game_name'),
                location=scene_data.get('location')
            )
        
        # Extract state info
        state = None
        if 'state' in data and isinstance(data['state'], dict):
            state_data = data['state']
            state = StateInfo(
                in_combat=state_data.get('in_combat'),
                in_menu=state_data.get('in_menu'),
                in_dialogue=state_data.get('in_dialogue'),
                loading=state_data.get('loading'),
                player_health_low=state_data.get('player_health_low')
            )
        
        # Extract observations
        observations = []
        if 'observations' in data and isinstance(data['observations'], list):
            observations = [str(o) for o in data['observations'] if o]
        
        # Extract visible text
        visible_text = []
        if 'visible_text' in data and isinstance(data['visible_text'], list):
            visible_text = [str(t) for t in data['visible_text'] if t]
        
        # Extract entities
        entities = []
        if 'entities' in data and isinstance(data['entities'], list):
            for ent in data['entities']:
                if isinstance(ent, dict) and 'type' in ent and 'name' in ent:
                    conf = ent.get('confidence', 0.7)
                    if isinstance(conf, (int, float)) and 0.0 <= conf <= 1.0:
                        entities.append(EntityInfo(
                            entity_type=str(ent['type']),
                            name=str(ent['name']),
                            confidence=float(conf),
                            description=ent.get('description')
                        ))
        
        # Extract events
        events = []
        if 'events' in data and isinstance(data['events'], list):
            events = [str(e) for e in data['events'] if e]
        
        # Extract confidence
        confidence = None
        if 'confidence' in data:
            conf_val = data['confidence']
            if isinstance(conf_val, (int, float)) and 0.0 <= conf_val <= 1.0:
                confidence = float(conf_val)
        
        # Compute significant changes by comparing with cached state
        significant_changes = self._compute_significant_changes(scene, state, cached_state)
        
        # Build description from observations
        description = "; ".join(observations) if observations else response_text.strip()
        
        return VisionAnalysisResult(
            scene=scene,
            state=state,
            observations=observations,
            visible_text=visible_text,
            entities=entities,
            events=events,
            confidence=confidence,
            description=description,
            significant_changes=significant_changes,
            timestamp=time.time()
        )
    
    def _extract_json_from_response(self, response_text: str) -> Optional[str]:
        """Extract JSON string from response, handling markdown wrapping."""
        if not response_text or not response_text.strip():
            return None
        
        text = response_text.strip()
        
        # Try parsing as raw JSON first
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass
        
        # Remove markdown code blocks
        # Pattern: ```json ... ``` or ``` ... ```
        patterns = [
            r'```json\s*(.*?)\s*```',
            r'```\s*(.*?)\s*```',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                candidate = match.group(1).strip()
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    continue
        
        # Try to find JSON object between braces
        brace_match = re.search(r'\{.*\}', text, re.DOTALL)
        if brace_match:
            candidate = brace_match.group(0)
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass
        
        return None
    
    def _fallback_parse(
        self,
        response_text: str,
        cached_state: Optional[Dict]
    ) -> VisionAnalysisResult:
        """Fallback parsing when JSON is not available."""
        # Return minimal result with raw text as description
        return VisionAnalysisResult(
            scene=None,
            state=None,
            observations=[],
            visible_text=[],
            entities=[],
            events=[],
            confidence=None,
            description=response_text.strip(),
            significant_changes=[],
            timestamp=time.time()
        )
    
    def _compute_significant_changes(
        self,
        scene: Optional[SceneInfo],
        state: Optional[StateInfo],
        cached_state: Optional[Dict]
    ) -> List[str]:
        """Compare current analysis with cached state to detect meaningful changes."""
        changes = []
        
        if not cached_state:
            return changes
        
        # Check application/game change
        if scene:
            prev_game = cached_state.get('game_name')
            if scene.game_name and scene.game_name != prev_game:
                changes.append(f"Game/application changed to '{scene.game_name}'")
            
            prev_app = cached_state.get('app_name')
            if scene.application and scene.application != prev_app:
                changes.append(f"Application changed to '{scene.application}'")
            
            prev_location = cached_state.get('location')
            if scene.location and scene.location != prev_location:
                changes.append(f"Location changed to '{scene.location}'")
        
        # Check state changes
        if state:
            prev_combat = cached_state.get('in_combat', False)
            if state.in_combat is not None and state.in_combat != prev_combat:
                if state.in_combat:
                    changes.append("Combat started")
                else:
                    changes.append("Combat ended")
            
            prev_menu = cached_state.get('in_menu', False)
            if state.in_menu is not None and state.in_menu != prev_menu:
                if state.in_menu:
                    changes.append("Menu opened")
                else:
                    changes.append("Menu closed")
            
            prev_dialogue = cached_state.get('in_dialogue', False)
            if state.in_dialogue is not None and state.in_dialogue != prev_dialogue:
                if state.in_dialogue:
                    changes.append("Dialogue started")
                else:
                    changes.append("Dialogue ended")
            
            prev_loading = cached_state.get('loading', False)
            if state.loading is not None and state.loading != prev_loading:
                if state.loading:
                    changes.append("Loading started")
                else:
                    changes.append("Loading finished")
            
            prev_health_low = cached_state.get('player_health_low', False)
            if state.player_health_low is not None and state.player_health_low != prev_health_low:
                if state.player_health_low:
                    changes.append("Player health LOW")
                else:
                    changes.append("Player health recovered")
        
        return changes
    
    def extract_entities_from_analysis(
        self,
        result: VisionAnalysisResult
    ) -> Dict[str, List[str]]:
        """
        Extract entity mentions from analysis result.
        
        Now uses structured entities from JSON output when available.
        Falls back to simple heuristics for legacy plain-text responses.
        
        Returns:
            Dict mapping entity types to lists of names
        """
        entities = {
            'characters': [],
            'enemies': [],
            'locations': [],
            'ui_elements': [],
            'items': [],
            'npcs': []
        }
        
        # First try structured entities from JSON output
        if result.entities:
            for ent in result.entities:
                ent_type = ent.entity_type.lower()
                name = ent.name.strip()
                
                if ent_type in ['character', 'npc']:
                    entities['characters'].append(name)
                elif ent_type == 'enemy':
                    entities['enemies'].append(name)
                elif ent_type == 'location':
                    entities['locations'].append(name)
                elif ent_type == 'item':
                    entities['items'].append(name)
                elif ent_type == 'ui_element':
                    entities['ui_elements'].append(name)
            
            return entities
        
        # Fallback: simple keyword-based extraction from description
        text = result.description.lower()
        
        # Look for location indicators (very basic)
        if ' in ' in text:
            # Potential location mentions after "in"
            pass  # Would need more sophisticated parsing
        
        return entities
