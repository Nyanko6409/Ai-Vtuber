# Changelog

All notable changes to the AI VTuber project will be documented in this file.

## [1.2.2] - 2026-09-12

### Fixed
- **F and D keyboard input bug**: When ChatUI text input is active/focused, pressing F or D now types "f" or "d" normally instead of triggering global shortcuts (FPS/debug toggle). F and D shortcuts only work when chat input is NOT active.

### Changed
- Modified keyboard event handling in `main.py` to check `chat_ui.input_active` before processing F and D shortcuts
- F key toggles FPS display only when chat input is inactive
- D key toggles debug display only when chat input is inactive
- Tab and ESC keys retain their global shortcut behavior regardless of chat state

## [1.2.1] - 2026-09-12

### Fixed
- **Upside down text rendering**: Fixed OpenGL texture coordinates in both chat UI and overlay to properly orient text (flipped Y-axis texture coordinates)
- **Keyboard shortcuts not working**: Special keys (Tab, ESC, F, D) now work even when chat input is active by giving them priority over chat input handling
- **CUDA library error**: Added troubleshooting guide for `libcublas.so.12` missing error with three solution options

### Changed
- Keyboard event handling now processes special keys (Tab, ESC, F, D) before chat input, ensuring shortcuts always work
- Updated README with improved keyboard shortcuts documentation and CUDA troubleshooting section

## [1.2.0] - 2026-09-12

### Added
- **Chat Interface with Control Buttons**
  - Toggle button to show/hide chat interface
  - Clear button to reset conversation history
  - Mouse hover effects on buttons
  - Visual feedback for button states
  - OpenGL texture rendering for smooth chat UI

- **Enhanced Event Handling**
  - Refactored event processing to avoid conflicts
  - Separate handling for chat and system events
  - Improved keyboard shortcut management
  - Better focus management between chat and system

- **Diagnostic Tools**
  - `test_model_diagnostic.py` - Validates Live2D model files
  - `test_python_compat.py` - Checks Python/native compatibility
  - `test_live2d_standalone.py` - Isolates Live2D issues
  - `test_opengl_check.py` - Verifies OpenGL/WSL compatibility

### Changed
- **Chat UI Rendering**
  - Migrated from direct surface drawing to OpenGL texture rendering
  - Improved performance and compatibility with OpenGL mode
  - Better transparency handling

- **Event Processing**
  - Events now processed once per frame
  - Chat events handled separately from system events
  - Tab key now toggles chat visibility (was focus toggle)

- **Button Controls**
  - Chat toggle moved from Tab key to dedicated button
  - ESC key only quits when chat is inactive
  - Clear chat button added for easy conversation reset

### Fixed
- **Critical Bugs**
  - Fixed `NameError: name 'pygame' is not defined`
  - Fixed event handling conflicts between chat and system
  - Fixed ESC key conflict with chat input
  - Fixed button click detection issues

- **Live2D Issues**
  - Added comprehensive error handling for model loading
  - Better error messages for Python version mismatch
  - File validation before model loading
  - Graceful degradation when Live2D fails

- **Performance**
  - Optimized event processing loop
  - Reduced redundant pygame.event.get() calls
  - Improved memory management for chat messages

### Technical Details

#### Chat UI Implementation
```python
# New button system
chat_ui.handle_button_click(mouse_pos)  # Handle button clicks
chat_ui.update_hover(mouse_pos)          # Update hover state
chat_ui.toggle_chat()                    # Toggle visibility
chat_ui.clear_chat()                     # Clear history
```

#### Event Handling Flow
```python
# Events processed once per frame
events = pygame.event.get()
for event in events:
    if event.type == pygame.MOUSEBUTTONDOWN:
        action = chat_ui.handle_button_click(event.pos)
        # Handle button actions
    elif event.type == pygame.KEYDOWN:
        if chat_ui.input_active:
            message = chat_ui.handle_event(event)
            # Process chat message
```

## [1.1.0] - 2026-09-11

### Added
- **Text Chat Interface**
  - Input box at bottom of window
  - Message history display
  - Typewriter effect for AI responses
  - Color-coded messages (user: blue, AI: green)
  - 200 character input limit

- **Chat Integration**
  - `process_chat_message()` method in App class
  - Background thread processing for chat messages
  - Integration with existing LLM/TTS pipeline
  - Full conversation logging in CLI

### Changed
- **Application Architecture**
  - Added ChatUI class for text input
  - Integrated chat with existing voice pipeline
  - Improved state management for dual input modes

### Fixed
- **KittenTTS Integration**
  - Fixed model loading for official 0.8.1 package
  - Proper error handling for missing espeak
  - Better voice selection and validation

- **STT CUDA Detection**
  - Migrated from PyTorch to CTranslate2 for CUDA detection
  - No PyTorch dependency required
  - Better fallback to CPU when CUDA unavailable

## [1.0.1] - 2026-09-10

### Fixed
- **Live2D Model Loading**
  - Added file validation before loading
  - Better error messages for missing files
  - Graceful handling of corrupted models
  - Python version compatibility checking

- **Error Handling**
  - Comprehensive exception handling throughout
  - Clear error messages in UI
  - Debug logging for troubleshooting
  - Graceful degradation when components fail

### Added
- **Diagnostic Scripts**
  - Model file validation
  - Python/native compatibility checking
  - Standalone Live2D testing
  - OpenGL/WSL verification

## [1.0.0] - 2026-09-09

### Initial Release
- Live2D avatar rendering with live2d-py
- Speech recognition with faster-whisper
- Text-to-speech with KittenTTS
- LLM integration via LM Studio
- Emotion-based avatar expressions
- Voice activity detection
- Real-time conversation
- Pygame/OpenGL UI

### Features
- Full local operation (no external APIs)
- CUDA acceleration for STT
- Configurable via YAML
- Debug logging
- State machine for pipeline management
- Conversation history
- Interruption handling

---

## Version History Summary

- **1.2.2** - Fixed F/D keyboard input bug (typing in chat)
- **1.2.1** - Fixed upside-down text, keyboard shortcuts, CUDA documentation
- **1.2.0** - Chat interface with buttons, improved event handling
- **1.1.0** - Text chat interface, KittenTTS integration
- **1.0.1** - Live2D fixes, error handling, diagnostics
- **1.0.0** - Initial release with core features

## Upcoming Features

### Planned for 1.3.0
- Scrollable message history
- Message timestamps
- Emotion indicators in chat
- Voice/text input toggle button
- Chat history export
- Multi-line input support

### Future Considerations
- Additional Live2D models
- More voice options
- Enhanced emotion detection
- Multi-language support
- Performance optimizations
- Mobile companion app
