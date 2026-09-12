# Complete Fix Guide for AI VTuber Errors

You have three errors that need to be fixed. Follow these steps in order:

---

## Error 1: STT Using PyTorch Instead of CTranslate2

**Symptom:**
```
[stt.whisper] INFO: torch not available, using CPU with int8
```

**Cause:** Your git repository has old code. The fixed code uses ctranslate2 for CUDA detection.

**Fix:**

The file `ai_vtuber/stt/whisper.py` in this project has the fix. You need to copy it to your machine:

```bash
# Option A: Copy the file manually
# Copy ai_vtuber/stt/whisper.py from this project to your machine

# Option B: If you can commit and push
cd /path/to/this/project
git add ai_vtuber/stt/whisper.py
git commit -m "Fix STT to use ctranslate2 for CUDA detection"
git push origin main

# Then on your machine:
cd ~/app/Ai-Vtuber
git pull origin main
```

After updating, you should see:
```
[stt.whisper] INFO: CUDA detected via CTranslate2 (1 device(s))
[stt.whisper] INFO: Using CUDA GPU acceleration
```

---

## Error 2: KittenTTS Wrong Package Version

**Symptom:**
```
[tts.kitten] ERROR: Failed to load KittenTTS: [ONNXRuntimeError] : 3 : NO_SUCHFILE : Load model from KittenML/kitten-tts-mini-0.8 failed
```

**Cause:** You have the PyPI `kittentts` 0.1.x package installed, but it uses different model names. You need the official 0.8.1 package from GitHub.

**Fix:**

```bash
# Uninstall the wrong package
pip uninstall -y kittentts

# Install the official 0.8.1 package from GitHub
pip install https://github.com/KittenML/KittenTTS/releases/download/0.8.1/kittentts-0.8.1-py3-none-any.whl

# Verify installation
python -c "from kittentts import KittenTTS; print('KittenTTS 0.8.1 installed successfully')"
```

Your config.yaml already has the correct model name:
```yaml
tts:
  model: "KittenML/kitten-tts-mini-0.8"  # Correct for official 0.8.1
```

After installing, you should see:
```
[tts.kitten] INFO: KittenTTS 0.8.x loaded. Voice: Bella, Speed: 1.0
```

---

## Error 3: Live2D SIGSEGV (Python Version Mismatch)

**Symptom:**
```
[live2d.v3] Cubism Native, Python 3.12.3
fish: Job 1, 'python main.py --debug' terminated by signal SIGSEGV
```

**Cause:** The live2d-py native extension was compiled for Python 3.12, but you're running Python 3.11.16. This causes an ABI mismatch and SIGSEGV.

**Fix:**

The file `ai_vtuber/avatar/live2d.py` in this project now checks compatibility BEFORE importing, which prevents the crash. Copy this file to your machine:

```bash
# Copy the fixed file
# Copy ai_vtuber/avatar/live2d.py from this project to your machine
```

After updating, you'll see a clear error message instead of a crash:
```
[avatar.live2d] ERROR: Python version mismatch detected!
  Current Python: cp311 (Python 3.11)
  live2d-py native extension built for: cp312
  This will cause SIGSEGV (segmentation fault).

SOLUTION - Choose one:
  Option A: Install Python 3.11 compatible live2d-py
    pip uninstall live2d-py
    pip install live2d-py

  Option B: Use Python 3.12
    sudo apt install python3.12 python3.12-venv
    python3.12 -m venv venv312
    source venv312/bin/activate
    pip install -r requirements.txt
```

**To actually fix Live2D, choose one:**

### Option A: Install Python 3.11 compatible live2d-py (Recommended)

```bash
# Uninstall current version
pip uninstall -y live2d-py

# Try to install from PyPI (may not have Python 3.11 wheel)
pip install live2d-py

# If that doesn't work, download the correct wheel from GitHub releases
# Visit: https://github.com/EasyLive2D/live2d-py/releases
# Download the cp311 wheel for Linux
pip install https://github.com/EasyLive2D/live2d-py/releases/download/v0.7.0.4/live2d_py-0.7.0.4-cp311-cp311-linux_x86_64.whl
```

### Option B: Use Python 3.12

```bash
# Install Python 3.12
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev

# Create new virtual environment
python3.12 -m venv venv312
source venv312/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install all dependencies
pip install -r requirements.txt

# Install official KittenTTS
pip install https://github.com/KittenML/KittenTTS/releases/download/0.8.1/kittentts-0.8.1-py3-none-any.whl

# Install espeak (required for KittenTTS)
sudo apt install -y espeak espeak-ng

# Run the application
python main.py --debug
```

---

## Complete Fix Script

Run this script to apply all fixes automatically:

```bash
#!/bin/bash
# fix_all_errors.sh

echo "=========================================="
echo "AI VTuber - Complete Fix Script"
echo "=========================================="
echo ""

# Fix 1: Clear Python cache
echo "[1/5] Clearing Python cache..."
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
echo "✓ Cache cleared"
echo ""

# Fix 2: Install espeak
echo "[2/5] Installing espeak (required for KittenTTS)..."
sudo apt update
sudo apt install -y espeak espeak-ng
echo "✓ espeak installed"
echo ""

# Fix 3: Fix KittenTTS
echo "[3/5] Fixing KittenTTS..."
pip uninstall -y kittentts
pip install https://github.com/KittenML/KittenTTS/releases/download/0.8.1/kittentts-0.8.1-py3-none-any.whl
echo "✓ KittenTTS 0.8.1 installed"
echo ""

# Fix 4: Check Live2D compatibility
echo "[4/5] Checking Live2D compatibility..."
python -c "
import sys
print(f'Python version: {sys.version_info.major}.{sys.version_info.minor}')
try:
    import live2d
    print('live2d-py is installed')
    # Check for version mismatch
    import subprocess
    result = subprocess.run([sys.executable, '-c', 'import live2d.v3'], 
                          capture_output=True, text=True)
    if 'Python 3.12' in result.stderr and sys.version_info.minor != 12:
        print('⚠ WARNING: Python version mismatch detected!')
        print('  live2d-py was compiled for Python 3.12')
        print('  You are running Python {}.{}'.format(sys.version_info.major, sys.version_info.minor))
        print('')
        print('  Fix: Install Python 3.11 compatible live2d-py or use Python 3.12')
    else:
        print('✓ No Python version mismatch detected')
except ImportError:
    print('✗ live2d-py not installed')
    print('  Install with: pip install live2d-py')
"
echo ""

# Fix 5: Check CUDA
echo "[5/5] Checking CUDA availability..."
python -c "
try:
    import ctranslate2
    cuda_count = ctranslate2.get_cuda_device_count()
    if cuda_count > 0:
        print(f'✓ CUDA available: {cuda_count} device(s)')
    else:
        print('✗ No CUDA devices found (will use CPU)')
except ImportError:
    print('✗ ctranslate2 not available')
except Exception as e:
    print(f'✗ CUDA check failed: {e}')
"
echo ""

echo "=========================================="
echo "Fix script complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. If Live2D shows version mismatch, apply Option A or B from the guide"
echo "2. Copy the fixed files from this project:"
echo "   - ai_vtuber/stt/whisper.py"
echo "   - ai_vtuber/avatar/live2d.py"
echo "3. Run: python main.py --debug"
echo ""
```

---

## Verification

After applying all fixes, run:

```bash
python main.py --debug
```

**Expected output:**
```
[stt.whisper] INFO: CUDA detected via CTranslate2 (1 device(s))
[stt.whisper] INFO: Using CUDA GPU acceleration
[stt.whisper] INFO: Whisper model loaded successfully on cuda

[tts.kitten] INFO: KittenTTS 0.8.x loaded. Voice: Bella, Speed: 1.0

[live2d] third-party wrapper (0.7.0)
[live2d.v3] Cubism Native, Python 3.11.16  ← Should match your Python version
[avatar.live2d] INFO: live2d-py loaded successfully (Cubism v3)
[avatar.live2d] INFO: Loading Live2D model: /mnt/e/.../ganyu.model3.json
[avatar.live2d] INFO: Live2D model loaded: ganyu.model3.json
[ai_vtuber] INFO: Live2D avatar initialized with OpenGL context
[ai_vtuber] INFO: Entering main loop. Press ESC or close window to quit.
```

---

## Summary

| Error | Cause | Fix |
|-------|-------|-----|
| STT using PyTorch | Old code in git repo | Copy fixed `stt/whisper.py` |
| KittenTTS model not found | Wrong package version | Install official 0.8.1 from GitHub |
| Live2D SIGSEGV | Python 3.12 native extension on Python 3.11 | Install compatible live2d-py or use Python 3.12 |

After applying these fixes, the application should run without errors.
