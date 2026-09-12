# Quick Start Guide - Chat Interface

## What's New

Your AI VTuber now has a **text chat interface** at the bottom of the window! You can type messages to test the LLM and TTS without speaking.

## How to Use

### 1. Start the Application
```bash
cd ai_vtuber
python main.py --debug
```

### 2. Type a Message
- The chat input box is at the bottom (blue border = active)
- Type your message: "Hello! How are you today?"
- Press **Enter** to send

### 3. Watch the AI Respond
- **Text**: AI response appears with typewriter effect (character by character)
- **Voice**: AI speaks the response using KittenTTS
- **Avatar**: Live2D model shows matching emotion and lip sync
- **Debug**: Full conversation logged in CLI

### 4. Toggle Chat Focus
- Press **Tab** to switch between chat mode and normal mode
- **Chat mode** (blue border): All typing goes to chat input
- **Normal mode**: Keyboard shortcuts work (ESC to quit, F for FPS, D for debug)

## Keyboard Shortcuts

| Key | Action | When |
|-----|--------|------|
| **Enter** | Send message | Chat active |
| **Backspace** | Delete character | Chat active |
| **Tab** | Toggle chat focus | Always |
| **ESC** | Quit application | Chat inactive |
| **F** | Toggle FPS display | Chat inactive |
| **D** | Toggle debug info | Chat inactive |

## Example Conversation

```
You: Hello! How are you today?
AI: [happy] I'm doing wonderful, thanks for asking! It's great to chat with you!

You: What's your favorite color?
AI: [thinking] Hmm, I'd say purple! It feels creative and mysterious.

You: Tell me a joke!
AI: [excited] Why don't scientists trust atoms? Because they make up everything!
```

## Testing the Full Pipeline

### Test LLM (Language Model)
1. Type a message in chat
2. Check CLI for: `[core.app] INFO: Chat message: ...`
3. Check CLI for: `[core.app] INFO: AI response: [emotion] ...`

### Test TTS (Text-to-Speech)
1. Send a message
2. Listen for audio output
3. Watch avatar mouth animate during speech

### Test Emotions
1. Send different types of messages
2. Watch avatar expression change
3. Check emotion tag in CLI: `[happy]`, `[sad]`, `[thinking]`, etc.

### Test Voice Input (Still Works!)
1. Press **Tab** to deactivate chat
2. Speak into microphone
3. AI responds with voice and text

## Troubleshooting

### Chat Input Not Responding
- Check if blue border is visible (chat is active)
- Press **Tab** to toggle focus
- Click on the input box

### No AI Response
- Check CLI for errors
- Verify LM Studio is running
- Check if message was sent: `[core.app] INFO: Chat message: ...`

### No Audio
- Check TTS model loaded: `[tts.kitten] INFO: KittenTTS 0.8.x loaded`
- Verify audio output device
- Check volume levels

### Typewriter Effect Not Showing
- Check if response is being generated (see CLI)
- Verify `chat_ui.update()` is being called
- Look for errors in console

## Debug Output

All chat activity is logged:
```
19:20:54 [core.app] INFO: Chat message: Hello!
19:20:55 [core.app] INFO: AI response: [happy] Hi there! How can I help you?
19:20:55 [tts.kitten] INFO: Generating TTS for: Hi there! How can I help you?...
19:20:56 [audio.playback] INFO: Playing audio...
```

## Tips

1. **Keep messages short** - AI responds better to concise inputs
2. **Watch the avatar** - Emotions change based on AI's mood
3. **Use voice too** - Chat and voice input work together
4. **Check CLI** - Full conversation history is logged
5. **Press Tab** - Quickly switch between chat and shortcuts

## What's Working

✅ **LM Studio** - Connected and responding  
✅ **KittenTTS** - Voice synthesis working  
✅ **Live2D Avatar** - Ganyu model loaded successfully  
✅ **Chat Interface** - Text input with typewriter effect  
✅ **Voice Input** - Microphone still active  
✅ **Emotion System** - Avatar expressions change  
✅ **CUDA Acceleration** - GPU acceleration for STT  

## Next Steps

1. Try different conversation topics
2. Test emotion variations
3. Compare voice vs text input
4. Experiment with different prompts
5. Have fun chatting with your AI VTuber!

---

**Note**: The full conversation is always logged in the CLI debug output, so you can review everything even if you miss it in the UI.
