# Windows 11 Setup Guide for AI VTuber

This guide explains how to run the AI VTuber application on Windows 11.

## Prerequisites

1. **Python 3.11 or 3.12**
   - Download from: https://www.python.org/downloads/
   - ✅ Check "Add Python to PATH" during installation

2. **Git for Windows** (optional, for cloning the repo)
   - Download from: https://git-scm.com/download/win

3. **Visual C++ Redistributable** (required for some packages)
   - Download from: https://aka.ms/vs/17/release/vc_redist.x64.exe

## Installation Steps

### 1. Clone or Download the Repository

```powershell
# If using Git
git clone <repository-url>
cd ai_vtuber

# Or download ZIP and extract to a folder
```

### 2. Create Virtual Environment

```powershell
# Create virtual environment
python -m venv .venv

# Activate it
.\.venv\Scripts\Activate.ps1

# If you get execution policy error, run:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 3. Install Dependencies

```powershell
# Upgrade pip
python -m pip install --upgrade pip

# Install requirements
pip install -r requirements.txt

# Install KittenTTS 0.8.1 (official version)
pip install https://github.com/KittenML/KittenTTS/releases/download/0.8.1/kittentts-0.8.1-py3-none-any.whl
```

### 4. Configure the Application

Edit `config.yaml`:

```yaml
# Update the model path to your Live2D model location
avatar:
  model_path: "C:/Users/YourName/VTubeStudio/Models/ganyu/ganyu.model3.json"
  # Use forward slashes OR double backslashes:
  # "C:\\Users\\YourName\\Models\\ganyu\\ganyu.model3.json"

# For CPU-only mode (recommended for most Windows users)
stt:
  device: "cpu"
  compute_type: "int8"

tts:
  backend: "cpu"
```

### 5. Start LM Studio

1. Download LM Studio from: https://lmstudio.ai/
2. Install and launch it
3. Download a model (e.g., Gemma-4-E4B)
4. Go to the "Local Server" tab
5. Click "Start Server" (default port: 1234)

### 6. Run the Application

```powershell
# Make sure virtual environment is active
.\.venv\Scripts\Activate.ps1

# Run with debug logging
python main.py --debug
```

## Troubleshooting

### Audio Issues

If you can't hear audio:

1. **Check Windows Sound Settings**
   - Right-click speaker icon → Open Sound settings
   - Ensure correct output device is selected

2. **Test Pygame Audio**
   ```powershell
   python -c "import pygame; pygame.mixer.init(); print('Pygame mixer OK')"
   ```

3. **Install DirectSound Dependencies**
   - Pygame uses DirectSound on Windows, which should work out of the box
   - If issues persist, reinstall pygame: `pip install --force-reinstall pygame`

### Microphone Issues

To list available microphones:

```powershell
python -c "import sounddevice; print(sounddevice.query_devices())"
```

Update `config.yaml` with the correct device index:

```yaml
audio:
  microphone_index: 0  # Change to your mic's index number
```

### CUDA/cuBLAS Errors

If you see errors like `Library libcublas.so.12 is not found` or similar:

1. **Use CPU Mode** (Recommended for most users)
   ```yaml
   stt:
     device: "cpu"
     compute_type: "int8"
   
   tts:
     backend: "cpu"
   ```

2. **If You Want CUDA Support**:
   - Install NVIDIA CUDA Toolkit from: https://developer.nvidia.com/cuda-downloads
   - Install cuDNN from: https://developer.nvidia.com/cudnn
   - Add CUDA to PATH:
     ```powershell
     $env:PATH = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6\bin;" + $env:PATH
     ```

### Live2D Model Not Loading

1. **Check Path Format**
   - Use forward slashes: `C:/Users/Name/Models/model.model3.json`
   - OR escaped backslashes: `C:\\Users\\Name\\Models\\model.model3.json`

2. **Verify Model Files**
   - Ensure `.model3.json`, `.moc3`, and texture files exist
   - Check that paths in `.model3.json` are correct

3. **Permissions**
   - Make sure the model folder isn't blocked by Windows
   - Right-click folder → Properties → Unblock if present

### Performance Issues

1. **Reduce Model Complexity**
   - Use smaller Live2D models
   - Lower FPS in config: `avatar.fps: 24`

2. **Use Smaller Models**
   - STT: Use `tiny` or `base` instead of `small`
   - TTS: Use `kitten-tts-nano-0.8` instead of `mini`

3. **Close Other Applications**
   - Free up RAM and CPU resources

## Quick Start Checklist

- [ ] Python 3.11+ installed and added to PATH
- [ ] Virtual environment created and activated
- [ ] All dependencies installed (`pip install -r requirements.txt`)
- [ ] KittenTTS 0.8.1 installed from GitHub
- [ ] LM Studio running with model loaded
- [ ] `config.yaml` updated with correct model path
- [ ] STT/TTS set to `"cpu"` mode (unless you have CUDA configured)
- [ ] Audio output device working
- [ ] Microphone accessible

## Commands Reference

```powershell
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Run application
python main.py

# Run with debug logging
python main.py --debug

# List audio devices
python -c "import sounddevice; print(sounddevice.query_devices())"

# Test pygame mixer
python -c "import pygame; pygame.mixer.init(); print('OK')"

# Deactivate virtual environment
deactivate
```

## Additional Resources

- LM Studio Docs: https://lmstudio.ai/docs
- Pygame Documentation: https://www.pygame.org/docs/
- Live2D Cubism SDK: https://www.live2d.com/en/sdk/download/
- This Project's README: See main README.md for more details

## Support

If you encounter issues:

1. Check the logs for error messages
2. Review this troubleshooting guide
3. Search existing issues on the repository
4. Create a new issue with:
   - Windows version
   - Python version
   - Error messages
   - Steps to reproduce
