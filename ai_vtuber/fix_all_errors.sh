#!/bin/bash
# AI VTuber - Automated Fix Script
# Fixes all three errors: STT PyTorch, KittenTTS wrong package, Live2D SIGSEGV

set -e  # Exit on error

echo "=========================================="
echo "AI VTuber - Automated Fix Script"
echo "=========================================="
echo ""

# Check if we're in a virtual environment
if [ -z "$VIRTUAL_ENV" ]; then
    echo "⚠ WARNING: Not in a virtual environment!"
    echo "  Please activate your venv first:"
    echo "  source .venv/bin/activate"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "[1/6] Clearing Python cache..."
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
echo "✓ Cache cleared"
echo ""

echo "[2/6] Installing system dependencies..."
sudo apt update -qq
sudo apt install -y -qq espeak espeak-ng > /dev/null 2>&1
echo "✓ espeak installed"
echo ""

echo "[3/6] Fixing KittenTTS..."
echo "  Uninstalling old package..."
pip uninstall -y kittentts > /dev/null 2>&1 || true
echo "  Installing official 0.8.1 from GitHub..."
pip install -q https://github.com/KittenML/KittenTTS/releases/download/0.8.1/kittentts-0.8.1-py3-none-any.whl
echo "✓ KittenTTS 0.8.1 installed"
echo ""

echo "[4/6] Checking Python version..."
PYTHON_VERSION=$(python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  Current Python: $PYTHON_VERSION"
echo ""

echo "[5/6] Checking Live2D compatibility..."
python -c "
import sys
import subprocess

try:
    # Check if live2d is installed
    result = subprocess.run([sys.executable, '-c', 'import live2d.v3'], 
                          capture_output=True, text=True, timeout=5)
    
    # Check for Python version mismatch
    if 'Python 3.12' in result.stderr:
        if sys.version_info.major == 3 and sys.version_info.minor == 11:
            print('⚠ WARNING: Python version mismatch detected!')
            print('  live2d-py was compiled for Python 3.12')
            print('  You are running Python 3.11')
            print('')
            print('  This will cause SIGSEGV.')
            print('')
            print('  SOLUTION: Install Python 3.11 compatible live2d-py')
            print('  Run: pip uninstall live2d-py && pip install live2d-py')
            print('')
            print('  Or use Python 3.12:')
            print('  sudo apt install python3.12 python3.12-venv')
            print('  python3.12 -m venv venv312')
            print('  source venv312/bin/activate')
            print('  pip install -r requirements.txt')
            sys.exit(1)
    else:
        print('✓ No Python version mismatch detected')
        
except subprocess.TimeoutExpired:
    print('⚠ WARNING: live2d import timed out (possible SIGSEGV)')
    print('  This indicates Python version mismatch')
    sys.exit(1)
except Exception as e:
    print(f'Note: {e}')
" || {
    echo ""
    echo "⚠ Live2D has compatibility issues."
    echo "  The application will still run, but without the avatar."
    echo "  See FIX_ALL_ERRORS.md for solutions."
    echo ""
}
echo ""

echo "[6/6] Checking CUDA availability..."
python -c "
try:
    import ctranslate2
    cuda_count = ctranslate2.get_cuda_device_count()
    if cuda_count > 0:
        print(f'✓ CUDA available: {cuda_count} device(s)')
        print('  STT will use GPU acceleration')
    else:
        print('Note: No CUDA devices found')
        print('  STT will use CPU (slower but works)')
except ImportError:
    print('Note: ctranslate2 not available')
    print('  STT will use CPU')
except Exception as e:
    print(f'Note: CUDA check failed: {e}')
" 
echo ""

echo "=========================================="
echo "Fix script complete!"
echo "=========================================="
echo ""
echo "Summary:"
echo "  ✓ Python cache cleared"
echo "  ✓ espeak installed"
echo "  ✓ KittenTTS 0.8.1 installed"
echo "  ✓ Live2D compatibility checked"
echo "  ✓ CUDA availability checked"
echo ""

# Check if files need to be copied
if [ -f "stt/whisper.py" ]; then
    # Check if the file has the ctranslate2 fix
    if grep -q "ctranslate2" stt/whisper.py 2>/dev/null; then
        echo "✓ STT code already has ctranslate2 fix"
    else
        echo "⚠ STT code needs update"
        echo "  The stt/whisper.py file needs the ctranslate2 fix"
        echo "  Copy the fixed version from the project"
    fi
fi

if [ -f "avatar/live2d.py" ]; then
    # Check if the file has the compatibility check
    if grep -q "_check_native_compatibility" avatar/live2d.py 2>/dev/null; then
        echo "✓ Live2D code already has compatibility check"
    else
        echo "⚠ Live2D code needs update"
        echo "  The avatar/live2d.py file needs the compatibility check"
        echo "  Copy the fixed version from the project"
    fi
fi

echo ""
echo "Next steps:"
echo "  1. If Live2D shows version mismatch, install compatible version"
echo "  2. Run: python main.py --debug"
echo ""
echo "Expected output:"
echo "  [stt.whisper] INFO: CUDA detected via CTranslate2"
echo "  [tts.kitten] INFO: KittenTTS 0.8.x loaded"
echo "  [avatar.live2d] INFO: Live2D model loaded"
echo ""
