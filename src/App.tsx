import { useState } from 'react'

function App() {
  const [activeTab, setActiveTab] = useState('overview')
  const [copiedCode, setCopiedCode] = useState<string | null>(null)

  const copyCode = (code: string, id: string) => {
    navigator.clipboard.writeText(code)
    setCopiedCode(id)
    setTimeout(() => setCopiedCode(null), 2000)
  }

  const CodeBlock = ({ code, id, lang = 'bash' }: { code: string; id: string; lang?: string }) => (
    <div className="relative group">
      <div className="absolute top-2 right-2 flex items-center gap-2">
        <span className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded">{lang}</span>
        <button
          onClick={() => copyCode(code, id)}
          className="text-xs bg-gray-700 hover:bg-gray-600 text-gray-300 px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity"
        >
          {copiedCode === id ? '✓ Copied' : 'Copy'}
        </button>
      </div>
      <pre className="bg-gray-900 border border-gray-700 rounded-lg p-4 pt-8 overflow-x-auto text-sm">
        <code className="text-green-300">{code}</code>
      </pre>
    </div>
  )

  const tabs = [
    { id: 'overview', label: 'Overview', icon: '🏠' },
    { id: 'architecture', label: 'Architecture', icon: '🏗️' },
    { id: 'installation', label: 'Installation', icon: '📦' },
    { id: 'configuration', label: 'Configuration', icon: '⚙️' },
    { id: 'code', label: 'Source Code', icon: '💻' },
  ]

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Hero Section */}
      <header className="relative overflow-hidden border-b border-gray-800">
        <div className="absolute inset-0 bg-gradient-to-br from-purple-900/20 via-transparent to-blue-900/20"></div>
        <div className="absolute inset-0">
          <div className="absolute top-10 left-10 w-72 h-72 bg-purple-500/10 rounded-full blur-3xl"></div>
          <div className="absolute bottom-10 right-10 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl"></div>
        </div>
        <div className="relative max-w-6xl mx-auto px-6 py-16">
          <div className="flex items-center gap-4 mb-6">
            <div className="w-16 h-16 bg-gradient-to-br from-purple-500 to-blue-500 rounded-2xl flex items-center justify-center text-3xl shadow-lg shadow-purple-500/20">
              🎭
            </div>
            <div>
              <h1 className="text-4xl font-bold bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text text-transparent">
                AI VTuber
              </h1>
              <p className="text-gray-400 text-lg">Local AI Virtual YouTuber for Ubuntu Linux</p>
            </div>
          </div>
          
          <div className="flex flex-wrap gap-3 mt-6">
            {['faster-whisper', 'Gemma 4', 'KittenTTS', 'Live2D', 'Pygame', 'Python'].map((tech) => (
              <span key={tech} className="px-3 py-1 bg-gray-800 border border-gray-700 rounded-full text-sm text-gray-300">
                {tech}
              </span>
            ))}
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-8">
            {[
              { label: 'STT', value: 'faster-whisper', icon: '🎤' },
              { label: 'LLM', value: 'Gemma 4 E4B', icon: '🧠' },
              { label: 'TTS', value: 'KittenTTS', icon: '🔊' },
              { label: 'Avatar', value: 'Live2DPy', icon: '🎭' },
            ].map((item) => (
              <div key={item.label} className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
                <div className="text-2xl mb-1">{item.icon}</div>
                <div className="text-xs text-gray-500 uppercase tracking-wider">{item.label}</div>
                <div className="text-sm font-medium text-gray-200">{item.value}</div>
              </div>
            ))}
          </div>
        </div>
      </header>

      {/* Navigation Tabs */}
      <nav className="sticky top-0 z-10 bg-gray-950/90 backdrop-blur-sm border-b border-gray-800">
        <div className="max-w-6xl mx-auto px-6">
          <div className="flex gap-1 overflow-x-auto py-2">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-all ${
                  activeTab === tab.id
                    ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
                }`}
              >
                <span>{tab.icon}</span>
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* Content */}
      <main className="max-w-6xl mx-auto px-6 py-10">
        {activeTab === 'overview' && (
          <div className="space-y-8">
            <section>
              <h2 className="text-2xl font-bold text-gray-100 mb-4">🚀 Features</h2>
              <div className="grid md:grid-cols-2 gap-4">
                {[
                  { title: 'Voice Input', desc: 'Real-time STT with faster-whisper + CUDA acceleration', icon: '🎤' },
                  { title: 'AI Conversation', desc: 'Gemma 4 E4B via LM Studio local API', icon: '🧠' },
                  { title: 'Voice Output', desc: 'Natural TTS with KittenTTS (24kHz, 8 voices)', icon: '🔊' },
                  { title: 'Live2D Avatar', desc: 'Expressions, blinking, lip sync, idle animation', icon: '🎭' },
                  { title: 'Low Latency', desc: 'Optimized for real-time on consumer hardware', icon: '⚡' },
                  { title: 'Fully Local', desc: 'Everything runs on your machine', icon: '🔒' },
                  { title: 'Interruption', desc: 'Stop TTS by speaking, seamless transition', icon: '🗣️' },
                  { title: 'Emotion System', desc: '8 emotions mapped to Live2D expressions', icon: '💫' },
                ].map((feature) => (
                  <div key={feature.title} className="flex gap-3 p-4 bg-gray-900/50 border border-gray-800 rounded-xl">
                    <span className="text-2xl">{feature.icon}</span>
                    <div>
                      <h3 className="font-semibold text-gray-200">{feature.title}</h3>
                      <p className="text-sm text-gray-400">{feature.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section>
              <h2 className="text-2xl font-bold text-gray-100 mb-4">💻 Hardware Requirements</h2>
              <div className="overflow-x-auto">
                <table className="w-full border-collapse">
                  <thead>
                    <tr className="border-b border-gray-700">
                      <th className="text-left p-3 text-gray-400 font-medium">Component</th>
                      <th className="text-left p-3 text-gray-400 font-medium">Minimum</th>
                      <th className="text-left p-3 text-gray-400 font-medium">Recommended</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      ['CPU', 'Ryzen 5 6600H', 'Ryzen 7+'],
                      ['GPU', 'RTX 3050 6GB', 'RTX 3060+'],
                      ['RAM', '16GB', '32GB'],
                      ['OS', 'Ubuntu 22.04+', 'Ubuntu 24.04'],
                    ].map(([comp, min, rec]) => (
                      <tr key={comp} className="border-b border-gray-800">
                        <td className="p-3 font-medium text-gray-200">{comp}</td>
                        <td className="p-3 text-gray-400">{min}</td>
                        <td className="p-3 text-gray-300">{rec}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section>
              <h2 className="text-2xl font-bold text-gray-100 mb-4">🔄 Pipeline</h2>
              <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  {[
                    { label: 'Microphone', color: 'bg-blue-500/20 text-blue-300 border-blue-500/30' },
                    { label: 'VAD', color: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30' },
                    { label: 'faster-whisper', color: 'bg-green-500/20 text-green-300 border-green-500/30' },
                    { label: 'Gemma 4 (LM Studio)', color: 'bg-purple-500/20 text-purple-300 border-purple-500/30' },
                    { label: 'Emotion Parser', color: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30' },
                    { label: 'Live2D Expression', color: 'bg-pink-500/20 text-pink-300 border-pink-500/30' },
                    { label: 'KittenTTS', color: 'bg-orange-500/20 text-orange-300 border-orange-500/30' },
                    { label: 'Audio Playback', color: 'bg-red-500/20 text-red-300 border-red-500/30' },
                  ].map((step, i) => (
                    <span key={step.label} className="flex items-center gap-2">
                      <span className={`px-3 py-1.5 rounded-lg border ${step.color}`}>{step.label}</span>
                      {i < 7 && <span className="text-gray-600">→</span>}
                    </span>
                  ))}
                </div>
              </div>
            </section>
          </div>
        )}

        {activeTab === 'architecture' && (
          <div className="space-y-8">
            <section>
              <h2 className="text-2xl font-bold text-gray-100 mb-4">🏗️ System Architecture</h2>
              <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
                <pre className="text-sm text-gray-300 overflow-x-auto whitespace-pre">{`
┌─────────────────────────────────────────────────────────────────┐
│                        AI VTuber Application                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────┐           │
│  │Microphone │───▶│   VAD    │───▶│  faster-whisper  │           │
│  │(16kHz)   │    │(webrtcvad)│    │  (STT, CUDA)    │           │
│  └──────────┘    └──────────┘    └────────┬─────────┘           │
│                                            │                      │
│                                            ▼                      │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────┐           │
│  │  Audio   │◀───│ KittenTTS│◀───│  LM Studio API   │           │
│  │ Playback │    │  (TTS)   │    │  (Gemma 4 E4B)   │           │
│  └──────────┘    └──────────┘    └────────┬─────────┘           │
│       │                                   │                      │
│       │         ┌──────────────┐          │                      │
│       └────────▶│ Live2D Avatar│◀─────────┘                      │
│                 │(expressions, │                                 │
│                 │ lip sync)    │                                 │
│                 └──────────────┘                                 │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              Pygame UI (OpenGL)                           │    │
│  │  [Status Bar] [Avatar View] [Transcription] [Response]   │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
`}</pre>
              </div>
            </section>

            <section>
              <h2 className="text-2xl font-bold text-gray-100 mb-4">📁 Project Structure</h2>
              <CodeBlock id="structure" lang="text" code={`ai_vtuber/
├── main.py              # Entry point & main loop
├── config.yaml          # All configuration
├── requirements.txt     # Python dependencies
├── README.md           # Documentation
├── core/
│   ├── app.py          # Main application controller
│   ├── state.py        # State machine (IDLE→LISTENING→...)
│   └── conversation.py # Conversation history manager
├── llm/
│   └── lmstudio.py     # OpenAI-compatible LM Studio client
├── stt/
│   └── whisper.py      # faster-whisper with CUDA/CPU
├── tts/
│   └── kitten.py       # KittenTTS wrapper
├── avatar/
│   └── live2d.py       # Live2D avatar (live2d-py)
├── audio/
│   ├── microphone.py   # Microphone input (sounddevice)
│   ├── vad.py          # Voice activity detection
│   └── playback.py     # Audio playback with interruption
└── ui/
    └── pygame_ui.py    # Pygame + OpenGL UI`} />
            </section>

            <section>
              <h2 className="text-2xl font-bold text-gray-100 mb-4">🔄 State Machine</h2>
              <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
                <div className="flex flex-wrap items-center justify-center gap-3">
                  {[
                    { state: 'IDLE', color: 'bg-green-500/20 border-green-500/30 text-green-300' },
                    { state: 'LISTENING', color: 'bg-blue-500/20 border-blue-500/30 text-blue-300' },
                    { state: 'TRANSCRIBING', color: 'bg-yellow-500/20 border-yellow-500/30 text-yellow-300' },
                    { state: 'THINKING', color: 'bg-orange-500/20 border-orange-500/30 text-orange-300' },
                    { state: 'SPEAKING', color: 'bg-emerald-500/20 border-emerald-500/30 text-emerald-300' },
                  ].map((s, i) => (
                    <span key={s.state} className="flex items-center gap-2">
                      <span className={`px-4 py-2 rounded-lg border font-mono text-sm ${s.color}`}>
                        {s.state}
                      </span>
                      {i < 4 && <span className="text-gray-600 text-xl">→</span>}
                    </span>
                  ))}
                </div>
                <div className="mt-4 text-center">
                  <span className="px-4 py-2 rounded-lg border bg-red-500/20 border-red-500/30 text-red-300 font-mono text-sm">
                    ERROR
                  </span>
                  <span className="text-gray-500 ml-2 text-sm">(auto-recovery to IDLE)</span>
                </div>
              </div>
            </section>

            <section>
              <h2 className="text-2xl font-bold text-gray-100 mb-4">💫 Emotion System</h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { emotion: 'neutral', emoji: '😐', desc: 'Default state' },
                  { emotion: 'happy', emoji: '😊', desc: 'Pleased response' },
                  { emotion: 'excited', emoji: '😄', desc: 'Enthusiastic' },
                  { emotion: 'thinking', emoji: '🤔', desc: 'Processing' },
                  { emotion: 'surprised', emoji: '😲', desc: 'Unexpected' },
                  { emotion: 'sad', emoji: '😢', desc: 'Sympathetic' },
                  { emotion: 'angry', emoji: '😠', desc: 'Frustrated' },
                  { emotion: 'sleepy', emoji: '😴', desc: 'Tired' },
                ].map((e) => (
                  <div key={e.emotion} className="bg-gray-900 border border-gray-800 rounded-lg p-3 text-center">
                    <div className="text-3xl mb-1">{e.emoji}</div>
                    <div className="text-sm font-mono text-gray-300">[{e.emotion}]</div>
                    <div className="text-xs text-gray-500">{e.desc}</div>
                  </div>
                ))}
              </div>
            </section>
          </div>
        )}

        {activeTab === 'installation' && (
          <div className="space-y-8">
            <section>
              <h2 className="text-2xl font-bold text-gray-100 mb-4">📦 Installation Guide</h2>
              
              <div className="space-y-6">
                <div>
                  <h3 className="text-lg font-semibold text-gray-200 mb-2">1. System Dependencies</h3>
                  <CodeBlock id="sys-deps" code={`sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip \\
    portaudio19-dev libsndfile1 ffmpeg \\
    libgl1-mesa-glx libglib2.0-0 \\
    cmake build-essential`} />
                </div>

                <div>
                  <h3 className="text-lg font-semibold text-gray-200 mb-2">2. Python Environment</h3>
                  <CodeBlock id="py-env" code={`cd ai_vtuber
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt`} />
                </div>

                <div>
                  <h3 className="text-lg font-semibold text-gray-200 mb-2">3. KittenTTS (Important!)</h3>
                  <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
                    <p className="text-gray-300 text-sm">The PyPI <code className="bg-gray-800 px-1 rounded">kittentts</code> package only has v0.1.x. For the full v0.8.x API, install from GitHub:</p>
                    <CodeBlock id="kittentts-install" code={`# Option A: Official 0.8.x (recommended)
pip install https://github.com/KittenML/KittenTTS/releases/download/0.8.1/kittentts-0.8.1-py3-none-any.whl

# Option B: PyPI 0.1.x (fallback - auto-detected)
pip install kittentts`} />
                  </div>
                </div>

                <div>
                  <h3 className="text-lg font-semibold text-gray-200 mb-2">4. LM Studio Setup</h3>
                  <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-2">
                    <p className="text-gray-300">1. Download <a href="https://lmstudio.ai/" className="text-purple-400 hover:underline">LM Studio</a></p>
                    <p className="text-gray-300">2. Download Gemma 4 E4B GGUF model</p>
                    <p className="text-gray-300">3. Start local server (default: <code className="bg-gray-800 px-1 rounded">http://localhost:1234</code>)</p>
                    <p className="text-gray-300">4. Enable OpenAI-compatible API</p>
                  </div>
                </div>

                <div>
                  <h3 className="text-lg font-semibold text-gray-200 mb-2">5. Live2D Model</h3>
                  <p className="text-gray-400 mb-2">Place your Live2D model files and update <code className="bg-gray-800 px-1 rounded">config.yaml</code>:</p>
                  <CodeBlock id="model-config" lang="yaml" code={`avatar:
  model_path: "/path/to/your/model.model3.json"`} />
                </div>

                <div>
                  <h3 className="text-lg font-semibold text-gray-200 mb-2">6. Run</h3>
                  <CodeBlock id="run" code={`cd ai_vtuber
source venv/bin/activate
python main.py

# With debug logging:
python main.py --debug

# With custom config:
python main.py --config custom.yaml`} />
                </div>
              </div>
            </section>

            <section>
              <h2 className="text-2xl font-bold text-gray-100 mb-4">⌨️ Keyboard Shortcuts</h2>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {[
                  { key: 'ESC', action: 'Quit application' },
                  { key: 'F', action: 'Toggle FPS display' },
                  { key: 'D', action: 'Toggle debug info' },
                ].map((shortcut) => (
                  <div key={shortcut.key} className="flex items-center gap-3 bg-gray-900 border border-gray-800 rounded-lg p-3">
                    <kbd className="px-2 py-1 bg-gray-800 border border-gray-600 rounded text-sm font-mono text-gray-200">
                      {shortcut.key}
                    </kbd>
                    <span className="text-sm text-gray-400">{shortcut.action}</span>
                  </div>
                ))}
              </div>
            </section>
          </div>
        )}

        {activeTab === 'configuration' && (
          <div className="space-y-8">
            <section>
              <h2 className="text-2xl font-bold text-gray-100 mb-4">⚙️ Configuration Reference</h2>
              <p className="text-gray-400 mb-4">All settings are in <code className="bg-gray-800 px-1 rounded">config.yaml</code>. Nothing is hardcoded.</p>
              
              <CodeBlock id="full-config" lang="yaml" code={`# AI VTuber Configuration

# LLM Settings (LM Studio OpenAI-compatible API)
llm:
  base_url: "http://localhost:1234/v1"
  model: "gemma-4-e4b"
  temperature: 0.8
  max_tokens: 300
  max_history: 10
  system_prompt: |
    You are a friendly AI VTuber assistant...

# STT Settings (faster-whisper)
stt:
  model_size: "small"     # tiny, base, small, medium, large-v3
  device: "auto"          # auto, cuda, cpu
  compute_type: "auto"    # auto, float16, int8, float32
  language: "en"
  beam_size: 5
  vad_threshold: 0.5
  silence_duration: 1.5
  min_speech_duration: 0.3
  sample_rate: 16000

# TTS Settings (KittenTTS)
tts:
  model: "KittenML/kitten-tts-mini-0.8"
  voice: "Bella"          # Bella, Jasper, Luna, Bruno, Rosie, Hugo, Kiki, Leo
  speed: 1.0
  backend: "cpu"          # cpu or cuda
  sample_rate: 24000

# Avatar Settings (Live2D via live2d-py)
avatar:
  model_path: ""          # Path to .model3.json
  window_width: 800
  window_height: 600
  fps: 30
  scale: 2.0
  expressions:
    neutral: "neutral"
    happy: "happy"
    excited: "happy"
    thinking: "neutral"
    surprised: "surprised"
    sad: "sad"
    angry: "angry"
    sleepy: "sleepy"

# Audio Settings
audio:
  microphone_index: -1    # -1 for default
  chunk_size: 1024
  channels: 1
  mute_during_playback: true

# UI Settings
ui:
  show_fps: true
  show_debug: true
  background_color: [30, 30, 40]
  text_color: [255, 255, 255]
  font_size: 14`} />
            </section>

            <section>
              <h2 className="text-2xl font-bold text-gray-100 mb-4">🔧 Key Settings Explained</h2>
              <div className="space-y-4">
                {[
                  {
                    setting: 'stt.model_size',
                    desc: 'Whisper model size. Larger = more accurate but slower. "small" is a good balance for RTX 3050.',
                    options: ['tiny', 'base', 'small', 'medium', 'large-v3']
                  },
                  {
                    setting: 'stt.device',
                    desc: '"auto" detects CUDA. Set to "cpu" if you have GPU memory issues.',
                    options: ['auto', 'cuda', 'cpu']
                  },
                  {
                    setting: 'tts.voice',
                    desc: 'KittenTTS voice name. 8 built-in voices available.',
                    options: ['Bella', 'Jasper', 'Luna', 'Bruno', 'Rosie', 'Hugo', 'Kiki', 'Leo']
                  },
                  {
                    setting: 'llm.max_history',
                    desc: 'Number of messages kept in conversation context. Higher = more context but slower.',
                    options: ['5', '10', '15', '20']
                  },
                ].map((item) => (
                  <div key={item.setting} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                    <code className="text-purple-300 font-mono text-sm">{item.setting}</code>
                    <p className="text-gray-400 text-sm mt-1">{item.desc}</p>
                    <div className="flex flex-wrap gap-1 mt-2">
                      {item.options.map((opt) => (
                        <span key={opt} className="px-2 py-0.5 bg-gray-800 rounded text-xs text-gray-300 font-mono">
                          {opt}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </div>
        )}

        {activeTab === 'code' && (
          <div className="space-y-8">
            <section>
              <h2 className="text-2xl font-bold text-gray-100 mb-4">💻 Key Source Files</h2>
              <p className="text-gray-400 mb-6">
                The complete Python source code is in the <code className="bg-gray-800 px-1 rounded">ai_vtuber/</code> directory. 
                Below are the key interfaces and modules.
              </p>

              <div className="space-y-6">
                <div>
                  <h3 className="text-lg font-semibold text-gray-200 mb-2">🎭 Avatar Interface</h3>
                  <CodeBlock id="avatar-api" lang="python" code={`from avatar.live2d import Live2DAvatar

avatar = Live2DAvatar(config["avatar"])
avatar.gl_init()
avatar.resize(800, 600)

# Set expression based on emotion
avatar.set_expression("happy")
avatar.set_expression("neutral")

# Control talking animation (lip sync)
avatar.set_talking(True)   # Start mouth animation
avatar.set_talking(False)  # Stop mouth animation

# Update & draw each frame
avatar.update(delta_time)  # Updates blink, lip sync
avatar.draw()              # Renders to OpenGL context`} />
                </div>

                <div>
                  <h3 className="text-lg font-semibold text-gray-200 mb-2">🧠 LLM Client</h3>
                  <CodeBlock id="llm-api" lang="python" code={`from llm.lmstudio import LMStudioClient

llm = LMStudioClient(config["llm"])
messages = [
    {"role": "system", "content": "You are a friendly AI VTuber..."},
    {"role": "user", "content": "Hello!"}
]
response = llm.chat(messages)
# Returns: "[happy]\\nHi there! Nice to meet you!"`} />
                </div>

                <div>
                  <h3 className="text-lg font-semibold text-gray-200 mb-2">🎤 STT Module (CUDA via CTranslate2)</h3>
                  <CodeBlock id="stt-api" lang="python" code={`from stt.whisper import WhisperSTT
import numpy as np

stt = WhisperSTT(config["stt"])
# audio_data: float32 numpy array at 16kHz
text = stt.transcribe(audio_data)
# Returns: "Hello, how are you?"`} />
                </div>

                <div>
                  <h3 className="text-lg font-semibold text-gray-200 mb-2">🔊 TTS Module</h3>
                  <CodeBlock id="tts-api" lang="python" code={`from tts.kitten import KittenTTS
import numpy as np

tts = KittenTTS(config["tts"])
audio = tts.generate("Hello! Nice to meet you!")
# Returns: numpy array (float32, 24kHz)
# Voices: Bella, Jasper, Luna, Bruno, Rosie, Hugo, Kiki, Leo`} />
                </div>

                <div>
                  <h3 className="text-lg font-semibold text-gray-200 mb-2">🔄 State Machine</h3>
                  <CodeBlock id="state-api" lang="python" code={`from core.state import State, StateMachine

sm = StateMachine()
print(sm.state)  # State.IDLE

sm.transition(State.LISTENING)  # True
sm.transition(State.THINKING)   # False (invalid from LISTENING)

# Register callbacks
sm.on_transition(lambda old, new: print(f"{old} -> {new}"))

# Error handling
sm.set_error("Connection lost")
sm.force_state(State.IDLE)  # Recovery`} />
                </div>

                <div>
                  <h3 className="text-lg font-semibold text-gray-200 mb-2">🗣️ Interruption System</h3>
                  <CodeBlock id="interrupt-api" lang="python" code={`# AudioPlayer supports interruption via callback
player.play(
    audio_data,
    interrupt_check=lambda: vad.is_speech(mic.read_chunk())
)

# When user speaks during playback:
# 1. interrupt_check() returns True
# 2. Playback stops immediately
# 3. Avatar stops talking animation
# 4. System returns to LISTENING state
# 5. New speech is processed`} />
                </div>
              </div>
            </section>

            <section>
              <h2 className="text-2xl font-bold text-gray-100 mb-4">📋 Dependencies</h2>
              <CodeBlock id="requirements" lang="text" code={`# Core
pyyaml>=6.0
openai>=1.0.0
numpy>=1.24.0

# Audio
sounddevice>=0.4.6
soundfile>=0.12.0
webrtcvad>=2.0.10

# STT
faster-whisper>=1.0.0

# TTS
kittentts>=0.8.0

# Avatar (Live2D)
live2d-py>=0.7.0

# UI
pygame>=2.5.0`} />
            </section>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-800 mt-16">
        <div className="max-w-6xl mx-auto px-6 py-8">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="text-2xl">🎭</span>
              <span className="text-gray-400">AI VTuber — Fully local, privacy-first AI companion</span>
            </div>
            <div className="flex items-center gap-4 text-sm text-gray-500">
              <span>Python 3.11+</span>
              <span>•</span>
              <span>Ubuntu Linux</span>
              <span>•</span>
              <span>MIT License</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}

export default App
