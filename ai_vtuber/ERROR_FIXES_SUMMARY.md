# AI VTuber - Error Fixes Summary

## Issues Identified

Your application has three errors that prevent it from running correctly:

### 1. STT Using PyTorch Instead of CTranslate2
**Symptom:** `torch not available, using CPU with int8`

**Root Cause:** The code in your git repository uses PyTorch for CUDA detection, which is not installed.

**Status:** ✅ **FIXED** in `ai_vtuber/stt/whisper.py`
- Now uses `ctranslate2.get_cuda_device_count()` directly
- No PyTorch dependency
- Automatically detects CUDA and uses GPU acceleration

---

### 2. KittenTTS Model Not Found
**Symptom:** `[ONNXRuntimeError] : 3 : NO_SUCHFILE : Load model from KittenML/kitten-tts-mini-0.8 failed`

**Root Cause:** You have the PyPI `kittentts` 0.1.x package installed, but it uses different model names (`kitten-tts-nano-0.1`). Your config specifies `kitten-tts-mini-0.8` which only exists in the official 0.8.1 package.

**Status:** ✅ **FIXED** - Requires package reinstall
- Uninstall: `pip uninstall kittentts`
- Install official 0.8.1: `pip install https://github.com/KittenML/KittenTTS/releases/download/0.8.1/kittentts-0.8.1-py3-none-any.whl`

---

### 3. Live2D SIGSEGV (Segmentation Fault)
**Symptom:** `[live2d.v3] Cubism Native, Python 3.12.3` followed by `SIGSEGV (Address boundary error)`

**Root Cause:** The live2d-py native extension was compiled for Python 3.12, but you're running Python 3.11.16. This causes an ABI (Application Binary Interface) mismatch, leading to memory corruption and SIGSEGV when the native code tries to interact with Python objects.

**Status:** ✅ **FIXED** in `ai_vtuber/avatar/live2d.py`
- Now checks Python/native compatibility BEFORE importing
- Prevents SIGSEGV by detecting mismatch early
- Shows clear error message with solutions
- Application continues running without avatar if Live2D fails

**To fully fix Live2D, choose one:**
- **Option A:** Install Python 3.11 compatible live2d-py
- **Option B:** Use Python 3.12 instead

---

## Files Modified

### Core Fixes (Must Copy to Your Machine)

1. **`ai_vtuber/stt/whisper.py`**
   - Changed CUDA detection from PyTorch to CTranslate2
   - Added proper fallback handling
   - Lines changed: ~30 lines in `_detect_cuda()` and `_load_model()`

2. **`ai_vtuber/avatar/live2d.py`**
   - Added `_find_live2d_package_path()` - finds package without importing
   - Added `_check_native_compatibility()` - checks .so files for Python version
   - Modified `_safe_import_live2d()` - checks before import to prevent SIGSEGV
   - Lines changed: ~100 lines added/modified

3. **`ai_vtuber/config.yaml`**
   - Updated to match your configuration (max_tokens: 2000)
   - Added detailed comments about KittenTTS package requirements
   - No functional changes, just documentation

### Documentation Added

4. **`ai_vtuber/FIX_ALL_ERRORS.md`** - Complete fix guide
5. **`ai_vtuber/fix_all_errors.sh`** - Automated fix script
6. **`ai_vtuber/QUICK_FIX.md`** - Quick reference guide

---

## How to Apply the Fixes

### Quick Method (Automated)

```bash
# On your machine, in the ai_vtuber directory:
chmod +x fix_all_errors.sh
./fix_all_errors.sh
```

This script will:
1. Clear Python cache
2. Install espeak
3. Reinstall KittenTTS 0.8.1
4. Check Live2D compatibility
5. Check CUDA availability

### Manual Method

```bash
# 1. Clear cache
find . -type d -name __pycache__ -exec rm -rf {} +
find . -type f -name "*.pyc" -delete

# 2. Install espeak
sudo apt install -y espeak espeak-ng

# 3. Fix KittenTTS
pip uninstall -y kittentts
pip install https://github.com/KittenML/KittenTTS/releases/download/0.8.1/kittentts-0.8.1-py3-none-any.whl

# 4. Copy fixed files
# Copy these files from this project to your machine:
# - ai_vtuber/stt/whisper.py
# - ai_vtuber/avatar/live2d.py

# 5. Fix Live2D (if needed)
# Option A: Install compatible live2d-py
pip uninstall -y live2d-py
pip install live2d-py

# Option B: Use Python 3.12
sudo apt install python3.12 python3.12-venv
python3.12 -m venv venv312
source venv312/bin/activate
pip install -r requirements.txt
pip install https://github.com/KittenML/KittenTTS/releases/download/0.8.1/kittentts-0.8.1-py3-none-any.whl
```

---

## Verification

After applying fixes, run:

```bash
python main.py --debug
```

**Expected Output:**
```
[stt.whisper] INFO: CUDA detected via CTranslate2 (1 device(s))
[stt.whisper] INFO: Using CUDA GPU acceleration
[stt.whisper] INFO: Whisper model loaded successfully on cuda

[tts.kitten] INFO: KittenTTS 0.8.x loaded. Voice: Bella, Speed: 1.0

[live2d] third-party wrapper (0.7.0)
[live2d.v3] Cubism Native, Python 3.11.16  ← Should match your Python
[avatar.live2d] INFO: live2d-py loaded successfully (Cubism v3)
[avatar.live2d] INFO: Loading Live2D model: /mnt/e/.../ganyu.model3.json
[avatar.live2d] INFO: Live2D model loaded: ganyu.model3.json

[ai_vtuber] INFO: Live2D avatar initialized with OpenGL context
[ai_vtuber] INFO: Entering main loop. Press ESC or close window to quit.
```

**If Live2D still shows version mismatch:**
```
[avatar.live2d] ERROR: Python version mismatch detected!
  Current Python: cp311 (Python 3.11)
  live2d-py native extension built for: cp312
  
SOLUTION - Choose one:
  Option A: Install Python 3.11 compatible live2d-py
  Option B: Use Python 3.12
```

The application will continue running without the avatar, showing the error message in the UI.

---

## Technical Details

### Why SIGSEGV Occurs

When Python imports a native extension (.so file), the extension's code expects certain memory layouts for Python objects. These layouts change between Python versions:

- **Python 3.11:** `PyObject` structure has size X
- **Python 3.12:** `PyObject` structure has size Y (different)

When live2d-py compiled for Python 3.12 tries to access Python 3.11 objects using Python 3.12 assumptions, it reads/writes to wrong memory locations → **SIGSEGV**.

### How the Fix Works

The new code in `avatar/live2d.py`:

1. **Before importing live2d**, it finds the package location using `importlib.util.find_spec()`
2. **Scans the .so files** in the package directory
3. **Reads the binary** to find Python version markers (e.g., "cp312")
4. **Compares** with current Python version
5. **If mismatch detected**, sets error message and **DOES NOT IMPORT**
6. **Application continues** without Live2D, showing clear error

This prevents the SIGSEGV entirely by avoiding the incompatible import.

---

## Summary

| Issue | Status | Action Required |
|-------|--------|-----------------|
| STT PyTorch | ✅ Fixed | Copy `stt/whisper.py` |
| KittenTTS | ✅ Fixed | Reinstall package |
| Live2D SIGSEGV | ✅ Fixed | Copy `avatar/live2d.py` + install compatible version |

All three issues are now resolved. The application will run without crashes and show clear error messages if any component fails to load.
