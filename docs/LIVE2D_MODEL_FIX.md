# Live2D Model Loading Fix Guide

## Current Issue

Your application is crashing with SIGSEGV during Live2D model loading. The crash happens AFTER:
- ✓ Live2D wrapper loads successfully
- ✓ Cubism Core initializes
- ✓ OpenGL context is created
- ✗ Model loading starts → **CRASH**

This indicates the issue is with the model files or how they're being loaded.

## Step 1: Run Diagnostic Script

First, let's check if all model files are present:

```bash
cd ai_vtuber
python test_model_diagnostic.py
```

This will check:
- ✓ Model JSON file exists
- ✓ Moc3 file (3D model data) exists
- ✓ All texture files exist
- ✓ Physics, pose, motions, expressions (optional)

**Expected output:**
```
✓ All required files present
```

If files are missing, you'll see:
```
✗ Missing required files!
  ✗ Missing: textures/texture_00.png
```

## Step 2: Common Issues and Fixes

### Issue A: Missing Model Files

**Symptom:** Diagnostic shows missing files

**Fix:** 
1. Check the model path in `config.yaml`:
   ```yaml
   avatar:
     model_path: "/mnt/e/SteamLibrary/steamapps/common/VTube Studio/VTube Studio_Data/StreamingAssets/Live2DModels/ganyu/ganyu.model3.json"
   ```

2. Verify the directory structure:
   ```bash
   ls -la "/mnt/e/SteamLibrary/steamapps/common/VTube Studio/VTube Studio_Data/StreamingAssets/Live2DModels/ganyu/"
   ```

3. You should see:
   - `ganyu.model3.json` (model definition)
   - `ganyu.moc3` (3D model data)
   - `textures/` directory with PNG files

### Issue B: Python Version Mismatch

**Symptom:** Log shows `[live2d.v3] Cubism Native, Python 3.12.3` but you're running Python 3.11

**Root Cause:** The live2d-py package was compiled for Python 3.12, causing ABI incompatibility.

**Fix Option 1: Install Python 3.11 compatible version**
```bash
# Uninstall current version
pip uninstall live2d-py

# Install from GitHub releases (check for cp311 wheel)
# Visit: https://github.com/EasyLive2D/live2d-py/releases
# Download the wheel that matches your Python version

# Example for Python 3.11:
pip install https://github.com/EasyLive2D/live2d-py/releases/download/v0.7.0.4/live2d_py-0.7.0.4-cp311-cp311-linux_x86_64.whl
```

**Fix Option 2: Use Python 3.12**
```bash
# Install Python 3.12
sudo apt install python3.12 python3.12-venv

# Create new virtual environment
python3.12 -m venv venv312
source venv312/bin/activate

# Reinstall all dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Install KittenTTS
pip install https://github.com/KittenML/KittenTTS/releases/download/0.8.1/kittentts-0.8.1-py3-none-any.whl
```

### Issue C: Corrupted Model Files

**Symptom:** All files present but still crashes

**Fix:**
1. Re-download the model from VTube Studio
2. Or try a different Live2D model to test if the issue is model-specific

### Issue D: OpenGL Context Issue

**Symptom:** Crash happens during `LoadModelJson`

**Fix:**
The updated code now validates files before loading and has better error handling. Make sure you have the latest `avatar/live2d.py` with the `_validate_model_files()` method.

## Step 3: Test with Updated Code

The updated `avatar/live2d.py` now:
1. ✓ Validates all model files before loading
2. ✓ Provides detailed error messages
3. ✓ Catches SIGSEGV and other fatal errors
4. ✓ Shows clear error in UI instead of crashing

**Run the application:**
```bash
python main.py --debug
```

**Expected behavior:**
- If files are missing: Clear error message listing missing files
- If Python mismatch: Clear error message with fix instructions
- If model loads: Ganyu avatar appears in window

## Step 4: Debug Output Analysis

Look for these lines in the log:

**Good signs:**
```
✓ All required model files validated
✓ Moc file exists: ganyu.moc3
✓ Texture exists: texture_00.png
✓ Live2D model loaded successfully: ganyu.model3.json
```

**Bad signs:**
```
✗ Missing required model files:
  - Moc: /path/to/ganyu.moc3
```

Or:
```
Python version mismatch detected!
  Current Python: cp311 (Python 3.11)
  live2d-py native extension built for: cp312
```

## Step 5: Alternative Solutions

If the above doesn't work, try:

### Solution 1: Use a Different Model

Download a simple test model to verify Live2D works:
```bash
# Download Haru model (official Live2D sample)
wget https://github.com/EasyLive2D/live2d-py/raw/main/resources/Haru/Haru.model3.json -O /tmp/Haru.model3.json

# Update config.yaml temporarily
avatar:
  model_path: "/tmp/Haru.model3.json"
```

### Solution 2: Disable Live2D Temporarily

Comment out the model path to test other features:
```yaml
avatar:
  model_path: ""  # Disabled
```

The application will run without the avatar but STT/TTS/LLM will still work.

### Solution 3: Check WSLg OpenGL Support

WSLg might have OpenGL issues:
```bash
# Test OpenGL
glxinfo | grep "OpenGL version"

# Should show something like:
# OpenGL version string: 4.6 (Compatibility Profile) Mesa 23.2.1
```

If OpenGL doesn't work, Live2D won't work either.

## Summary

The crash is most likely caused by:
1. **Missing model files** → Run diagnostic script
2. **Python version mismatch** → Install compatible live2d-py
3. **Corrupted model** → Re-download or try different model

Start with the diagnostic script to identify the exact issue.
