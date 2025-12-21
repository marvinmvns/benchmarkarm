# 🎙️ Raspberry Pi Voice Processor

Sistema de processamento de voz otimizado para **Raspberry Pi Zero 2W** com **ReSpeaker HAT**.

## Características

- ✅ **Transcrição de voz** usando Whisper (whisper.cpp otimizado para ARM)
- ✅ **Resumo de textos** usando LLM local (TinyLlama/Phi) ou API externa
- ✅ **Super performático** - otimizado para hardware limitado (512MB RAM)
- ✅ **Configurável** - escolha modelos, APIs e parâmetros
- ✅ **VAD integrado** - detecção de atividade de voz
- ✅ **Cache inteligente** - reduz processamento redundante

## Hardware Suportado

- **Raspberry Pi Zero 2W** (principal)
- Raspberry Pi 3/4/5 (também compatível)
- **ReSpeaker 2-Mics Pi HAT** ou **ReSpeaker 4-Mic Array**

## Arquitetura

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   ReSpeaker     │────▶│   Whisper.cpp    │────▶│   LLM Engine    │
│   Audio Input   │     │   Transcription  │     │   Summarization │
└─────────────────┘     └──────────────────┘     └─────────────────┘
         │                       │                        │
         ▼                       ▼                        ▼
    ┌─────────┐           ┌───────────┐           ┌─────────────┐
    │   VAD   │           │   Cache   │           │  Local/API  │
    └─────────┘           └───────────┘           └─────────────┘
```

## Instalação Rápida

```bash
# Clone o repositório
git clone https://github.com/seu-usuario/raspberry-voice-processor.git
cd raspberry-voice-processor

# Execute o script de instalação
chmod +x scripts/install.sh
./scripts/install.sh

# Configure
cp config/config.example.yaml config/config.yaml
nano config/config.yaml

# Execute
python3 src/main.py
```

## Configuração

Edite `config/config.yaml`:

```yaml
# Modo de operação
mode: "local"  # local, api, hybrid

# Whisper
whisper:
  model: "tiny"  # tiny, base, small (tiny recomendado para Pi Zero 2W)
  language: "pt"

# LLM
llm:
  provider: "local"  # local, openai, anthropic
  local_model: "tinyllama"

# Áudio
audio:
  sample_rate: 16000
  channels: 1
  vad_enabled: true
```

## Modos de Operação

### 1. Local (Offline)
Todo processamento no dispositivo. Mais lento, mas sem dependência de internet.

### 2. API (Online)
Usa APIs externas (OpenAI, Anthropic). Mais rápido e preciso.

### 3. Híbrido
Transcrição local + LLM via API (melhor custo-benefício).

## Performance

| Componente | Pi Zero 2W | Pi 4 |
|------------|------------|------|
| Whisper tiny | ~3s/10s áudio | ~0.5s/10s |
| TinyLlama | ~5s/100 tokens | ~1s/100 tokens |
| Latência total | ~8-10s | ~2-3s |

## Estrutura do Projeto

```
├── src/
│   ├── main.py              # Ponto de entrada
│   ├── audio/               # Captura e processamento de áudio
│   │   ├── capture.py       # Captura do ReSpeaker
│   │   └── vad.py          # Detecção de atividade de voz
│   ├── transcription/       # Transcrição
│   │   └── whisper.py      # Interface Whisper
│   ├── llm/                 # Modelos de linguagem
│   │   ├── base.py         # Interface base
│   │   ├── local.py        # LLM local (llama.cpp)
│   │   └── api.py          # APIs externas
│   └── utils/               # Utilitários
│       ├── config.py       # Gerenciamento de config
│       └── cache.py        # Sistema de cache
├── config/
│   └── config.yaml         # Configuração principal
├── scripts/
│   ├── install.sh          # Instalação automática
│   └── setup_respeaker.sh  # Setup do ReSpeaker HAT
└── tests/                   # Testes
```

## Licença

MIT License
