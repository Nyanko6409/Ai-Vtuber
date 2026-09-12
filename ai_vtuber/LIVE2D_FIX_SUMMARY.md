# Live2D SIGSEGV Fix - Summary

## Problem

The AI VTuber application crashes with SIGSEGV (segmentation fault) when attempting to load Live2D models.

**Key observation:**
- Application runs Python 3.11.16
- Live2D native output reports Python 3.12.3
- This indicates a Python/native ABI mismatch

## Root Cause Analysis

The most likely cause is that the `live2d-py` package was installed with native extensions (.so files) compiled for Python 3.12, but the application is running Python 3.11. This causes:

1. **ABI Incompatibility**: The Python C API structures differ between versions
2. **Memory Layout Differences**: Internal structures have different sizes/offsets
3. **Function Signature Changes**: Some functions may have changed between Python 3.11 and 3.12

When the native code tries to interact with Python 3.11 using Python 3.12 assumptions, it accesses invalid memory → SIGSEGV.

## Diagnostic Tools Created

Five diagnostic scripts have been created to identify the exact issue:

### 1. test_live2d_diagnose.py
Inspects the installed live2d-py package:
- Package location and version
- Native library files (.so/.pyd)
- Available modules (v2/v3)

### 2. test_model_verify.py
Verifies all model files exist:
- Reads ganyu.model3.json
- Checks all referenced textures, motions, expressions
- Reports missing files

### 3. test_opengl_check.py
Verifies OpenGL/WSL compatibility:
- Creates OpenGL context
- Checks OpenGL version and capabilities
- Tests basic OpenGL operations

### 4. test_python_compat.py
**Most important for this issue** - Checks Python/native compatibility:
- Current Python version and executable
- Native extension file names (looking for cp311/cp312 markers)
- Python version strings embedded in .so binaries
- Package location vs current environment

### 5. test_live2d_standalone.py
Isolates each Live2D operation to find where SIGSEGV occurs:
1. Pygame context creation
2. Live2D initialization
3. Model file loading
4. OpenGL renderer initialization
5. LAppModel creation
6. Model loading
7. Model resize
8. Model update
9. Model render
10. Sustained rendering

## Code Changes Made

### avatar/live2d.py

**Added Python compatibility check:**
```python
def _check_python_compatibility() -> bool:
    """Check if live2d-py is compatible with current Python version."""
    # Reads native .so file to detect Python version markers
    # Returns False if mismatch detected
```

**Enhanced error handling:**
- Catches both `Exception` and `BaseException` (to handle SIGSEGV-related errors)
- Stores error messages for display
- Prevents initialization if Python mismatch detected
- Provides clear error messages

**Added error_message property:**
```python
@property
def error_message(self) -> Optional[str]:
    """Get error message if initialization failed."""
    return self._error_message
```

### main.py

**Updated to display Live2D errors:**
```python
live2d_error = None
if app._avatar:
    success = app.avatar.init_gl()
    if success:
        app.avatar.resize(ui.width, ui.height)
    else:
        live2d_error = app.avatar.error_message or "Live2D initialization failed"
```

**Passes error to UI:**
```python
error_msg = status.get("error") or live2d_error
ui.draw_overlay(status, error_msg)
```

### ui/pygame_ui.py

**Enhanced error display:**
- Handles multi-line error messages
- Larger error box (3/4 width instead of 1/2)
- Shows up to 6 lines of error text
- More prominent warning icon

## How to Diagnose and Fix

### Step 1: Run Diagnostic Scripts

```bash
cd ai_vtuber
python test_python_compat.py
```

**Expected output if Python mismatch:**
```
[Native Extension Files]
Linux .so files found:
  /path/to/live2d/v3.cpython-312-x86_64-linux-gnu.so
    → Built for Python 3.12

[Native Module Python Version Detection]
Checking: v3.cpython-312-x86_64-linux-gnu.so
  Found Python version strings:
    python3.12
```

### Step 2: Run Standalone Test

```bash
python test_live2d_standalone.py
```

**Expected behavior:**
- If Python mismatch: Crashes with SIGSEGV during test [2] or [4]
- If OpenGL issue: Fails at test [1] or [4] with Python exception
- If model issue: Fails at test [3] or [5] with Python exception

### Step 3: Fix the Issue

**Option A: Install correct live2d-py for Python 3.11**

Check PyPI for Python 3.11 wheel:
```bash
pip uninstall live2d-py
pip install live2d-py==0.7.0.4
```

If no Python 3.11 wheel on PyPI, download from GitHub:
```bash
pip install https://github.com/EasyLive2D/live2d-py/releases/download/v0.7.0.4/live2d_py-0.7.0.4-cp311-cp311-linux_x86_64.whl
```

**Option B: Use Python 3.12**

```bash
# Install Python 3.12
sudo apt install python3.12 python3.12-venv

# Create new venv
python3.12 -m venv venv312
source venv312/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

**Option C: Build from source**

```bash
git clone https://github.com/EasyLive2D/live2d-py.git
cd live2d-py
pip install .
```

### Step 4: Verify Fix

```bash
# Run standalone test
python test_live2d_standalone.py

# Should show all tests passing:
# [1] Pygame context: OK
# [2] Live2D initialization: OK
# [3] Model loading: OK
# [4] Renderer initialization: OK
# [5] Model creation and loading: OK
# [6] Model resize: OK
# [7] Model update: OK
# [8] Model render: OK
# [9] Sustained rendering: OK
# [10] Cleanup: OK

# Run main application
python main.py --debug
```

## Safety Improvements

The updated code now:

1. **Detects Python mismatch early** - Before attempting to load models
2. **Prevents SIGSEGV** - Skips Live2D initialization if mismatch detected
3. **Shows clear errors** - Displays error message in UI instead of black screen
4. **Allows app to continue** - UI works even if Live2D fails
5. **Provides diagnostic info** - Clear messages about what went wrong

## Files Modified

1. `ai_vtuber/avatar/live2d.py` - Added compatibility check and error handling
2. `ai_vtuber/main.py` - Display Live2D errors in UI
3. `ai_vtuber/ui/pygame_ui.py` - Enhanced error display

## Files Created

1. `ai_vtuber/test_live2d_diagnose.py` - Package inspection
2. `ai_vtuber/test_model_verify.py` - Model file verification
3. `ai_vtuber/test_opengl_check.py` - OpenGL/WSL check
4. `ai_vtuber/test_python_compat.py` - Python/native compatibility check
5. `ai_vtuber/test_live2d_standalone.py` - Isolated Live2D test
6. `ai_vtuber/TESTING_LIVE2D.md` - Testing documentation
7. `ai_vtuber/LIVE2D_FIX_SUMMARY.md` - This file

## Next Steps

1. Run `python test_python_compat.py` to confirm the diagnosis
2. Run `python test_live2d_standalone.py` to see where it crashes
3. Apply the appropriate fix (install correct version or upgrade Python)
4. Verify with standalone test
5. Run main application

## Notes

- The application will now show a clear error message instead of crashing silently
- The UI remains functional even if Live2D cannot load
- All diagnostic tools can be run independently
- The fix is minimal and focused on the Live2D system only
- No changes to STT, TTS, LLM, or other systems
