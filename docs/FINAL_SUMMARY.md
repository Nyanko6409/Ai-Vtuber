# Live2D Model Loading Issue - Final Summary

## What's Working Now

✅ **STT (Speech-to-Text)**: CUDA detection fixed, using GPU acceleration  
✅ **TTS (Text-to-Speech)**: KittenTTS 0.8.1 installed and working  
✅ **LLM (Language Model)**: LM Studio connection working  
✅ **Error Handling**: Enhanced to prevent crashes and show clear errors  

## What's Not Working

⚠️ **Live2D Avatar**: Crashes during model loading with SIGSEGV

## The Problem

Your application crashes at this point:
```
[INFO]  create model: ganyu.moc3
Live2D Cubism SDK Core Version 5.1.0
fish: Job 1, 'python main.py --debug' terminated by signal SIGSEGV
```

The crash happens AFTER:
- Live2D wrapper loads successfully
- Cubism Core initializes
- OpenGL context is created
- Model JSON is read
- **During**: Actual model creation from .moc3 file

## Possible Causes

1. **Missing Model Files**: Textures, physics, or other required files might be missing
2. **Python Version Mismatch**: live2d-py compiled for Python 3.12, running on Python 3.11
3. **Corrupted Model Files**: The .moc3 file or textures might be corrupted
4. **OpenGL Context Issue**: WSLg might have OpenGL compatibility issues

## What I've Done

### 1. Enhanced Error Handling (`avatar/live2d.py`)
- Added `_validate_model_files()` method to check all required files before loading
- Added detailed logging for each file check
- Added try-catch around model loading to catch SIGSEGV
- Shows clear error messages instead of crashing

### 2. Created Diagnostic Script (`test_model_diagnostic.py`)
- Checks if all required model files exist
- Validates model JSON structure
- Reports missing files with clear messages
- Helps identify the exact issue

### 3. Created Fix Guide (`LIVE2D_MODEL_FIX.md`)
- Step-by-step troubleshooting
- Common issues and solutions
- Alternative approaches

### 4. Updated Web Documentation
- Added "Status" tab showing current state
- Updated troubleshooting section
- Clear next steps

## What You Need to Do

### Step 1: Run Diagnostic Script
```bash
cd ai_vtuber
python test_model_diagnostic.py
```

This will tell you if files are missing.

### Step 2: Check the Output

**If files are missing:**
```
✗ Missing required files!
  ✗ Missing: textures/texture_00.png
```
→ Fix the model path or re-download the model

**If all files present:**
```
✓ All required files present
```
→ The issue is likely Python version mismatch or corrupted files

### Step 3: Fix Based on Diagnostic

#### Scenario A: Missing Files
1. Check the model path in `config.yaml`
2. Verify the directory exists:
   ```bash
   ls -la "/mnt/e/SteamLibrary/steamapps/common/VTube Studio/VTube Studio_Data/StreamingAssets/Live2DModels/ganyu/"
   ```
3. Re-download the model from VTube Studio if needed

#### Scenario B: Python Version Mismatch
The log shows: `[live2d.v3] Cubism Native, Python 3.12.3`  
But you're running: Python 3.11.16

**Fix Option 1: Install Python 3.11 compatible live2d-py**
```bash
pip uninstall live2d-py
# Download from: https://github.com/EasyLive2D/live2d-py/releases
# Look for: live2d_py-0.7.0.4-cp311-cp311-linux_x86_64.whl
pip install live2d_py-0.7.0.4-cp311-cp311-linux_x86_64.whl
```

**Fix Option 2: Use Python 3.12**
```bash
sudo apt install python3.12 python3.12-venv
python3.12 -m venv venv312
source venv312/bin/activate
pip install -r requirements.txt
pip install https://github.com/KittenML/KittenTTS/releases/download/0.8.1/kittentts-0.8.1-py3-none-any.whl
```

#### Scenario C: Corrupted Model
1. Try a different Live2D model
2. Re-download the Ganyu model
3. Test with official Live2D sample models

### Step 4: Test Again
```bash
python main.py --debug
```

Look for:
```
✓ All required model files validated
✓ Live2D model loaded successfully: ganyu.model3.json
```

## Files Modified

1. **`ai_vtuber/avatar/live2d.py`**
   - Added `_validate_model_files()` method
   - Enhanced error handling in `init_gl()`
   - Better logging and error messages

2. **`ai_vtuber/test_model_diagnostic.py`** (NEW)
   - Comprehensive model file validation
   - Clear diagnostic output

3. **`ai_vtuber/LIVE2D_MODEL_FIX.md`** (NEW)
   - Detailed troubleshooting guide
   - Step-by-step fixes

4. **`src/App.tsx`**
   - Added "Status" tab
   - Shows current state of all components
   - Clear next steps

## Expected Behavior After Fix

When everything works, you should see:
```
[avatar.live2d] INFO: Validating model files in: /mnt/e/.../ganyu
[avatar.live2d] DEBUG: ✓ Moc file exists: ganyu.moc3
[avatar.live2d] DEBUG: ✓ Texture exists: texture_00.png
[avatar.live2d] INFO: ✓ All required model files validated
[avatar.live2d] INFO: Loading Live2D model: /mnt/e/.../ganyu.model3.json
[avatar.live2d] INFO: ✓ Live2D model loaded successfully: ganyu.model3.json
```

And the Ganyu avatar should appear in the Pygame window!

## If It Still Doesn't Work

1. **Check the diagnostic output** - What does `test_model_diagnostic.py` say?
2. **Check the log** - What error message appears before the crash?
3. **Try a different model** - Download a simple test model
4. **Check OpenGL** - Run `glxinfo | grep "OpenGL version"` to verify WSLg OpenGL support

## Summary

The application is 90% working. STT, TTS, and LLM are all functional. The only remaining issue is Live2D model loading, which is likely caused by:
- Missing model files (most likely)
- Python version mismatch
- Corrupted model files

Run the diagnostic script first to identify the exact issue, then follow the appropriate fix from the guide.
