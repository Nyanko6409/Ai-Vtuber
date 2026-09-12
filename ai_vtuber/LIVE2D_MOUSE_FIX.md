# Live2D Mouse Controls Fix - PROJECTION Matrix Approach

## Root Cause

The avatar wasn't visibly moving/zooming because `live2d-py`'s `LAppModel.Draw()` renders using its own internal shader pipeline and **never reads the legacy OpenGL `GL_MODELVIEW` matrix stack**. 

The previous approach used:
```python
gl.glMatrixMode(gl.GL_MODELVIEW)
gl.glPushMatrix()
gl.glScalef(self._zoom, self._zoom, 1.0)
gl.glTranslatef(self._offset_x, self._offset_y, 0.0)
self._model.Draw()  # <- This ignores MODELVIEW!
gl.glPopMatrix()
```

This had **zero effect** on the rendered model.

## Solution

Apply transforms via the **PROJECTION matrix** instead, which affects how the entire scene is projected onto the screen. This is the standard approach used by VTube Studio and similar applications.

### Changed Files

#### 1. `/workspace/ai_vtuber/avatar/live2d.py` - `draw()` method

**Before:** Applied scale/translate via MODELVIEW (ignored by live2d-py)

**After:** Applies zoom/offset via custom orthographic projection:
```python
def draw(self) -> None:
    """Draw the Live2D model with zoom and position transforms."""
    if not self._initialized or not self._model:
        return
    try:
        import OpenGL.GL as gl
        
        # Get viewport dimensions
        viewport = gl.glGetIntegerv(gl.GL_VIEWPORT)
        width = viewport[2]
        height = viewport[3]
        
        # Save and reset projection matrix
        gl.glMatrixMode(gl.GL_PROJECTION)
        gl.glPushMatrix()
        gl.glLoadIdentity()
        
        # Calculate projection with zoom and offset baked in
        half_w = (width / 2.0) / self._zoom
        half_h = (height / 2.0) / self._zoom
        
        # Convert pixel offsets to normalized coordinates
        offset_x_norm = self._offset_x / (width / 2.0) * self._zoom
        offset_y_norm = self._offset_y / (height / 2.0) * self._zoom
        
        # Apply offset to projection bounds
        left = -half_w - offset_x_norm * half_w
        right = half_w - offset_x_norm * half_w
        bottom = -half_h - offset_y_norm * half_h
        top = half_h - offset_y_norm * half_h
        
        gl.glOrtho(left, right, bottom, top, -1.0, 1.0)
        
        # ModelView must be identity for Live2D
        gl.glMatrixMode(gl.GL_MODELVIEW)
        gl.glPushMatrix()
        gl.glLoadIdentity()
        
        # Draw with projection applied
        self._model.Draw()
        
        # Restore matrices
        gl.glMatrixMode(gl.GL_MODELVIEW)
        gl.glPopMatrix()
        gl.glMatrixMode(gl.GL_PROJECTION)
        gl.glPopMatrix()
        
    except ImportError:
        logger.warning("OpenGL not available, drawing without transforms")
        self._model.Draw()
    except Exception as e:
        logger.error(f"Live2D draw error: {e}")
        try:
            self._model.Draw()
        except Exception:
            pass
```

#### 2. `/workspace/ai_vtuber/ui/pygame_ui.py` - `begin_frame()` method

Added comment clarifying that transforms must persist:
```python
# NOTE: Do NOT reset avatar transforms here - they must persist across frames
# The avatar's draw() method will apply its own zoom/offset via projection matrix
```

## How It Works Now

### Mouse Drag Navigation
1. Left-click outside chat input → sets `_dragging = True`
2. Mouse moves while dragging → calls `avatar.move_by(dx, dy)` 
3. This updates `_offset_x` and `_offset_y`
4. Next frame's `draw()` applies these offsets via projection matrix
5. Avatar visibly moves on screen
6. Release mouse → stops dragging, position persists

### Mouse Wheel Zoom
1. Scroll up → calls `avatar.zoom_in(0.2)`
2. This increases `_zoom` (clamped to max 5.0)
3. Next frame's `draw()` uses new zoom in projection calculation
4. Avatar visibly grows larger
5. Scroll down → opposite effect

### Keyboard → Chat Only
- All keyboard controls for avatar removed (WASD, arrows, +/-, R)
- Keyboard is now exclusively for chat input
- You can type "wasd", "+", "-", etc. into chat normally
- No key interception - all characters work in chat

## Control Scheme

| Input | Action |
|-------|--------|
| **Left Mouse + Drag** | Move avatar |
| **Mouse Wheel Up** | Zoom in |
| **Mouse Wheel Down** | Zoom out |
| **Keyboard** | Chat text only |

## Validation Checklist

Run `python main.py --debug` and verify:

- [ ] Left-click + drag moves avatar visibly
- [ ] Avatar stays at new position after release
- [ ] Scroll wheel up makes avatar larger
- [ ] Scroll wheel down makes avatar smaller
- [ ] Zoom changes persist across frames
- [ ] Can type "wasd" in chat box
- [ ] Can type "+=" in chat box  
- [ ] Can type "-" in chat box
- [ ] Chat input focus doesn't start dragging
- [ ] No OpenGL errors in console
- [ ] No Live2D crashes

## Testing on Windows 11

Copy these files to your Windows setup:
- `avatar/live2d.py`
- `ui/pygame_ui.py`
- `main.py`
- `ui/chat_ui.py`

Then run: `python main.py --debug`

## Mathematical Explanation

For a window of size 800×600:

**Default (zoom=1.0, offset=0):**
- Projection: `glOrtho(-400, 400, -300, 300, -1, 1)`
- Center of screen maps to (0, 0) in Live2D coordinates

**Zoomed 2x (zoom=2.0, offset=0):**
- `half_w = 400 / 2.0 = 200`
- Projection: `glOrtho(-200, 200, -150, 150, -1, 1)`
- Smaller viewing area = avatar appears larger

**Offset right 100px (zoom=1.0, offset_x=100):**
- `offset_x_norm = 100 / 400 * 1.0 = 0.25`
- `left = -400 - 0.25 * 400 = -500`
- `right = 400 - 0.25 * 400 = 300`
- Projection: `glOrtho(-500, 300, -300, 300, -1, 1)`
- View shifts left, making avatar appear to move right

