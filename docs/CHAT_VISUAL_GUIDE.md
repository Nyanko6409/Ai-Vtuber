# Chat Interface - Visual Guide

## Button Layout

```
┌─────────────────────────────────────────────────────────┐
│                                                          │
│                    Live2D Avatar                          │
│                                                          │
│                                                          │
│                                                          │
│                                                          │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Message History                                  │   │
│  │  You: Hello! How are you?                         │   │
│  │  AI: I'm doing great, thanks for asking!         │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Type a message... (Enter to send)          [✖][💬]│   │
│  │  Press Enter to send | Tab to toggle chat         │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
└─────────────────────────────────────────────────────────┘
                                              ↑    ↑
                                           Clear  Toggle
                                          Button  Button
```

## Button States

### Toggle Button (💬)

**When Chat is Visible:**
```
┌──────┐
│  💬  │  ← Blue background (active)
└──────┘
```

**When Chat is Hidden:**
```
┌──────┐
│  💬  │  ← Gray background (inactive)
└──────┘
```

**On Hover:**
```
┌──────┐
│  💬  │  ← Lighter background (hover effect)
└──────┘
```

### Clear Button (✖)

**Normal State:**
```
┌──────┐
│  ✖   │  ← Gray background
└──────┘
```

**On Hover:**
```
┌──────┐
│  ✖   │  ← Lighter background (hover effect)
└──────┘
```

**Note:** Clear button only appears when chat is visible

## Interaction Flow

### Toggling Chat Visibility

```
Step 1: Chat is visible
┌─────────────────────┐
│  Chat Interface     │
│  [Messages...]      │
│  [Input box]   [💬] │  ← Blue button
└─────────────────────┘

Step 2: Click toggle button
         ↓
Step 3: Chat hides
┌─────────────────────┐
│                     │
│   (Avatar only)     │
│                     │
│                [💬] │  ← Gray button
└─────────────────────┘

Step 4: Click toggle button again
         ↓
Step 5: Chat reappears
┌─────────────────────┐
│  Chat Interface     │
│  [Messages...]      │
│  [Input box]   [💬] │  ← Blue button
└─────────────────────┘
```

### Clearing Chat History

```
Step 1: Chat has messages
┌─────────────────────┐
│  You: Hello!        │
│  AI: Hi there!      │
│  You: How are you?  │
│  [Input box]   [✖]  │  ← Clear button
└─────────────────────┘

Step 2: Click clear button
         ↓
Step 3: Chat cleared
┌─────────────────────┐
│                     │
│  (Empty)            │
│                     │
│  [Input box]   [✖]  │  ← Clear button
└─────────────────────┘
```

## Mouse Interaction

### Clicking Buttons

1. **Move mouse over button**
   - Button changes to hover color
   - Visual feedback provided

2. **Click left mouse button**
   - Action executed immediately
   - State updated
   - UI redrawn

### Typing in Chat

1. **Click on input box** (or it's already focused)
   - Blue border appears
   - Cursor blinks

2. **Type message**
   - Characters appear in input box
   - Cursor moves with text

3. **Press Enter**
   - Message sent
   - Input cleared
   - AI responds

## Keyboard Shortcuts Reference

### When Chat is Active (Input focused)

| Key | Action |
|-----|--------|
| Any letter/number | Type character |
| Backspace | Delete last character |
| Enter | Send message |
| Tab | Toggle chat visibility |

### When Chat is Inactive

| Key | Action |
|-----|--------|
| Tab | Toggle chat visibility |
| ESC | Quit application |
| F | Toggle FPS display |
| D | Toggle debug info |

## Color Scheme

### Chat Interface Colors

```
Background:     (30, 30, 40)     - Dark blue-gray
Input Box:      (40, 40, 50)     - Slightly lighter
Border:         (80, 80, 100)    - Medium gray
Active Border:  (100, 150, 255)  - Bright blue

User Text:      (100, 200, 255)  - Light blue
AI Text:        (200, 255, 150)  - Light green
Placeholder:    (150, 150, 150)  - Gray

Button Normal:  (60, 60, 80)     - Dark gray
Button Hover:   (80, 80, 110)    - Medium gray
Button Active:  (100, 150, 255)  - Bright blue
```

## Button Dimensions

```
Button Size:    30x30 pixels
Button Margin:  10 pixels from edges
Border Radius:  6 pixels (rounded corners)

Position:
- Toggle button: Bottom-right, above input box
- Clear button: Left of toggle button
- Input box: Bottom of window, full width minus margins
```

## Accessibility Features

### Visual Indicators
- **Color changes** for button states (normal, hover, active)
- **Border highlighting** for active input
- **Icon clarity** - Simple, recognizable icons
- **Contrast** - Good contrast between text and background

### Interaction Options
- **Mouse control** - Click buttons directly
- **Keyboard control** - Use Tab key as alternative
- **Focus indication** - Clear visual feedback for active elements
- **Hover feedback** - Immediate response to mouse movement

## Tips for Users

### Getting Started
1. Look for the blue 💬 button in the bottom-right
2. Click it to show/hide the chat
3. Click the input box to start typing
4. Press Enter to send your message

### Efficient Usage
- Use **Tab** key to quickly toggle chat without mouse
- Click **✖** button to start fresh conversation
- Watch for **blue border** to know when input is active
- Check **button colors** to see chat state

### Troubleshooting
- **Can't type?** → Click on input box or press Tab
- **Chat disappeared?** → Click the 💬 button
- **Want to clear?** → Click the ✖ button
- **Accidentally quit?** → Chat was active, use mouse to click ✖ instead

## Example Scenarios

### Scenario 1: Casual Conversation
```
1. Click 💬 button (if chat hidden)
2. Click input box
3. Type: "Hello! How are you today?"
4. Press Enter
5. Watch AI respond with typewriter effect
6. Listen to voice response
7. Continue conversation...
```

### Scenario 2: Quick Question
```
1. Press Tab to show chat
2. Type: "What's the weather like?"
3. Press Enter
4. Read response
5. Press Tab to hide chat (clean view)
```

### Scenario 3: Fresh Start
```
1. Have long conversation
2. Click ✖ button to clear history
3. Start new conversation
4. Clean slate, no old messages
```

### Scenario 4: Voice + Text
```
1. Speak into microphone (voice input)
2. AI responds with voice
3. Press Tab to show chat
4. Type follow-up question
5. Press Enter
6. AI responds again
7. Both input methods work together!
```

## Performance Notes

- **Button rendering**: Minimal performance impact
- **Hover detection**: Efficient collision checking
- **OpenGL texture**: Smooth rendering, no lag
- **Event handling**: Optimized for 30 FPS
- **Memory usage**: Chat history limited to 10 messages

## Summary

The chat interface provides an intuitive, visually appealing way to interact with your AI VTuber. The control buttons make it easy to manage the chat experience, while the keyboard shortcuts provide quick access for power users. The combination of mouse and keyboard controls ensures flexibility for different usage patterns.
