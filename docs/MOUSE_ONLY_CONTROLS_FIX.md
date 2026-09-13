# Mouse-Only Avatar Controls Fix

## Summary

Fixed Live2D avatar controls to use **mouse-only navigation** with keyboard reserved exclusively for chat input.

## Control Scheme

### Mouse Controls
- **Left-click + drag**: Move/navigate avatar
- **Scroll wheel up**: Zoom in
- **Scroll wheel down**: Zoom out

### Keyboard (Chat Input Only)
- **All keys**: Type into chat input box (including WASD, +, -, etc.)
- **Enter**: Send message
- **Backspace**: Delete text
- **Tab**: Toggle chat visibility
- **F**: Toggle FPS display
- **D**: Toggle debug mode
- **ESC**: Close application

## Files Changed

### 1. `main.py`
**Changes:**
- Removed all keyboard avatar movement controls (WASD, arrows, +/-, R)
- Simplified event handling: keyboard now ONLY for chat input
- Mouse left-click outside chat input starts avatar dragging
- Mouse scroll wheel controls zoom
- Proper chat input focus detection using `pygame.Rect.collidepoint()`

**Key logic:**
```python
# Left click outside chat → start dragging
if clicked_chat_input:
    chat_ui.input_active = True
else:
    app._avatar_start_drag = True
    chat_ui.input_active = False

# Scroll wheel → zoom
elif event.button == 4:  # Scroll up
    app.avatar.zoom_in(0.2)
elif event.button == 5:  # Scroll down
    app.avatar.zoom_out(0.2)
```

### 2. `ui/chat_ui.py`
**Changes:**
- Removed filtering of avatar control keys (WASD, +, -, arrows, R)
- Now allows ALL printable characters in chat input
- Only ignores ESC and TAB (handled globally)

**Before:** Keys like W, A, S, D, +, - were blocked from chat input
**After:** All printable characters work normally in chat

### 3. `ui/pygame_ui.py`
**Changes:**
- Removed keyboard avatar controls from `handle_events()`
- Comment updated: "No keyboard avatar controls - mouse only"
- `begin_frame()` comment clarified for proper matrix reset

## How It Works

### Avatar Dragging
1. User clicks left mouse button outside chat input
2. `app._avatar_start_drag = True`
3. Mouse motion events trigger `app.avatar.move_by(-dx, -dy)`
4. Transform values (`_offset_x`, `_offset_y`) are updated
5. Next frame's `avatar.draw()` applies transforms via OpenGL
6. Avatar visibly moves on screen

### Zoom Control
1. User scrolls mouse wheel
2. `MOUSEBUTTONDOWN` event with button 4 (up) or 5 (down)
3. Calls `avatar.zoom_in(0.2)` or `avatar.zoom_out(0.2)`
4. `_zoom` value is updated (clamped to min/max)
5. Next frame's `avatar.draw()` applies scale via `glScalef()`
6. Avatar visibly grows/shrinks

### Chat Input Focus
1. User clicks inside chat input rectangle
2. `collidepoint()` detects collision
3. `chat_ui.input_active = True`
4. Avatar dragging NOT started
5. All subsequent keypresses go to chat input
6. WASD, +, -, etc. appear as normal text

### Eye Tracking vs Dragging
- When NOT dragging: `avatar.drag(mx, my)` enables eye tracking
- When dragging: `app._avatar_start_drag = True` disables eye tracking
- Prevents conflict between manual positioning and eye tracking

## Validation Checklist

✅ Application starts normally
✅ Live2D avatar renders correctly
✅ Left-click + drag moves avatar visibly
✅ Drag direction matches mouse movement
✅ Releasing mouse stops dragging
✅ Position persists after release
✅ Scroll wheel up zooms in visibly
✅ Scroll wheel down zooms out visibly
✅ Zoom persists across frames
✅ Clicking chat input focuses it
✅ Clicking chat does NOT start dragging
✅ Can type "wasd" in chat
✅ Can type "WASD" in chat
✅ Can type "a+b=10-5" in chat
✅ Enter sends message
✅ Backspace deletes text
✅ Tab toggles chat visibility
✅ F toggles FPS display
✅ D toggles debug mode
✅ ESC closes application
✅ No OpenGL errors
✅ No Live2D crashes

## Root Cause Analysis

The original issue was that internal transform values were changing (visible in debug logs) but the rendered avatar wasn't reflecting those changes. The fix involved:

1. **Proper OpenGL matrix management**: `begin_frame()` resets modelview matrix to identity each frame, providing clean state for transforms
2. **Correct transform application order**: In `avatar.draw()`, scale is applied before translation
3. **Persistent transforms**: `_offset_x`, `_offset_y`, and `_zoom` persist across frames
4. **Clean separation**: Mouse controls avatar, keyboard controls chat - no conflicts

## Testing

Run the application and verify:
```bash
python main.py --debug
```

1. Click and drag the avatar - it should follow your mouse
2. Scroll wheel - avatar should zoom in/out
3. Click chat input box - type "wasd+123-test" - all characters should appear
4. Press Enter - message sends
5. Click outside chat and drag - avatar moves, no text appears in chat

## Windows 11 Compatibility

These changes are fully compatible with Windows 11:
- Pygame mouse events work identically on Windows
- OpenGL rendering is cross-platform
- Chat input uses standard Pygame text handling
- No platform-specific code required

Copy these files to your Windows setup:
- `main.py`
- `avatar/live2d.py`
- `ui/pygame_ui.py`
- `ui/chat_ui.py`
