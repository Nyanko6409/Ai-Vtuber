#!/bin/bash
# Fix script for AI VTuber errors
# Run this from the ai_vtuber directory

echo "=========================================="
echo "AI VTuber Fix Script"
echo "=========================================="
echo ""

# Check if we're in the right directory
if [ ! -f "main.py" ]; then
    echo "Error: Please run this script from the ai_vtuber directory"
    exit 1
fi

echo "[1/4] Clearing Python cache..."
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
echo "✓ Cache cleared"
echo ""

echo "[2/4] Checking espeak installation (required for KittenTTS)..."
if ! command -v espeak &> /dev/null; then
    echo "✗ espeak not found. Installing..."
    sudo apt update
    sudo apt install -y espeak espeak-ng
    echo "✓ espeak installed"
else
    echo "✓ espeak already installed"
fi
echo ""

echo "[3/4] Checking Python version compatibility..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "Current Python: $PYTHON_VERSION"

# Check if live2d-py is installed
if python3 -c "import live2d" 2>/dev/null; then
    echo "live2d-py is installed"
    
    # Check for Python version mismatch
    LIVE2D_OUTPUT=$(python3 -c "import live2d.v3" 2>&1 || python3 -c "import live2d.v2" 2>&1)
    if echo "$LIVE2D_OUTPUT" | grep -q "Python 3.12"; then
        echo ""
        echo "⚠ WARNING: Python version mismatch detected!"
        echo "  Application Python: $PYTHON_VERSION"
        echo "  live2d-py compiled for: Python 3.12"
        echo ""
        echo "This will cause SIGSEGV. You have two options:"
        echo ""
        echo "Option A: Install Python 3.11 compatible live2d-py"
        echo "  pip uninstall live2d-py"
        echo "  pip install https://github.com/EasyLive2D/live2d-py/releases/download/v0.7.0.4/live2d_py-0.7.0.4-cp311-cp311-linux_x86_64.whl"
        echo ""
        echo "Option B: Use Python 3.12"
        echo "  sudo apt install python3.12 python3.12-venv"
        echo "  python3.12 -m venv venv312"
        echo "  source venv312/bin/activate"
        echo "  pip install -r requirements.txt"
        echo ""
    else
        echo "✓ No Python version mismatch detected"
    fi
else
    echo "✗ live2d-py not installed"
    echo "  Install with: pip install live2d-py"
fi
echo ""

echo "[4/4] Checking CUDA availability..."
python3 -c "
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
echo "1. If you saw Python version mismatch warning, apply Option A or B above"
echo "2. Run: python main.py --debug"
echo ""
echo "If Live2D still crashes with SIGSEGV:"
echo "  python test_python_compat.py"
echo "  python test_live2d_standalone.py"
