# Live2D Mouse Controls Fix - VTube Studio Style Navigation

## Problem
Mouse and keyboard controls were changing internal transform values (zoom, offset_x, offset_y) but the rendered avatar was not visibly reflecting these changes.

## Root Cause
The OpenGL matrix management was incorrect:
1. The `draw()` method was using `GL_MODELVIEW` matrix instead of `GL_PROJECTION`
2. The `begin_frame()` method wasn't setting up a proper projection matrix for Live2D rendering
3. Live2D's `LAppModel.Draw()` internally manages its own modelview matrix, so our transforms were being reset

## Solution

### 1. Modified `avatar/live2d.py` - draw() method
Changed from using GL_MODELVIEW to GL_PROJECTION matrix for transforms:
- Save projection matrix state with `glPushMatrix()`
- Apply zoom (scale) first: `glScalef(self._zoom, self._zoom, 1.0)`
- Apply position (translation): `glTranslatef(offset_x/zoom, offset_y/zoom, 0.0)`
- Draw the model
- Restore projection matrix with `glPopMatrix()`

This approach is similar to VTube Studio's camera control system.

### 2. Modified `ui/pygame_ui.py` - begin_frame() method
Set up proper orthographic projection matching window coordinates:
```python
GL.glOrtho(-self.width/2, self.width/2, -self.height/2, self.height/2, -1000, 1000)
```
This creates a coordinate system where:
- Center of screen is (0, 0)
- X ranges from -width/2 to +width/2
- Y ranges from -height/2 to +height/2

## How It Works Now

### Mouse Controls
- **Left-click + drag**: Moves avatar by delta mouse movement
  - Uses `move_by(dx, dy)` which updates `_offset_x` and `_offset_y`
  - Eye tracking is disabled while dragging
  - Movement persists after releasing mouse
  
- **Mouse wheel scroll**: Zooms in/out
  - Scroll up: `zoom_in(0.2)` - increases zoom level
  - Scroll down: `zoom_out(0.2)` - decreases zoom level
  - Zoom persists across frames

### Keyboard Controls (always work, even when chat is focused)
- **W/Arrow Up**: Move avatar up 20 units
- **S/Arrow Down**: Move avatar down 20 units  
- **A/Arrow Left**: Move avatar left 20 units
- **D/Arrow Right**: Move avatar right 20 units
- **+/- or =**: Zoom in/out
- **R**: Reset zoom and position to defaults

### Chat Input Integration
- Clicking chat input box focuses it (doesn't start dragging)
- Avatar control keys (WASD, arrows, +/-, R) are filtered out and never inserted into chat
- Normal typing still works in chat input
- Enter sends message, Backspace deletes text

## Files Changed
1. `/workspace/ai_vtuber/avatar/live2d.py` - draw() method now uses GL_PROJECTION
2. `/workspace/ai_vtuber/ui/pygame_ui.py` - begin_frame() sets up proper orthographic projection
3. `/workspace/ai_vtuber/main.py` - Event handling already correct (from previous fixes)
4. `/workspace/ai_vtuber/ui/chat_ui.py` - Key filtering already correct (from previous fixes)

## Testing On Windows 11
Copy these files to your Windows setup:
- `avatar/live2d.py`
- `ui/pygame_ui.py`
- `main.py`
- `ui/chat_ui.py`

Then run: `python main.py --debug`

Test all controls:
✓ Mouse wheel zooms avatar in/out visibly
✓ Left-click drag moves avatar visibly
✓ WASD/arrow keys move avatar
✓ +/- zoom, R resets
✓ Chat input can be typed in while avatar controls still work
