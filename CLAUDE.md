# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Raspberry Pi Voice Processor - A complete voice processing system optimized for **Raspberry Pi Zero 2W** with **ReSpeaker HAT**. Captures audio, automatically transcribes with Whisper, generates summaries with LLM, and provides everything via a web interface.

**Primary target hardware**: Raspberry Pi Zero 2W (512MB RAM + 8-16GB swap), ReSpeaker 2-Mic or 4-Mic HAT

## Remote Debugging & Testing

When you need to test changes on the actual Raspberry Pi hardware or debug runtime errors:

### SSH Access
```bash
# Connect to Raspberry Pi
ssh bigfriend@192.168.31.124
# Password: Amlb3fyk#

# Navigate to project
cd ~/benchmarkarm

# Stop the service
./run.sh stop

# Pull latest changes from git
git pull

# Start the service
./run.sh start

# View logs in real-time
./run.sh logs

# Check status
./run.sh status
```

**When to use SSH debugging:**
- Testing hardware-specific features (ReSpeaker HAT, LEDs, buttons)
- Debugging runtime errors that only occur on Pi Zero 2W
- Verifying performance optimizations on low-memory device
- Testing whisper.cpp or llama.cpp compiled binaries
- After making significant configuration or code changes

**Workflow:**
1. Make code changes locally
2. Commit and push to git
3. SSH into Raspberry Pi
4. Pull changes and restart service
5. Monitor logs for errors
6. Fix issues and repeat

## Common Commands

### Installation & Setup
```bash
# Full installation (includes swap setup, whisper.cpp, llama.cpp)
./run.sh install --swap 16G

# Setup ReSpeaker HAT (on Raspberry Pi only)
./run.sh setup-audio

# Download models
./scripts/download_models.sh
```

### Running the Application
```bash
# Start web server (default: http://localhost:5000)
./run.sh start

# Stop server
./run.sh stop

# Check status
./run.sh status

# Test audio input
./run.sh test
```

### Development
```bash
# Activate virtual environment
source venv/bin/activate

# Run web server directly
python -m src.web.server

# Run tests
pytest tests/

# Configuration file
config/config.yaml  # Copy from config.example.yaml if missing
```

## Architecture Overview

The system follows a pipeline architecture with three main stages:

### 1. Audio Processing Layer (`src/audio/`)
- **AudioCapture** (`capture.py`): Handles ReSpeaker HAT or USB microphone input
- **VoiceActivityDetector** (`vad.py`): WebRTC-based VAD to detect speech segments
- **ContinuousListener** (`continuous_listener.py`): 24/7 background listening thread that detects voice and triggers processing

### 2. Transcription Layer (`src/transcription/`)
- **WhisperTranscriber** (`whisper.py`): Interface to whisper.cpp (compiled C++ version for ARM optimization)
- Uses GGML quantized models (tiny, base, small) stored in `external/whisper.cpp/models/`
- Fallback to Python whisper library if whisper.cpp unavailable

### 3. LLM Processing Layer (`src/llm/`)
- **LLMProvider** (`base.py`): Abstract base class for all LLM providers
- **LocalLLM** (`local.py`): Uses llama.cpp for local inference (TinyLlama, Phi-2, Gemma)
- **API Providers** (`api.py`): OpenAI, Anthropic, Ollama wrappers
- Models stored in `models/` directory as GGUF files

### 4. Web Interface (`src/web/`)
- **Flask server** (`server.py`): REST API + web interface
- **MemoryLogHandler**: Singleton log handler that stores recent logs in memory for web UI display
- Tabs: Home, Settings, Continuous Listen, Transcription, Models, Files

### 5. Batch Processing (`src/utils/batch_processor.py`)
- Automatically scans `~/audio-recordings` for `.wav` files
- Transcribes each file and saves as `.txt` with metadata
- Removes original `.wav` files after successful transcription (configurable via `keep_original_audio`)
- Can run periodically or be triggered manually via API

### 6. Hardware Integration (`src/hardware/`)
- **LED** (`led.py`): Controls ReSpeaker HAT APA102 LEDs via SPI
- **Button** (`button.py`): GPIO button handling for ReSpeaker HAT

### Core Pipeline (`src/pipeline.py`)
The **VoiceProcessor** class orchestrates the entire flow:
1. Audio capture → VAD → Whisper transcription → LLM processing
2. Integrates caching to avoid reprocessing
3. Returns **ProcessingResult** with transcription + optional summary

## Key Configuration

The system is configured via `config/config.yaml` (YAML format):

**Important toggles:**
- `mode`: "local", "api", or "hybrid" - determines LLM provider selection
- `whisper.use_cpp`: Use whisper.cpp (recommended) vs Python library
- `usb_receiver.auto_transcribe`: Auto-transcribe detected audio
- `usb_receiver.auto_summarize`: **LLM toggle** - enable/disable automatic summarization
- `usb_receiver.keep_original_audio`: Keep `.wav` files after transcription (default: false)
- `system.low_memory_mode`: Optimize for Pi Zero 2W constraints

## Resource Management

This codebase is optimized for extremely limited resources (512MB RAM):

1. **Lazy loading**: Components like transcriber and LLM are initialized only when needed
2. **Swap dependency**: Pi Zero 2W requires 8-16GB swap for LLM inference
3. **CPU throttling**: `src/utils/cpu_limiter.py` prevents thermal throttling
4. **Memory-efficient logs**: MemoryLogHandler uses deque with maxlen=200
5. **Process isolation**: Background processing uses threads to avoid blocking web UI

## External Dependencies

The project wraps two key C++ libraries (compiled locally):

1. **whisper.cpp** (`external/whisper.cpp/`):
   - Compiled with `cmake` for ARM optimization
   - Binary at `external/whisper.cpp/build/bin/main` or `whisper-cli`
   - Models downloaded to `external/whisper.cpp/models/`

2. **llama.cpp** (`external/llama.cpp/`):
   - Compiled with `cmake` for local LLM inference
   - Binary at `external/llama.cpp/build/bin/llama-cli` (or legacy `main`)
   - Uses GGUF quantized models from `models/` directory

## File Storage & Cleanup

**Audio recordings**: `~/audio-recordings/` (configurable)
**Transcription format** (`.txt` files):
```
# Transcrição: audio_20231223_101530.wav
# Data: 2023-12-23 10:15:30
# Timestamp: 2023-12-23T10:15:30.123456
# Duração: 45.2s
# Modelo: whisper-tiny
# Idioma: pt
# Tempo de processamento: 3.45s

[Transcribed text here]
```

**Automatic cleanup**: When `keep_original_audio: false`, `.wav` files are deleted after successful transcription to save disk space.

## API Endpoints

Key REST API routes (see `src/web/server.py`):

**Listener control:**
- `POST /api/listener/start` - Start continuous listening
- `POST /api/listener/stop` - Stop listening
- `GET /api/listener/status` - Get listener state
- `GET /api/listener/segments` - Get recent transcriptions

**Batch processing:**
- `POST /api/batch/run` - Process pending files now
- `POST /api/batch/start` - Start automatic batch processor
- `POST /api/batch/stop` - Stop batch processor
- `GET /api/batch/status` - Get batch processor state

**Model management:**
- `GET /api/models/status` - Check installed models
- `POST /api/models/download/whisper/<model>` - Download Whisper model
- `POST /api/models/download/llm/<model>` - Download LLM model

**Files:**
- `GET /api/files/transcriptions` - List all transcription files
- `GET /api/files/transcriptions/<file>` - Read specific transcription
- `DELETE /api/files/transcriptions/<file>` - Delete transcription
- `GET /api/files/search?q=<term>` - Search transcriptions

## Hardware-Specific Notes

**ReSpeaker HAT**: Requires specific driver setup via `scripts/setup_respeaker.sh`
- 2-Mic HAT: 3 APA102 LEDs, GPIO button on pin 17
- 4-Mic HAT: Similar but different LED configuration

**USB Gadget mode**: Pi Zero 2W can receive audio via USB from PC
- Setup: `sudo ./scripts/setup_usb_gadget.sh`
- Configured via `usb_receiver.usb_gadget_enabled: true`

**Performance expectations** (Pi Zero 2W):
- Whisper tiny: ~3-5s per 10s audio
- TinyLlama summary: ~5-8s per 200 words
- Total latency: ~8-15s for full pipeline

## Testing

Minimal test coverage in `tests/`:
- `test_config.py` - Configuration loading
- `test_cache.py` - Cache functionality

For audio testing: `./run.sh test` runs hardware validation

## Important Implementation Notes

1. **Singleton pattern**: `MemoryLogHandler` uses singleton to ensure single log buffer across app
2. **Thread safety**: ContinuousListener and BatchProcessor use threading locks for state management
3. **Resource locking**: Transcriber and LLM instances are shared/locked to prevent concurrent access on low-memory systems
4. **Error handling**: All components have `on_error` callbacks for graceful degradation
5. **Language**: Portuguese (pt-BR) - UI text, prompts, and default Whisper language
