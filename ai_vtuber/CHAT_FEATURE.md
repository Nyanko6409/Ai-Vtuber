# Chat Interface Feature

## Overview

A text-based chat interface has been added to the AI VTuber application, allowing you to test the LLM and TTS by typing messages directly.

## Features

### 1. Chat Input Box
- **Location**: Bottom of the window with rounded corners
- **Style**: Semi-transparent dark background with border
- **Placeholder**: "Type a message... (Enter to send, Esc to toggle)"
- **Character limit**: 200 characters

### 2. Message History
- **Display**: Shows last 10 messages (user and AI)
- **User messages**: Blue color
- **AI messages**: Green color
- **Location**: Above the input box

### 3. Typewriter Effect
- **Behavior**: AI responses appear character by character
- **Speed**: 0.03 seconds per character
- **Visual**: Creates a natural typing animation
- **Full text**: Always available in CLI debug logs

### 4. Keyboard Controls
- **Enter**: Send message
- **Backspace**: Delete character
- **Esc**: Toggle input focus
- **Any printable key**: Add character to input

## How It Works

### User Input Flow
1. Type message in the input box
2. Press Enter to send
3. Message appears in chat history (blue)
4. Message is sent to LLM via `app.process_chat_message()`

### AI Response Flow
1. LLM generates response with emotion tag
2. Response is parsed (emotion tag extracted)
3. Avatar expression is updated
4. Response appears in chat history (green)
5. **Typewriter effect**: Text appears character by character
6. TTS generates audio
7. Audio plays through speakers
8. Avatar mouth animates during speech

### Integration with Voice Input
- Chat input works **alongside** voice input
- Both can be used simultaneously
- Voice input still uses the original pipeline
- Chat input uses the same LLM/TTS pipeline

## Usage

### Starting the Application
```bash
cd ai_vtuber
python main.py --debug
```

### Sending a Message
1. Click on the input box (or it's active by default)
2. Type your message
3. Press Enter
4. Watch the AI respond with typewriter effect
5. Listen to the TTS audio

### Example Conversation
```
You: Hello! How are you?
AI: [happy] I'm doing great, thanks for asking! How can I help you today?
```

### Debug Output
All messages are logged to the CLI:
```
[core.app] INFO: Chat message: Hello! How are you?
[core.app] INFO: AI response: [happy] I'm doing great, thanks for asking!
```

## Technical Details

### Files Modified
1. **`ai_vtuber/ui/chat_ui.py`** (NEW)
   - ChatUI class with input handling
   - Typewriter effect implementation
   - Message history management
   - Drawing routines

2. **`ai_vtuber/core/app.py`**
   - Added `process_chat_message()` method
   - Added `_process_chat_message_thread()` for background processing
   - Integrates with existing LLM/TTS pipeline

3. **`ai_vtuber/main.py`**
   - Initialize ChatUI
   - Handle chat events in main loop
   - Update chat UI with current response
   - Draw chat UI on top of everything

### Architecture
```
User types message
    ↓
ChatUI.handle_event() captures input
    ↓
Enter pressed → callback to main.py
    ↓
app.process_chat_message(text)
    ↓
Background thread: _process_chat_message_thread()
    ↓
Add to conversation history
    ↓
Generate LLM response
    ↓
Parse emotion tag
    ↓
Update avatar expression
    ↓
Generate TTS audio
    ↓
Play audio
    ↓
Update UI with response (typewriter effect)
```

### Typewriter Effect Implementation
- **State tracking**: `typewriter_target`, `typewriter_text`, `typewriter_index`
- **Timer-based**: Advances one character every 0.03 seconds
- **Automatic**: Starts when new AI response is detected
- **Non-blocking**: Runs in main UI thread, doesn't block audio

## Testing the Pipeline

### Test LLM
1. Type a message
2. Check CLI for response generation
3. Verify emotion tag is parsed correctly
4. Check avatar expression changes

### Test TTS
1. Send a message
2. Listen for audio output
3. Verify audio matches the text
4. Check avatar mouth animation

### Test Integration
1. Send multiple messages
2. Verify conversation history is maintained
3. Check emotion changes between messages
4. Test interruption (speak while AI is talking)

## Troubleshooting

### Chat Input Not Working
- Check if input box is active (border should be blue)
- Press Esc to toggle focus
- Click on the input box

### Typewriter Effect Not Showing
- Check if AI response is being generated (see CLI logs)
- Verify `current_response` is being passed to `chat_ui.update()`
- Check for errors in the console

### Messages Not Appearing
- Verify `chat_ui.draw()` is being called
- Check if messages are being added to `chat_ui.messages`
- Look for errors in the drawing code

### Audio Not Playing
- Check TTS model is loaded (see CLI logs)
- Verify audio device is working
- Check if `_speak()` is being called

## Future Enhancements

Potential improvements:
1. **Scrollable message history**: For longer conversations
2. **Message timestamps**: Show when each message was sent
3. **Emotion indicators**: Show emotion emoji next to AI messages
4. **Voice input toggle**: Button to enable/disable voice input
5. **Clear chat**: Button to clear message history
6. **Export chat**: Save conversation to file
7. **Multi-line input**: Support for longer messages with Shift+Enter

## Summary

The chat interface provides a convenient way to test the AI VTuber's LLM and TTS capabilities without needing to speak. The typewriter effect adds a natural feel to the AI responses, while the full text is always available in the debug logs for verification.
