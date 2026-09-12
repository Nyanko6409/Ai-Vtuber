# Quick Fix Guide

You have three errors to fix:

## Error 1: STT Still Using PyTorch Detection

**Symptom:**
```
[stt.whisper] INFO: torch not available, using CPU with int8
```

**Cause:** Python cache is using old code.

**Fix:**
```bash
# Clear Python cache
find . -type d -name __pycache__ -exec rm -rf {} +
find . -type f -name "*.pyc" -delete

# Restart the application
python main.py --debug
```

You should now see:
```
[stt.whisper] INFO: CUDA detected via CTranslate2 (1 device(s))
[stt.whisper] INFO: Using CUDA GPU acceleration
```

---

## Error 2: KittenTTS Missing espeak

**Symptom:**
```
[tts.kitten] ERROR: Failed to load KittenTTS: espeak not installed on your system
```

**Cause:** KittenTTS requires espeak for text normalization.

**Fix:**
```bash
sudo apt update
sudo apt install -y espeak espeak-ng
```

Then restart:
```bash
python main.py --debug
```

---

## Error 3: Live2D SIGSEGV (Python Version Mismatch)

**Symptom:**
```
[live2d.v3] Cubism Native, Python 3.12.3
fish: Job 1, 'python main.py --debug' terminated by signal SIGSEGV
```

**Cause:** The live2d-py package was compiled for Python 3.12, but you're running Python 3.11.

**Fix - Option A (Recommended): Install Python 3.11 compatible wheel**

```bash
pip uninstall live2d-py
pip install https://github.com/EasyLive2D/live2d-py/releases/download/v0.7.0.4/live2d_py-0.7.0.4-cp311-cp311-linux_x86_64.whl
```

**Fix - Option B: Use Python 3.12**

```bash
# Install Python 3.12
sudo apt install python3.12 python3.12-venv

# Create new virtual environment
python3.12 -m venv venv312
source venv312/bin/activate

# Reinstall all dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Install KittenTTS (official 0.8.x)
pip install https://github.com/KittenML/KittenTTS/releases/download/0.8.1/kittentts-0.8.1-py3-none-any.whl

# Install espeak
sudo apt install -y espeak espeak-ng

# Run the application
python main.py --debug
```

---

## Automated Fix Script

Run the automated fix script:

```bash
chmod +x fix_errors.sh
./fix_errors.sh
```

This will:
1. Clear Python cache
2. Install espeak if missing
3. Check for Python version mismatch
4. Check CUDA availability

---

## Verification

After applying fixes, run:

```bash
# Test Live2D standalone
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

Expected output:
```
[stt.whisper] INFO: CUDA detected via CTranslate2 (1 device(s))
[stt.whisper] INFO: Using CUDA GPU acceleration
[tts.kitten] INFO: KittenTTS loaded. Voice: Bella, Speed: 1.0
[live2d] third-party wrapper (0.7.0)
[live2d.v3] Cubism Native, Python 3.11.16  ← Should match your Python version
[ai_vtuber] INFO: Live2D avatar initialized with OpenGL context
[ai_vtuber] INFO: Entering main loop. Press ESC or close window to quit.
```

---

## Summary of Required Actions

1. **Clear Python cache** (fixes STT PyTorch detection)
2. **Install espeak** (fixes KittenTTS)
3. **Fix Python version mismatch** (fixes Live2D SIGSEGV)
   - Either install Python 3.11 compatible live2d-py wheel
   - Or upgrade to Python 3.12

After these fixes, the application should run without errors.
