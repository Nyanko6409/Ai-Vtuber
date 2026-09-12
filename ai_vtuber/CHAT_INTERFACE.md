# Chat Interface Implementation

## Overview
The AI VTuber now includes a text-based chat interface that allows you to communicate with the AI via text input, in addition to voice input. This is useful for testing the LLM and TTS systems without needing to speak.

## Features

### Chat Input Box
- **Location**: Bottom of the window with rounded corners
- **Appearance**: Semi-transparent dark background with blue border when active
- **Placeholder**: "Type a message... (Enter to send, Tab to toggle focus)"
- **Character limit**: 200 characters

### Message Display
- **User messages**: Displayed in blue
- **AI responses**: Displayed in green with typewriter effect
- **Location**: Above the input box, showing conversation history
- **Auto-scroll**: Latest messages are always visible

### Typewriter Effect
- AI responses appear character by character (0.03 seconds per character)
- Creates a natural typing animation
- Full text is logged in CLI debug output

### Controls
- **Enter**: Send message
- **Backspace**: Delete character
- **Tab**: Toggle chat input focus (when not in chat mode)
- **ESC**: Quit application (when chat is not active)
- **F**: Toggle FPS display (when chat is not active)
- **D**: Toggle debug info (when chat is not active)

## Usage

### Starting the Application
```bash
cd ai_vtuber
python main.py --debug
```

### Sending Messages
1. The chat input is active by default (blue border)
2. Type your message in the input box
3. Press **Enter** to send
4. The AI will respond with text (typewriter effect) and voice (TTS)

### Toggling Chat Focus
- Press **Tab** to toggle between chat mode and normal mode
- In chat mode: All typing goes to the chat input
- In normal mode: Keyboard shortcuts (ESC, F, D) work normally

## Technical Details

### Files Modified
1. **main.py**
   - Added `import pygame`
   - Refactored event handling to process events once
   - Integrated chat UI event handling
   - Added chat UI update and drawing in main loop

2. **ui/chat_ui.py**
   - Implemented `ChatUI` class with input handling
   - Added typewriter effect for AI responses
   - Message history management
   - Drawing routines for input box and messages

3. **core/app.py**
   - Added `process_chat_message()` method
   - Added `_process_chat_message_thread()` for background processing
   - Integrated with existing LLM/TTS pipeline

### Event Handling Flow
```
1. pygame.event.get() retrieves all events once
2. For each event:
   - If QUIT: Exit application
   - If VIDEORESIZE: Resize window
   - If KEYDOWN:
     - If chat is active: Pass to chat_ui.handle_event()
     - If chat is inactive: Handle shortcuts (ESC, F, D, Tab)
```

### Message Processing Flow
```
1. User types message and presses Enter
2. chat_ui.handle_event() returns the message
3. app.process_chat_message() is called
4. Background thread starts:
   - Add message to conversation history
   - Generate LLM response with emotion tag
   - Parse emotion and update avatar expression
   - Generate TTS audio
   - Play audio
   - Update UI with response (typewriter effect)
```

## Debug Output

All chat interactions are logged in the CLI:
```
[core.app] INFO: Chat message: Hello, how are you?
[core.app] INFO: AI response: [happy] I'm doing great, thanks for asking!
```

## Known Issues and Fixes

### Issue: pygame not defined
**Cause**: Missing `import pygame` in main.py  
**Fix**: Added `import pygame` at the top of main.py

### Issue: Events consumed twice
**Cause**: `pygame.event.get()` was called in both ui.handle_events() and main loop  
**Fix**: Refactored to call `pygame.event.get()` once in main loop and pass events to handlers

### Issue: ESC key conflict
**Cause**: ESC was used for both quitting and toggling chat focus  
**Fix**: Changed chat toggle to Tab key, ESC only quits when chat is inactive

## Testing the Pipeline

You can now test the complete pipeline:
1. **STT**: Speak into microphone (voice input still works)
2. **LLM**: Type in chat box OR speak
3. **TTS**: AI responds with voice
4. **Avatar**: Live2D model shows emotions and lip sync
5. **UI**: Chat messages display with typewriter effect

## Future Enhancements

Potential improvements:
- Scrollable message history
- Message timestamps
- Emotion indicators in chat
- Voice/text input toggle button
- Chat history export
- Multi-line input support
