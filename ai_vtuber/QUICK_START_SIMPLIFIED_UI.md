# Quick Start - Simplified UI

## What Changed?

The UI has been **dramatically simplified** to focus on the Live2D avatar:

✅ **Avatar is now the main focus** (90% of the window)  
✅ **Removed chat history display** from Pygame window  
✅ **Removed transcription/response panels**  
✅ **Compact error notifications** instead of huge panels  
✅ **Smaller input box** at the bottom  

## New Layout

```
┌──────────────────────────────────────────┐
│ ● IDLE - Waiting for speech     FPS: 30 │  <- Status (30px)
│                                          │
│                                          │
│              LIVE2D AVATAR              │  <- Avatar (main focus!)
│                                          │
│                                          │
│                                          │
│                                          │
│ ┌──────────────────────────────────────┐ │
│ │ Type a message... (Enter to send)   │ │  <- Input (35px)
│ └──────────────────────────────────────┘ │
└──────────────────────────────────────────┘
```

## How to Use

### 1. Start the Application
```bash
cd ai_vtuber
python main.py --debug
```

### 2. Type a Message
- Click on the input box at the bottom (or it's already active)
- Type your message
- Press **Enter** to send

### 3. Watch the Avatar
- The Live2D avatar is now the main focus
- It responds with expressions and voice
- All conversation text is logged in the terminal

### 4. Check the Terminal
All conversation is logged to the CLI:
```
[core.app] INFO: Chat input: hello
[core.app] INFO: AI response: [happy] Hi there! How can I help you?
```

## Controls

| Key | Action |
|-----|--------|
| **Enter** | Send message |
| **Backspace** | Delete character |
| **Tab** | Toggle input box visibility |
| **ESC** | Quit application |
| **F** | Toggle FPS display |
| **D** | Toggle debug info |

## Buttons

- 💬 **Toggle button** - Show/hide input box
- ✖ **Clear button** - Clear input text

## What's Different?

### Removed from Pygame Window
- ❌ Chat history ("You:" / "AI:" messages)
- ❌ Transcription display
- ❌ Response display
- ❌ Large error panels
- ❌ Hint text

### Still Available
- ✅ Text input (smaller, cleaner)
- ✅ Status bar (smaller)
- ✅ FPS counter
- ✅ Error notifications (compact)
- ✅ All keyboard shortcuts
- ✅ All buttons

### Where to Find Conversation
All conversation text is now in the **terminal/CLI**:
```bash
# You'll see:
19:36:17 [ai_vtuber] INFO: Chat input: hello
19:36:43 [core.app] INFO: AI response: [happy] Hi there! 😊
```

## Benefits

1. **Clean interface** - No clutter
2. **Avatar focus** - Character is the star
3. **Professional look** - Minimal, elegant design
4. **Better performance** - Less rendering overhead
5. **Full conversation log** - Everything in terminal

## Example Session

### Terminal Output
```bash
$ python main.py --debug

19:36:08 [ai_vtuber] INFO: Entering main loop
19:36:17 [ai_vtuber] INFO: Chat input: hello
19:36:17 [core.app] INFO: Processing chat message: hello
19:36:43 [core.app] INFO: AI response: [happy] Hi there! 😊 Thanks for stopping by!
19:36:46 [tts.kitten] INFO: Generating TTS for: Hi there! 😊 Thanks...
19:36:50 [tts.kitten] INFO: TTS generated: 306000 samples
```

### Pygame Window
- Clean window with avatar centered
- Small status bar at top
- Small input box at bottom
- Avatar responds with expressions and voice

## Troubleshooting

### Input Box Not Visible?
- Press **Tab** to toggle visibility
- Click where the input box should be

### Can't Type?
- Make sure input box is active (blue border)
- Press **Tab** to activate it
- Click on the input area

### Want to See Conversation?
- Check the terminal/CLI window
- All text is logged there
- Use `--debug` flag for detailed logs

### Error Messages?
- Errors now appear as compact bar at top
- Full error details in terminal
- Doesn't cover the avatar anymore

## Summary

**Before:** Cluttered UI with avatar barely visible  
**After:** Clean, avatar-focused interface

The Live2D avatar is now the star of the show, with a minimal, professional UI that stays out of the way!
