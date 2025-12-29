# 🎙️ Raspberry Pi Voice Processor

Sistema completo de processamento de voz otimizado para **Raspberry Pi Zero 2W** com **ReSpeaker HAT**.
Captura áudio 24/7, transcreve com Whisper, e salva automaticamente em JSON/TXT.

---

## ✨ Características Principais

- 🎧 **Escuta Contínua 24/7** - Captura e transcreve áudio automaticamente
- 📝 **Transcrição com Whisper** - Via API distribuída ou whisper.cpp local
- 🔄 **5 Servidores WhisperAPI** - Balanceamento Round Robin automático
- 🔌 **Fallback Local** - Continua funcionando offline com whisper.cpp
- 💾 **Persistência Total** - Áudios salvos em disco, sobrevive a reinício/queda de energia
- 🔄 **Recuperação Automática** - Jobs pendentes reprocessados ao reiniciar
- 🌐 **Interface Web** - Controle completo via navegador
- ⚡ **Super Otimizado** - Funciona com 512MB RAM + swap

---

## 🚀 Início Rápido

```bash
# Clone e instale
git clone https://github.com/marvinmvns/benchmarkarm.git
cd benchmarkarm
./run.sh install --swap 16G

# Inicie
./run.sh start

# Acesse: http://seu-raspberry:8080
```

---

## 🏗️ Arquitetura

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  🎤 Áudio   │────▶│  WhisperAPI (5x) │────▶│  💾 Persistência │
│  ReSpeaker  │     │  Round Robin     │     │  JSON/TXT/SQLite │
└─────────────┘     └──────────────────┘     └─────────────────┘
       │                    │                        │
       ▼                    ▼                        ▼
  ┌─────────┐        ┌────────────┐          ┌───────────────┐
  │   VAD   │        │  Fallback  │          │  🌐 Web API   │
  │ (info)  │        │whisper.cpp │          │    :8080      │
  └─────────┘        └────────────┘          └───────────────┘
```

---

## 🔧 Configuração Principal

```yaml
# config/config.yaml

whisper:
  provider: whisperapi          # whisperapi, local
  model: large-v3
  language: pt
  whisperapi_url: http://192.168.31.121:3001
  whisperapi_urls:              # Lista para Round Robin
    - http://192.168.31.121:3001
    - http://192.168.31.120:3001
    - http://192.168.31.110:3001
    - http://192.168.31.101:3001
    - http://192.168.31.100:3001

usb_receiver:
  enabled: true
  continuous_listen: true
  use_ram_storage: false        # false = disco (persistente)
  save_directory: ~/audio-recordings
  auto_transcribe: true
  min_audio_duration: 3
  max_audio_duration: 10
```

---

## 🌐 API REST

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/api/listener/start` | POST | Iniciar escuta contínua |
| `/api/listener/stop` | POST | Parar escuta |
| `/api/listener/status` | GET | Status da escuta |
| `/api/batch/status` | GET | Status do processador batch |
| `/api/batch/run` | POST | Processar arquivos pendentes |
| `/api/jobs/stats` | GET | Estatísticas do JobManager |
| `/api/jobs/servers` | GET | Status dos servidores WhisperAPI |
| `/api/jobs/recover` | POST | Recuperar jobs pendentes |
| `/api/config` | GET/POST | Configuração |
| `/api/logs` | GET | Logs da aplicação |

---

## 💾 Persistência e Recuperação

### Arquivos Gerados

| Tipo | Local | Descrição |
|------|-------|-----------|
| **WAV** | `~/audio-recordings/` | Áudio temporário (removido após transcrição) |
| **JSON** | `~/.cache/voice-processor/` | Cache de transcrições |
| **TXT Diário** | `~/audio-recordings/daily/` | Consolidação diária |
| **SQLite** | `~/.cache/voice-processor/transcriptions.db` | Banco de dados persistente |

### Recuperação Automática

Ao reiniciar (mesmo após queda de energia):
1. ✅ Jobs pendentes do JobManager são recuperados
2. ✅ Arquivos WAV não processados são transcritos
3. ✅ ProcessamentoPeriódicominicia automaticamente (a cada 5 min)

---

## 🔄 Fallback Local

Quando todos os servidores WhisperAPI falham:

```
⚠️ Todos os 5 servidores API falharam. Tentando fallback para whisper.cpp local...
✅ Fallback local bem-sucedido! (159.2s)
```

O sistema usa `whisper.cpp` com modelo `ggml-tiny.bin` (~2.5 min por transcrição).

---

## 📊 Status dos Servidores

```bash
# Ver status dos servidores WhisperAPI
curl http://raspberry:8080/api/jobs/servers | jq
```

Resposta:
```json
{
  "servers": [
    {"url": "http://192.168.31.121:3001", "healthy": true, "active_jobs": 0},
    {"url": "http://192.168.31.120:3001", "healthy": true, "active_jobs": 1},
    ...
  ],
  "total": 5
}
```

---

## 🖥️ Hardware Suportado

| Dispositivo | Status |
|-------------|--------|
| Raspberry Pi Zero 2W | ✅ Principal (swap 8-16GB) |
| Raspberry Pi 3B/3B+ | ✅ Compatível |
| Raspberry Pi 4/5 | ✅ Recomendado |
| ReSpeaker 2-Mics HAT | ✅ Suportado |

---

## 📁 Estrutura

```
benchmarkarm/
├── config/config.yaml       # Configuração principal
├── src/
│   ├── audio/
│   │   ├── capture.py       # Captura de áudio
│   │   ├── continuous_listener.py  # Escuta contínua 24/7
│   │   └── vad.py           # Detecção de voz (informativo)
│   ├── transcription/
│   │   ├── whisper.py       # WhisperAPI + fallback local
│   │   └── job_manager.py   # Gerenciamento de jobs
│   ├── utils/
│   │   ├── batch_processor.py   # Processador em lote
│   │   └── transcription_store.py  # Persistência
│   └── web/
│       └── server.py        # API Flask
└── external/
    └── whisper.cpp/         # Fallback local
```

---

## 🔧 Scripts

```bash
./run.sh install    # Instalação completa
./run.sh start      # Iniciar servidor
./run.sh stop       # Parar servidor
./run.sh logs       # Ver logs
./run.sh status     # Ver status
```

---

## 📄 Licença

MIT License

---

<p align="center">
  Feito com ❤️ para Raspberry Pi
</p>
