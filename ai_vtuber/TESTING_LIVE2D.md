# Live2D Diagnostic Tests

This directory contains diagnostic scripts to identify the cause of the Live2D SIGSEGV crash.

## Background

The application crashes with SIGSEGV when loading Live2D models. The Live2D native output reports Python 3.12.3 while the application runs Python 3.11.16, suggesting a Python/native ABI mismatch.

## Test Scripts

### 1. test_live2d_diagnose.py
Inspects the installed live2d-py package to understand what we're working with.

```bash
python test_live2d_diagnose.py
```

**What it checks:**
- Python environment details
- live2d package location and version
- Native library files (.so/.pyd)
- Available Live2D modules (v2/v3)

### 2. test_model_verify.py
Verifies that all files referenced in the Live2D model exist.

```bash
python test_model_verify.py
```

**What it checks:**
- Model JSON file exists and is readable
- All referenced textures exist
- All referenced motions exist
- All referenced expressions exist
- Physics, pose, and other files exist

### 3. test_opengl_check.py
Verifies OpenGL/WSL compatibility.

```bash
python test_opengl_check.py
```

**What it checks:**
- Pygame can create OpenGL window
- OpenGL context is valid
- OpenGL version and capabilities
- Required OpenGL extensions

### 4. test_python_compat.py
Investigates Python/native ABI compatibility.

```bash
python test_python_compat.py
```

**What it checks:**
- Current Python version and executable
- Multiple Python installations
- Live2D package location
- Native extension file names (looking for cp311/cp312)
- Python version strings in native binaries
- PYTHONPATH and sys.path

### 5. test_live2d_standalone.py
Isolates each step of Live2D initialization to find where SIGSEGV occurs.

```bash
python test_live2d_standalone.py
```

**What it tests:**
1. Pygame context creation
2. Live2D initialization
3. Model file loading
4. OpenGL renderer initialization
5. LAppModel creation
6. Model loading
7. Model resize
8. Model update
9. Model render (one frame)
10. Sustained rendering (3 seconds)

**This is the most important test.** It will show exactly which operation causes the crash.

## Running All Tests

```bash
# Run in order
python test_live2d_diagnose.py
python test_model_verify.py
python test_opengl_check.py
python test_python_compat.py
python test_live2d_standalone.py
```

## Expected Results

### If Python version mismatch is the issue:
- `test_python_compat.py` will show the native .so file contains "python3.12" strings
- `test_live2d_standalone.py` will crash with SIGSEGV during initialization or model loading

### If OpenGL/WSL is the issue:
- `test_opengl_check.py` will fail to create OpenGL context or show missing extensions

### If model files are missing:
- `test_model_verify.py` will show missing texture/motion/expression files

### If Live2D API is wrong:
- `test_live2d_standalone.py` will fail at a specific step with a Python exception (not SIGSEGV)

## Fixing the Issue

### Python Version Mismatch (Most Likely)

If the tests confirm Python 3.12 native binary is loaded in Python 3.11:

**Option 1: Install correct live2d-py for Python 3.11**
```bash
pip uninstall live2d-py
pip install live2d-py==0.7.0.4  # Check PyPI for Python 3.11 wheel
```

If no Python 3.11 wheel exists on PyPI, download from GitHub releases:
```bash
pip install https://github.com/EasyLive2D/live2d-py/releases/download/v0.7.0.4/live2d_py-0.7.0.4-cp311-cp311-linux_x86_64.whl
```

**Option 2: Use Python 3.12**
```bash
# Install Python 3.12
sudo apt install python3.12 python3.12-venv

# Create new venv with Python 3.12
python3.12 -m venv venv312
source venv312/bin/activate

# Reinstall all dependencies
pip install -r requirements.txt
```

**Option 3: Build from source**
```bash
git clone https://github.com/EasyLive2D/live2d-py.git
cd live2d-py
pip install .
```

### OpenGL/WSL Issues

If OpenGL tests fail:
```bash
# Install WSLg dependencies
sudo apt install mesa-utils libgl1-mesa-glx

# Test OpenGL
glxinfo | grep "OpenGL version"
```

### Missing Model Files

If model verification fails, ensure all files referenced in `ganyu.model3.json` exist in the model directory.

## After Fixing

Once the standalone test passes:
```bash
python test_live2d_standalone.py
```

Run the main application:
```bash
python main.py --debug
```

The Live2D avatar should now load and render without crashing.
