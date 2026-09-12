# AI VTuber - Local AI Virtual YouTuber

A fully local AI VTuber application for Ubuntu Linux that combines speech recognition, LLM conversation, text-to-speech, and Live2D avatar rendering.

## Features

- 🎤 **Voice Input** - Real-time speech-to-text using faster-whisper with CUDA acceleration
- 🧠 **AI Conversation** - Powered by Gemma 4 E4B via LM Studio's local API
- 🔊 **Voice Output** - Natural speech synthesis using KittenTTS
- 🎭 **Live2D Avatar** - Animated avatar with expressions, blinking, and lip sync
- ⚡ **Low Latency** - Optimized for real-time interaction on consumer hardware
- 🔒 **Fully Local** - Everything runs on your machine (except LM Studio's API)

## Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | Ryzen 5 6600H | Ryzen 7 or better |
| GPU | RTX 3050 6GB | RTX 3060+ |
| RAM | 16GB | 32GB |
| OS | Ubuntu 22.04+ | Ubuntu 24.04 |

## Architecture

```
Microphone
  → VAD (Voice Activity Detection)
  → faster-whisper (Speech-to-Text)
  → Gemma 4 E4B via LM Studio (LLM)
  → Emotion Parser
  → Live2D Expression
  → KittenTTS (Text-to-Speech)
  → Audio Playback
```

### State Machine

```
IDLE → LISTENING → TRANSCRIBING → THINKING → SPEAKING → IDLE
  ↑                                                      ↓
  └──────────────────── ERROR ───────────────────────────┘
```

## Installation

### 1. System Dependencies

```bash
# Install system packages
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip \
    portaudio19-dev libsndfile1 ffmpeg \
    libgl1-mesa-glx libglib2.0-0

# For Live2D support
sudo apt install -y cmake build-essential
```

### 2. Python Environment

```bash
cd ai_vtuber
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. LM Studio Setup

1. Download and install [LM Studio](https://lmstudio.ai/)
2. Download the Gemma 4 E4B GGUF model
3. Start the local server (default: `http://localhost:1234`)
4. Ensure the OpenAI-compatible API is enabled

### 4. Live2D Model

Place your Live2D model files in a directory and update `config.yaml`:

```yaml
avatar:
  model_path: "/path/to/your/model.model3.json"
```

## Configuration

All settings are in `config.yaml`. Key options:

```yaml
# LLM
llm:
  base_url: "http://localhost:1234/v1"
  model: "gemma-4-e4b"
  temperature: 0.8
  max_tokens: 300

# STT
stt:
  model_size: "small"  # tiny, base, small, medium, large-v3
  device: "auto"       # auto, cuda, cpu

# TTS
tts:
  model: "KittenML/kitten-tts-mini-0.8"
  voice: "Bella"       # Bella, Jasper, Luna, Bruno, Rosie, Hugo, Kiki, Leo
  speed: 1.0

# Avatar
avatar:
  model_path: ""       # Path to .model3.json
```

## Running

```bash
cd ai_vtuber
source venv/bin/activate
python main.py
```

### Command Line Options

```bash
python main.py --config custom_config.yaml  # Custom config
python main.py --debug                       # Debug logging
```

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| ESC | Quit |
| F | Toggle FPS display |
| D | Toggle debug info |

## Project Structure

```
ai_vtuber/
├── main.py              # Entry point
├── config.yaml          # Configuration
├── requirements.txt     # Dependencies
├── README.md           # This file
├── core/
│   ├── app.py          # Main application controller
│   ├── state.py        # State machine
│   └── conversation.py # Conversation history
├── llm/
│   └── lmstudio.py     # LM Studio client
├── stt/
│   └── whisper.py      # faster-whisper STT
├── tts/
│   └── kitten.py       # KittenTTS
├── avatar/
│   └── live2d.py       # Live2D avatar
├── audio/
│   ├── microphone.py   # Microphone input
│   ├── vad.py          # Voice activity detection
│   └── playback.py     # Audio playback
└── ui/
    └── pygame_ui.py    # Pygame UI
```

## Emotion System

The LLM is prompted to start each response with an emotion tag:

```
[happy]
That sounds really fun!
```

Supported emotions: `neutral`, `happy`, `excited`, `thinking`, `surprised`, `sad`, `angry`, `sleepy`

The emotion tag is parsed, sent to the Live2D avatar as an expression, and removed before TTS synthesis.

## Interruption

When you speak while the avatar is talking:
1. TTS playback stops immediately
2. Talking animation stops
3. System returns to listening state
4. Your new speech is processed

## Troubleshooting

### "Cannot connect to LM Studio"
- Ensure LM Studio is running with the server enabled
- Check that the model is loaded
- Verify the URL in config.yaml matches LM Studio's settings

### "Microphone failed"
- Check that a microphone is connected
- List devices: `python -c "import sounddevice; print(sounddevice.query_devices())"`
- Set `microphone_index` in config.yaml

### "Live2D model not found"
- Ensure the model path in config.yaml is correct
- Use absolute paths for reliability
- Verify the model files are complete (.model3.json + textures + motions)

### Low FPS
- Reduce window size in config.yaml
- Use a smaller Whisper model (tiny/base)
- Close other GPU-intensive applications

## License

MIT
