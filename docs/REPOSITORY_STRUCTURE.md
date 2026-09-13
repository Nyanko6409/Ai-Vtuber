# Repository Structure

This document describes the organization of the AI VTuber repository.

## Root Directory

```
/workspace/
├── ai_vtuber/          # Main application package
├── data/               # Persistent memory files (user facts, bot memories)
├── personality/        # Bot personality definition (soul.md)
├── docs/               # Documentation files (*.md)
├── tests/              # Test files and test utilities
├── src/                # Frontend source code (TypeScript/JavaScript)
├── CHANGELOG.md        # Version history
├── README.md           # Project overview
└── [config files]      # package.json, tsconfig.json, vite.config.js
```

## Directory Descriptions

### `/ai_vtuber/`
Main Python application package containing all VTuber functionality:
- `main.py` - Application entry point
- `core/` - Core application logic, state machine, conversation history
- `ui/` - User interface components (Pygame + OpenGL)
- `avatar/` - Live2D avatar rendering and controls
- `audio/` - Microphone, VAD, playback
- `llm/` - LLM client (LM Studio integration)
- `stt/` - Speech-to-text (faster-whisper)
- `tts/` - Text-to-speech (KittenTTS)
- `emotion/` - Emotion analysis and state management
- `memory/` - Persistent memory management

### `/data/`
Persistent storage for runtime memories:
- `user.md` - User facts and preferences
- `memory.md` - Bot's persistent memories from interactions

**Note:** These files are automatically created if missing.

### `/personality/`
Bot personality definition:
- `soul.md` - Character traits, conversational style, emotional behavior

**Note:** This file is loaded once at startup and cached in memory.

### `/docs/`
Documentation files including:
- Development notes
- Feature summaries
- Fix documentation
- Setup guides
- Testing reports

### `/tests/`
Test files for verifying functionality:
- `test_analyzer.py` - Emotion/topic extraction tests
- `test_bugfixes.py` - Regression tests
- `test_live2d_*.py` - Live2D diagnostic tests
- `test_model_*.py` - Model verification tests
- `test_opengl_check.py` - OpenGL compatibility tests
- `test_python_compat.py` - Python version compatibility tests

### `/src/`
Frontend web application source code (TypeScript/Vite).

## File Organization Principles

1. **Source Code**: All Python application code lives in `/ai_vtuber/`
2. **Tests**: All test files live in `/tests/`
3. **Documentation**: All `.md` files (except README.md and CHANGELOG.md) live in `/docs/`
4. **Data**: Runtime data files live in `/data/`
5. **Personality**: Bot character definition lives in `/personality/soul.md`

## Cross-Platform Compatibility

This repository supports:
- **Native Windows**: Run directly on Windows
- **WSL2**: Run on Ubuntu 24.04 under WSL2

All paths use Python's `pathlib` for cross-platform compatibility. Do not hard-code platform-specific paths.

## Important Notes

- **DO NOT** place test files in `/ai_vtuber/`
- **DO NOT** place documentation `.md` files in `/ai_vtuber/` (except README.md in root)
- **DO NOT** modify `data/` or `personality/` paths in code - they are auto-detected relative to project root
- **DO** keep `/ai_vtuber/` clean with only source code and necessary package files
