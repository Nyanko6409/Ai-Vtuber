# AI VTuber - Local AI Virtual YouTuber

A fully local AI VTuber application that combines Live2D avatar rendering, speech recognition, text-to-speech, and LLM conversation - all running on your machine.

![AI VTuber](https://img.shields.io/badge/Python-3.11-blue) ![License](https://img.shields.io/badge/License-MIT-green) ![Platform](https://img.shields.io/badge/Platform-Ubuntu%2024.04-orange)

## 🌟 Features

### Core Features
- **Live2D Avatar** - Animated character with expressions, blinking, and lip sync
- **Speech Recognition** - Real-time voice input using faster-whisper with CUDA acceleration
- **Text-to-Speech** - Natural voice output using KittenTTS (Bella voice)
- **LLM Integration** - Connects to LM Studio for AI conversations
- **Chat Interface** - Text-based input with typewriter effect and control buttons
- **Emotion System** - Avatar expressions change based on conversation context
- **Full Privacy** - Everything runs locally, no data sent to external servers

### Chat Interface
- **Interactive Chat Box** - Rounded input field at the bottom of the window
- **Control Buttons** - Toggle visibility and clear chat history
- **Typewriter Effect** - AI responses appear character by character
- **Message History** - Shows conversation with color-coded messages
- **Dual Input** - Use voice OR text input (both work simultaneously)

## 🚀 Quick Start

### Prerequisites
- Ubuntu 24.04 (WSL2 supported)
- Python 3.11
- NVIDIA GPU with CUDA support (recommended)
- LM Studio installed and running

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/Nyanko6409/Ai-Vtuber.git
cd Ai-Vtuber/ai_vtuber
```

2. **Create virtual environment**
```bash
python3.11 -m venv venv
source venv/bin/activate
```

3. **Install dependencies**
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

4. **Install KittenTTS (official 0.8.1)**
```bash
pip install https://github.com/KittenML/KittenTTS/releases/download/0.8.1/kittentts-0.8.1-py3-none-any.whl
```

5. **Install system dependencies**
```bash
sudo apt update
sudo apt install -y espeak espeak-ng
```

6. **Configure LM Studio**
- Download and install [LM Studio](https://lmstudio.ai/)
- Load a model (e.g., Gemma 4 E4B)
- Start the local server (default: http://localhost:1234)

7. **Configure Live2D model**
Edit `config.yaml` and set your model path:
```yaml
avatar:
  model_path: "/path/to/your/model.model3.json"
```

### Running the Application

```bash
python main.py --debug
```

## 🎮 Controls

### Chat Interface Controls

| Button | Action | Description |
|--------|--------|-------------|
| 💬 (Chat Icon) | Toggle Chat | Show/hide the chat interface |
| ✖ (X Icon) | Clear Chat | Clear all message history |

### Keyboard Shortcuts

| Key | Action | When |
|-----|--------|------|
| **Enter** | Send message | Chat input active |
| **Backspace** | Delete character | Chat input active |
| **Tab** | Toggle chat visibility | Always |
| **ESC** | Quit application | Always |
| **F** | Toggle FPS display | Always |
| **D** | Toggle debug info | Always |

**Note:** Special keys (Tab, ESC, F, D) now work even when chat input is active. You don't need to deactivate chat to use these shortcuts.

### Mouse Controls
- **Click chat buttons** - Toggle visibility or clear chat
- **Click input box** - Focus the text input
- **Hover over buttons** - Visual feedback

## 📖 Usage Guide

### Starting a Conversation

1. **Launch the application**
```bash
python main.py --debug
```

2. **Wait for initialization**
   - Live2D model loads
   - Whisper STT model loads (with CUDA if available)
   - KittenTTS model loads
   - LM Studio connection established

3. **Start chatting**
   - **Voice input**: Just speak into your microphone
   - **Text input**: Click the chat box or press Tab, then type and press Enter

4. **Watch the AI respond**
   - Text appears with typewriter effect
   - Voice speaks the response
   - Avatar shows matching emotion
   - Full conversation logged in CLI

### Example Conversation

```
You: Hello! How are you today?
AI: [happy] I'm doing wonderful, thanks for asking! It's great to chat with you!

You: Tell me a joke!
AI: [excited] Why don't scientists trust atoms? Because they make up everything!

You: That's funny! What's your favorite color?
AI: [thinking] Hmm, I'd say purple! It feels creative and mysterious.
```

## ⚙️ Configuration

All settings are in `config.yaml`. Key configurations:

### LLM Settings
```yaml
llm:
  base_url: "http://localhost:1234/v1"
  model: "gemma-4-e4b"
  temperature: 0.8
  max_tokens: 2000
  max_history: 10
```

### STT Settings
```yaml
stt:
  model_size: "small"  # tiny, base, small, medium, large-v3
  device: "auto"       # auto (detects CUDA), cuda, cpu
  compute_type: "auto"
  language: "en"
```

### TTS Settings
```yaml
tts:
  model: "KittenML/kitten-tts-mini-0.8"
  voice: "Bella"
  speed: 1.0
  backend: "cpu"
```

### Avatar Settings
```yaml
avatar:
  model_path: "/path/to/model.model3.json"
  window_width: 800
  window_height: 600
  fps: 30
  scale: 2.0
```

## 🔧 Troubleshooting

### Common Issues

#### 1. Live2D Model Not Loading
**Symptom**: Black screen or error message
**Solution**:
- Check model path in `config.yaml`
- Verify model files exist (moc3, textures, physics)
- Run diagnostic: `python test_model_diagnostic.py`

#### 2. Python Version Mismatch
**Symptom**: `SIGSEGV` or `Python 3.12.3` in logs when running Python 3.11
**Solution**:
```bash
# Install compatible live2d-py
pip uninstall live2d-py
pip install live2d-py  # Try to get correct version
```

#### 3. KittenTTS Not Loading
**Symptom**: `espeak not installed` error
**Solution**:
```bash
sudo apt install espeak espeak-ng
```

#### 4. CUDA Not Detected
**Symptom**: `torch not available, using CPU with int8`
**Solution**:
- The app now uses CTranslate2 for CUDA detection (no PyTorch needed)
- Check logs for: `CUDA detected via CTranslate2`
- If still using CPU, verify NVIDIA drivers are installed

#### 5. Chat Interface Not Responding
**Symptom**: Can't type or send messages
**Solution**:
- Check if chat is visible (blue border on input box)
- Press Tab to toggle chat visibility
- Click on the input box to focus it
- Check CLI for errors

#### 6. CUDA Library Error
**Symptom**: `RuntimeError: Library libcublas.so.12 is not found or cannot be loaded`
**Solution**:

**Option 1: Install CUDA libraries**
```bash
sudo apt install nvidia-cuda-toolkit
```

**Option 2: Use CPU instead of CUDA**
Edit `config.yaml`:
```yaml
stt:
  device: "cpu"  # Change from "auto" to "cpu"
  compute_type: "int8"
```

**Option 3: Add CUDA to library path**
```bash
export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH
```

### Debug Mode

Run with debug logging:
```bash
python main.py --debug
```

This shows detailed logs for:
- Model loading
- CUDA detection
- Chat messages
- Emotion parsing
- TTS generation
- Avatar rendering

## 📊 System Status

### Current Working Components
✅ **LM Studio** - Connected and responding  
✅ **KittenTTS** - Voice synthesis working (Bella voice)  
✅ **Live2D Avatar** - Ganyu model loaded successfully  
✅ **Chat Interface** - Text input with typewriter effect  
✅ **Voice Input** - Microphone active with VAD  
✅ **Emotion System** - Avatar expressions change  
✅ **CUDA Acceleration** - GPU acceleration for STT  

### Diagnostic Tools

The project includes several diagnostic scripts:

```bash
# Check Live2D model files
python test_model_diagnostic.py

# Check Python/native compatibility
python test_python_compat.py

# Test Live2D standalone
python test_live2d_standalone.py

# Check OpenGL/WSL compatibility
python test_opengl_check.py
```

## 🏗️ Architecture

```
Microphone Input
    ↓
Voice Activity Detection (VAD)
    ↓
faster-whisper (STT with CUDA)
    ↓
LM Studio API (Gemma 4 E4B)
    ↓
Emotion Parser
    ↓
┌───────────────┬───────────────┐
│               │               │
Live2D Avatar   KittenTTS      Chat UI
(Expressions)   (Voice)        (Text Display)
```

### Key Components

- **core/app.py** - Main application controller
- **ui/chat_ui.py** - Chat interface with buttons
- **ui/pygame_ui.py** - Pygame/OpenGL rendering
- **avatar/live2d.py** - Live2D model handling
- **stt/whisper.py** - Speech recognition
- **tts/kitten.py** - Text-to-speech
- **llm/lmstudio.py** - LLM API client

## 📝 Recent Updates

### Latest Changes (September 2026)

#### Chat Interface with Buttons
- ✅ Added toggle button to show/hide chat
- ✅ Added clear button to reset conversation
- ✅ Improved event handling (no more conflicts)
- ✅ OpenGL texture rendering for chat UI
- ✅ Mouse hover effects on buttons

#### Bug Fixes
- ✅ Fixed `pygame` not defined error
- ✅ Fixed event handling conflicts
- ✅ Fixed ESC key conflict with chat
- ✅ Improved button click detection
- ✅ Better error messages for Live2D issues

#### Performance Improvements
- ✅ CUDA detection via CTranslate2 (no PyTorch)
- ✅ Optimized event processing
- ✅ Better memory management
- ✅ Smoother typewriter effect

## 🤝 Contributing

Contributions are welcome! Areas for improvement:
- Additional Live2D models
- More voice options
- Enhanced emotion detection
- Multi-language support
- Performance optimizations

## 📄 License

MIT License - See LICENSE file for details

## 🙏 Acknowledgments

- [Live2D Cubism](https://www.live2d.com/) - Avatar rendering
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) - Speech recognition
- [KittenTTS](https://github.com/KittenML/KittenTTS) - Text-to-speech
- [LM Studio](https://lmstudio.ai/) - Local LLM hosting
- [live2d-py](https://github.com/EasyLive2D/live2d-py) - Python Live2D bindings

## 📞 Support

For issues and questions:
1. Check the troubleshooting section
2. Run diagnostic scripts
3. Check debug logs
4. Review existing issues on GitHub

---

**Note**: This application runs entirely locally. No data is sent to external servers except for the LM Studio API (which runs on your machine).
