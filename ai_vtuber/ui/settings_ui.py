"""AI VTuber - Settings UI Module

Provides a settings panel for configuring audio, TTS, LLM, and avatar settings.

COLOR REFERENCE:
- (30, 30, 40, 240) (Dark Gray-Blue): Settings panel background
- (50, 50, 60, 230) (Medium Dark Gray): Field backgrounds
- (70, 70, 90, 230) (Lighter Dark Gray): Active field background
- (255, 255, 255) (White): Text color
- (100, 150, 255) (Light Blue): Accent color for sliders/checkboxes
- (60, 120, 200) (Blue): Button background
- (80, 140, 220) (Lighter Blue): Button hover state
"""

import logging
import pygame
import pygame.freetype
from typing import Optional, Callable, Any
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)


class SettingsUI:
    """Settings panel for configuring VTuber parameters.
    
    Provides dropdowns, sliders, and text inputs for:
    - Audio input device selection
    - TTS model, voice, speed
    - LLM model, temperature
    - Avatar model path
    - UI preferences
    """

    def __init__(self, width: int, height: int, config: dict) -> None:
        self.width = width
        self.height = height
        self.config = config
        
        # Settings panel state
        self.settings_visible = False
        self.active_field: Optional[str] = None  # Which field is being edited
        self.scroll_offset = 0
        self.max_scroll = 0
        
        # Field definitions: name, type, section, key, display_name, options/limits
        self.fields = [
            # Audio Settings
            {"name": "microphone_index", "type": "dropdown", "section": "audio", "key": "microphone_index", 
             "display_name": "Microphone", "options": self._get_microphone_list()},
            
            # STT Settings
            {"name": "stt_model", "type": "dropdown", "section": "stt", "key": "model_size",
             "display_name": "STT Model", "options": ["tiny", "base", "small", "medium", "large-v3"]},
            {"name": "stt_device", "type": "dropdown", "section": "stt", "key": "device",
             "display_name": "STT Device", "options": ["auto", "cuda", "cpu"]},
            {"name": "vad_threshold", "type": "slider", "section": "stt", "key": "vad_threshold",
             "display_name": "Voice Detection Sensitivity", "min": 0.1, "max": 0.9, "step": 0.1},
            
            # TTS Settings
            {"name": "tts_model", "type": "dropdown", "section": "tts", "key": "model",
             "display_name": "TTS Model", "options": [
                 "KittenML/kitten-tts-nano-0.8-int8",
                 "KittenML/kitten-tts-nano-0.8",
                 "KittenML/kitten-tts-micro-0.8",
                 "KittenML/kitten-tts-mini-0.8"
             ]},
            {"name": "tts_voice", "type": "dropdown", "section": "tts", "key": "voice",
             "display_name": "TTS Voice", "options": ["Bella", "Jasper", "Luna", "Bruno", "Rosie", "Hugo", "Kiki", "Leo"]},
            {"name": "tts_speed", "type": "slider", "section": "tts", "key": "speed",
             "display_name": "TTS Speed", "min": 0.5, "max": 2.0, "step": 0.05},
            {"name": "tts_backend", "type": "dropdown", "section": "tts", "key": "backend",
             "display_name": "TTS Backend", "options": ["cpu", "cuda"]},
            
            # LLM Settings
            {"name": "llm_model", "type": "text", "section": "llm", "key": "model",
             "display_name": "LLM Model"},
            {"name": "llm_temperature", "type": "slider", "section": "llm", "key": "temperature",
             "display_name": "Temperature", "min": 0.1, "max": 2.0, "step": 0.1},
            {"name": "llm_stream", "type": "checkbox", "section": "llm", "key": "stream_enabled",
             "display_name": "Stream LLM Responses"},
            
            # Avatar Settings
            {"name": "avatar_model", "type": "text", "section": "avatar", "key": "model_path",
             "display_name": "Avatar Model Path"},
            {"name": "avatar_scale", "type": "slider", "section": "avatar", "key": "scale",
             "display_name": "Avatar Scale", "min": 0.5, "max": 5.0, "step": 0.1},
            
            # Filler Settings
            {"name": "fillers_enabled", "type": "checkbox", "section": "fillers", "key": "enabled",
             "display_name": "Enable Filler Words"},
            {"name": "start_delay", "type": "slider_int", "section": "fillers", "key": "start_delay_ms",
             "display_name": "Start Delay (ms)", "min": 100, "max": 2000, "step": 100},
            {"name": "stall_threshold", "type": "slider_int", "section": "fillers", "key": "stall_threshold_ms",
             "display_name": "Stall Threshold (ms)", "min": 100, "max": 2000, "step": 100},
        ]
        
        # UI dimensions
        self.panel_width = 400
        self.panel_height = height - 100
        self.panel_x = (width - self.panel_width) // 2
        self.panel_y = 50
        self.field_height = 35
        self.label_width = 180
        self.control_width = 200
        
        # Colors
        self.bg_color = (30, 30, 40, 240)
        self.field_bg = (50, 50, 60, 230)
        self.field_active = (70, 70, 90, 230)
        self.text_color = (255, 255, 255)
        self.accent_color = (100, 150, 255)
        self.button_color = (60, 120, 200)
        self.button_hover = (80, 140, 220)
        
        # Fonts
        self._font: Optional[pygame.freetype.Font] = None
        self._small_font: Optional[pygame.freetype.Font] = None
        
        # Callbacks
        self.on_save: Optional[Callable[[dict], None]] = None
        self.on_close: Optional[Callable[[], None]] = None
        
        # Button states
        self.save_button_rect: Optional[pygame.Rect] = None
        self.cancel_button_rect: Optional[pygame.Rect] = None
        self.close_button_rect: Optional[pygame.Rect] = None
        
        # Temporary config for editing
        self.temp_config: dict = {}
        
    def _get_microphone_list(self) -> list[str]:
        """Get list of available microphones."""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            mics = []
            for i, dev in enumerate(devices):
                if dev['max_input_channels'] > 0:
                    mics.append(f"{i}: {dev['name']}")
            if not mics:
                mics = ["-1: Default Microphone"]
            return ["-1: Default Microphone"] + mics
        except Exception as e:
            logger.warning(f"Could not query microphones: {e}")
            return ["-1: Default Microphone"]
    
    def init_fonts(self) -> None:
        """Initialize fonts after Pygame is initialized."""
        self._font = pygame.freetype.Font(None, 16)
        self._small_font = pygame.freetype.Font(None, 14)
    
    def toggle_visibility(self) -> None:
        """Toggle settings panel visibility."""
        self.settings_visible = not self.settings_visible
        if self.settings_visible:
            self._load_temp_config()
            self.scroll_offset = 0
        logger.info(f"Settings panel {'shown' if self.settings_visible else 'hidden'}")
    
    def _load_temp_config(self) -> None:
        """Load current config into temporary edit buffer."""
        self.temp_config = {
            "audio": dict(self.config.get("audio", {})),
            "stt": dict(self.config.get("stt", {})),
            "tts": dict(self.config.get("tts", {})),
            "llm": dict(self.config.get("llm", {})),
            "avatar": dict(self.config.get("avatar", {})),
            "fillers": dict(self.config.get("fillers", {})),
        }
    
    def _save_config(self) -> bool:
        """Save temporary config to file and reload."""
        try:
            config_path = Path(__file__).parent.parent / "config.yaml"
            
            # Load existing config to preserve comments and structure
            with open(config_path, 'r', encoding='utf-8') as f:
                existing_config = yaml.safe_load(f)
            
            # Update sections
            for section in ["audio", "stt", "tts", "llm", "avatar", "fillers"]:
                if section in self.temp_config:
                    if section not in existing_config:
                        existing_config[section] = {}
                    existing_config[section].update(self.temp_config[section])
            
            # Write back
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(existing_config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
            
            logger.info("Configuration saved successfully")
            
            # Update runtime config
            self.config.update(existing_config)
            
            if self.on_save:
                self.on_save(existing_config)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            return False
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle Pygame events for settings panel.
        
        Returns True if event was consumed, False otherwise.
        """
        if not self.settings_visible:
            return False
        
        if event.type == pygame.MOUSEBUTTONDOWN:
            mouse_pos = pygame.mouse.get_pos()
            
            # Check close button
            if self.close_button_rect and self.close_button_rect.collidepoint(mouse_pos):
                self.toggle_visibility()
                return True
            
            # Check save button
            if self.save_button_rect and self.save_button_rect.collidepoint(mouse_pos):
                if self._save_config():
                    self.toggle_visibility()
                return True
            
            # Check cancel button
            if self.cancel_button_rect and self.cancel_button_rect.collidepoint(mouse_pos):
                self.toggle_visibility()
                return True
            
            # Check field interactions
            self._handle_field_click(mouse_pos)
            return True
        
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.toggle_visibility()
                return True
            
            # Handle text input for active text field
            if self.active_field and self._get_field_type(self.active_field) == "text":
                if event.key == pygame.K_RETURN:
                    self.active_field = None
                    return True
                elif event.key == pygame.K_BACKSPACE:
                    current_value = self._get_field_value(self.active_field)
                    if isinstance(current_value, str):
                        self._set_field_value(self.active_field, current_value[:-1])
                    return True
                elif hasattr(event, 'unicode') and event.unicode:
                    char = event.unicode
                    if char.isprintable():
                        current_value = self._get_field_value(self.active_field)
                        if isinstance(current_value, str):
                            self._set_field_value(self.active_field, current_value + char)
                    return True
        
        elif event.type == pygame.MOUSEMOTION:
            # Handle slider dragging
            if self.active_field:
                field_def = self._get_field_def(self.active_field)
                if field_def and field_def["type"] in ("slider", "slider_int"):
                    mouse_pos = pygame.mouse.get_pos()
                    self._handle_slider_drag(field_def, mouse_pos)
                    return True
        
        elif event.type == pygame.MOUSEBUTTONUP:
            self.active_field = None
            return True
        
        return False
    
    def _handle_field_click(self, mouse_pos: tuple[int, int]) -> None:
        """Handle click on settings fields."""
        y = self.panel_y + 20 - self.scroll_offset
        
        for field_def in self.fields:
            field_rect = pygame.Rect(
                self.panel_x + 20,
                y,
                self.panel_width - 40,
                self.field_height
            )
            
            if field_rect.collidepoint(mouse_pos):
                field_type = field_def["type"]
                
                if field_type == "dropdown":
                    # Cycle through options
                    current = self._get_field_value(field_def["name"])
                    options = field_def.get("options", [])
                    if options:
                        try:
                            idx = options.index(current)
                            next_idx = (idx + 1) % len(options)
                            self._set_field_value(field_def["name"], options[next_idx])
                        except ValueError:
                            self._set_field_value(field_def["name"], options[0])
                
                elif field_type == "checkbox":
                    # Toggle checkbox
                    current = self._get_field_value(field_def["name"])
                    self._set_field_value(field_def["name"], not current)
                
                elif field_type in ("slider", "slider_int"):
                    # Start slider drag
                    self.active_field = field_def["name"]
                    self._handle_slider_drag(field_def, mouse_pos)
                
                elif field_type == "text":
                    # Activate text input
                    self.active_field = field_def["name"]
                
                break
            
            y += self.field_height + 5
        
        # Calculate max scroll
        total_height = len(self.fields) * (self.field_height + 5) + 80
        self.max_scroll = max(0, total_height - (self.panel_height - 40))
    
    def _handle_slider_drag(self, field_def: dict, mouse_pos: tuple[int, int]) -> None:
        """Handle slider value change based on mouse position."""
        min_val = field_def.get("min", 0)
        max_val = field_def.get("max", 100)
        step = field_def.get("step", 1)
        
        slider_x = self.panel_x + 20 + self.label_width + 10
        slider_width = self.control_width - 20
        
        # Calculate value from mouse X
        rel_x = max(0, min(1, (mouse_pos[0] - slider_x) / slider_width))
        value = min_val + rel_x * (max_val - min_val)
        
        # Round to step
        if step >= 1:
            value = round(value / step) * step
        else:
            value = round(value / step) * step
        
        if field_def["type"] == "slider_int":
            value = int(value)
        
        self._set_field_value(field_def["name"], value)
    
    def _get_field_def(self, name: str) -> Optional[dict]:
        """Get field definition by name."""
        for field in self.fields:
            if field["name"] == name:
                return field
        return None
    
    def _get_field_type(self, name: str) -> str:
        """Get field type by name."""
        field_def = self._get_field_def(name)
        return field_def["type"] if field_def else "text"
    
    def _get_field_value(self, name: str) -> Any:
        """Get current value for a field from temp config."""
        for field in self.fields:
            if field["name"] == name:
                section = field["section"]
                key = field["key"]
                return self.temp_config.get(section, {}).get(key, None)
        return None
    
    def _set_field_value(self, name: str, value: Any) -> None:
        """Set value for a field in temp config."""
        for field in self.fields:
            if field["name"] == name:
                section = field["section"]
                key = field["key"]
                if section not in self.temp_config:
                    self.temp_config[section] = {}
                self.temp_config[section][key] = value
                break
    
    def update(self, delta_time: float) -> None:
        """Update settings state."""
        pass  # No continuous updates needed
    
    def draw(self, screen: pygame.Surface) -> None:
        """Draw the settings panel."""
        if not self.settings_visible or not self._font:
            return
        
        # Draw semi-transparent background overlay
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        screen.blit(overlay, (0, 0))
        
        # Draw settings panel background
        panel_rect = pygame.Rect(self.panel_x, self.panel_y, self.panel_width, self.panel_height)
        pygame.draw.rect(screen, self.bg_color, panel_rect, border_radius=10)
        
        # Draw title
        title_text = "⚙ Settings"
        self._font.render_to(screen, (self.panel_x + 20, self.panel_y + 15), title_text, self.text_color)
        
        # Draw close button
        close_btn_rect = pygame.Rect(self.panel_x + self.panel_width - 40, self.panel_y + 10, 30, 30)
        pygame.draw.rect(screen, self.button_color, close_btn_rect, border_radius=5)
        self._small_font.render_to(screen, (close_btn_rect.x + 10, close_btn_rect.y + 8), "✕", self.text_color)
        self.close_button_rect = close_btn_rect
        
        # Draw fields with scrolling
        clip_rect = pygame.Rect(self.panel_x + 10, self.panel_y + 50, self.panel_width - 20, self.panel_height - 100)
        screen.set_clip(clip_rect)
        
        y = self.panel_y + 20 - self.scroll_offset
        for field_def in self.fields:
            field_rect = pygame.Rect(
                self.panel_x + 20,
                y,
                self.panel_width - 40,
                self.field_height
            )
            
            # Draw field background
            bg_color = self.field_active if self.active_field == field_def["name"] else self.field_bg
            pygame.draw.rect(screen, bg_color, field_rect, border_radius=5)
            
            # Draw label
            label = field_def["display_name"]
            self._small_font.render_to(screen, (field_rect.x + 10, field_rect.y + 10), label, self.text_color)
            
            # Draw control based on type
            field_type = field_def["type"]
            current_value = self._get_field_value(field_def["name"])
            
            if field_type == "dropdown":
                self._draw_dropdown(screen, field_rect, current_value, field_def.get("options", []))
            elif field_type == "checkbox":
                self._draw_checkbox(screen, field_rect, current_value)
            elif field_type in ("slider", "slider_int"):
                self._draw_slider(screen, field_rect, current_value, field_def)
            elif field_type == "text":
                self._draw_text_input(screen, field_rect, str(current_value) if current_value else "")
            
            y += self.field_height + 5
        
        screen.set_clip(None)
        
        # Draw buttons at bottom
        button_y = self.panel_y + self.panel_height - 40
        
        # Save button
        self.save_button_rect = pygame.Rect(self.panel_x + 20, button_y, 100, 30)
        pygame.draw.rect(screen, self.button_color, self.save_button_rect, border_radius=5)
        self._small_font.render_to(screen, (self.save_button_rect.x + 25, button_y + 8), "Save", self.text_color)
        
        # Cancel button
        self.cancel_button_rect = pygame.Rect(self.panel_x + 140, button_y, 100, 30)
        pygame.draw.rect(screen, (100, 100, 100), self.cancel_button_rect, border_radius=5)
        self._small_font.render_to(screen, (self.cancel_button_rect.x + 20, button_y + 8), "Cancel", self.text_color)
        
        # Scroll indicator if content overflows
        if self.max_scroll > 0:
            scroll_height = max(30, int((self.panel_height - 100) / (len(self.fields) * (self.field_height + 5) + 80) * (self.panel_height - 100)))
            scroll_y = self.panel_y + 50 + int(self.scroll_offset / max(1, self.max_scroll) * (self.panel_height - 100 - scroll_height))
            scroll_rect = pygame.Rect(self.panel_x + self.panel_width - 10, scroll_y, 5, scroll_height)
            pygame.draw.rect(screen, self.accent_color, scroll_rect, border_radius=2)
    
    def _draw_dropdown(self, screen: pygame.Surface, rect: pygame.Rect, value: Any, options: list[str]) -> None:
        """Draw dropdown field."""
        display_value = str(value) if value else (options[0] if options else "")
        # Truncate if too long
        if len(display_value) > 25:
            display_value = display_value[:22] + "..."
        self._small_font.render_to(screen, (rect.right - 150, rect.y + 10), f"▼ {display_value}", self.accent_color)
    
    def _draw_checkbox(self, screen: pygame.Surface, rect: pygame.Rect, checked: bool) -> None:
        """Draw checkbox field."""
        box_rect = pygame.Rect(rect.right - 30, rect.y + 10, 20, 20)
        pygame.draw.rect(screen, self.accent_color if checked else (100, 100, 100), box_rect, border_radius=3)
        if checked:
            self._small_font.render_to(screen, (box_rect.x + 5, box_rect.y + 2), "✓", (255, 255, 255))
    
    def _draw_slider(self, screen: pygame.Surface, rect: pygame.Rect, value: Any, field_def: dict) -> None:
        """Draw slider field."""
        min_val = field_def.get("min", 0)
        max_val = field_def.get("max", 100)
        step = field_def.get("step", 1)
        
        slider_x = rect.right - 150
        slider_y = rect.y + 17
        slider_width = 100
        slider_height = 6
        
        # Draw track
        track_rect = pygame.Rect(slider_x, slider_y, slider_width, slider_height)
        pygame.draw.rect(screen, (100, 100, 100), track_rect, border_radius=3)
        
        # Calculate handle position (snap to step for display)
        if max_val != min_val:
            rel_pos = (value - min_val) / (max_val - min_val)
        else:
            rel_pos = 0
        handle_x = slider_x + int(rel_pos * slider_width)
        
        # Draw handle
        handle_rect = pygame.Rect(handle_x - 3, slider_y - 3, 12, 12)
        pygame.draw.rect(screen, self.accent_color, handle_rect, border_radius=6)
        
        # Draw value (rounded to step for display)
        if step >= 1:
            display_value = round(value / step) * step
            if field_def["type"] == "slider_int":
                display_value = int(display_value)
        else:
            display_value = round(value / step) * step
        self._small_font.render_to(screen, (slider_x + slider_width + 10, rect.y + 10), str(display_value), self.text_color)
    
    def _draw_text_input(self, screen: pygame.Surface, rect: pygame.Rect, text: str) -> None:
        """Draw text input field."""
        # Truncate if too long
        display_text = text[-20:] if len(text) > 20 else text
        if self.active_field and text:
            display_text += "|"  # Cursor
        self._small_font.render_to(screen, (rect.right - 150, rect.y + 10), display_text, self.accent_color)
