# 🎙️ Raspberry Pi Voice Processor

Sistema completo de processamento de voz otimizado para **Raspberry Pi Zero 2W** com **ReSpeaker HAT**.
Captura áudio, transcreve automaticamente com Whisper, gera resumos com LLM e disponibiliza tudo via interface web.

---

## ✨ Características Principais

- 🎧 **Escuta Contínua 24/7** - Captura e transcreve áudio automaticamente
- 📝 **Transcrição com Whisper** - whisper.cpp otimizado para ARM
- 🤖 **Resumo com LLM** - TinyLlama/Phi-2 local ou APIs externas
- 📂 **Gerenciamento de Arquivos** - Salva transcrições como .txt e remove .wav automaticamente
- 🌐 **Interface Web** - Controle completo via navegador
- ⚡ **Super Otimizado** - Funciona com apenas 512MB RAM + swap
- 🔌 **Modo Offline** - Funciona sem internet

---

## 🖥️ Hardware Suportado

| Dispositivo | Status | Observações |
|-------------|--------|-------------|
| **Raspberry Pi Zero 2W** | ✅ Principal | Requer swap de 8-16GB |
| Raspberry Pi 3B/3B+ | ✅ Compatível | Melhor performance |
| Raspberry Pi 4/5 | ✅ Compatível | Recomendado para modelos maiores |
| ReSpeaker 2-Mics HAT | ✅ Suportado | Recomendado |
| ReSpeaker 4-Mic Array | ✅ Suportado | Alternativa |
| Microfone USB | ✅ Suportado | Funciona sem HAT |

---

## 🏗️ Arquitetura

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   🎤 Áudio      │────▶│   Whisper.cpp    │────▶│   LLM Engine    │
│   (ReSpeaker)   │     │   Transcrição    │     │   Resumo        │
└─────────────────┘     └──────────────────┘     └─────────────────┘
         │                       │                        │
         ▼                       ▼                        ▼
    ┌─────────┐           ┌───────────┐           ┌─────────────┐
    │   VAD   │           │ .txt File │           │  Local/API  │
    └─────────┘           └───────────┘           └─────────────┘
                                │
                                ▼
                    ┌─────────────────────┐
                    │  🌐 Interface Web   │
                    │  (Flask + REST API) │
                    └─────────────────────┘
```

---

## 🚀 Instalação

### Instalação Rápida (Recomendado)

```bash
# Clone o repositório
git clone https://github.com/marvinmvns/benchmarkarm.git
cd benchmarkarm

# Execute o instalador (configura swap, whisper.cpp, llama.cpp)
chmod +x run.sh
./run.sh install --swap 16G

# Inicie o servidor web
./run.sh start
```

### Instalação Manual

```bash
# 1. Dependências do sistema
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv portaudio19-dev \
    libsndfile1 git cmake build-essential

# 2. Ambiente virtual Python
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Compilar whisper.cpp
cd external
git clone https://github.com/ggerganov/whisper.cpp.git
cd whisper.cpp && mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j2
cd ../../..

# 4. Compilar llama.cpp (opcional, para resumos locais)
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp && mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF
make -j2
cd ../../..

# 5. Configurar
cp config/config.example.yaml config/config.yaml

# 6. Iniciar
python -m src.web.server
```

---

## 🌐 Interface Web

Acesse `http://seu-raspberry:5000` no navegador.

### Abas Disponíveis

| Aba | Função |
|-----|--------|
| **🏠 Início** | Status do sistema, informações de hardware |
| **⚙️ Configurações** | Todas as configurações da aplicação |
| **🎧 Escuta Contínua** | Controles de escuta, transcrições em tempo real |
| **📝 Transcrição** | Transcrição manual de arquivos/gravação |
| **📦 Modelos** | Gerenciador de modelos Whisper e LLM |
| **📂 Arquivos** | Lista de transcrições salvas, busca, visualização |

---

## ⚙️ Configuração

### Arquivo `config/config.yaml`

```yaml
# Modo de operação: local, api, hybrid
mode: "local"

# Whisper (Transcrição)
whisper:
  model: "tiny"           # tiny, base, small
  language: "pt"          # Idioma
  use_cpp: true           # Usar whisper.cpp (recomendado)
  threads: 4

# LLM (Resumos)
llm:
  provider: "local"       # local, openai, anthropic, ollama
  local:
    model: "tinyllama"    # tinyllama, phi2, gemma2b

# Escuta Contínua
usb_receiver:
  enabled: true
  save_directory: "~/audio-recordings"
  auto_transcribe: true   # Transcrever automaticamente
  auto_summarize: true    # Gerar resumos (toggle de LLM)
  auto_start: false       # Iniciar escuta ao abrir
  auto_process: false     # Processar arquivos pendentes automaticamente
  keep_original_audio: false  # Manter .wav (false = remove após transcrição)
```

### Funcionalidades Configuráveis

| Configuração | Descrição |
|--------------|-----------|
| `auto_transcribe` | Transcreve áudio automaticamente quando detectado |
| `auto_summarize` | **Toggle de LLM** - Gera resumos usando LLM local/API |
| `auto_start` | Inicia a escuta automaticamente quando a aplicação abre |
| `auto_process` | Inicia o processador em lote automaticamente |
| `keep_original_audio` | Se `false`, remove `.wav` após transcrever para `.txt` |

---

## 📂 Processamento em Lote

O sistema processa arquivos `.wav` automaticamente:

1. **Escaneia** `~/audio-recordings` por arquivos `.wav`
2. **Transcreve** cada arquivo com Whisper
3. **Salva** resultado como `.txt` com metadados
4. **Remove** o `.wav` original para economizar espaço

### Formato do Arquivo `.txt`

```txt
# Transcrição: audio_20231223_101530.wav
# Data: 2023-12-23 10:15:30
# Timestamp: 2023-12-23T10:15:30.123456
# Duração: 45.2s
# Modelo: whisper-tiny
# Idioma: pt
# Tempo de processamento: 3.45s

[Texto transcrito aqui]
```

### Controle via API

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/api/batch/status` | GET | Status do processador |
| `/api/batch/run` | POST | Executar processamento agora |
| `/api/batch/start` | POST | Iniciar processamento automático |
| `/api/batch/stop` | POST | Parar processamento automático |

---

## 📦 Modelos

### Modelos Whisper (Transcrição)

| Modelo | Tamanho | RAM | Velocidade |
|--------|---------|-----|------------|
| **tiny** | 75 MB | ~200 MB | ~3s/10s áudio |
| base | 140 MB | ~400 MB | ~5s/10s áudio |
| small | 460 MB | ~1 GB | ~15s/10s áudio |

### Modelos LLM (Resumos)

| Modelo | Tamanho | RAM/Swap | Velocidade |
|--------|---------|----------|------------|
| **TinyLlama 1.1B** | 670 MB | ~2 GB | ~5s/100 tokens |
| Phi-2 2.7B | 1.6 GB | ~4 GB | ~10s/100 tokens |
| Gemma 2B | 1.5 GB | ~4 GB | ~8s/100 tokens |

### Download de Modelos

Acesse a aba **📦 Modelos** na interface web e clique em "📥 Baixar" no modelo desejado.

---

## 🔧 Scripts Úteis

```bash
# Comandos principais
./run.sh install          # Instalação completa
./run.sh start            # Iniciar servidor web
./run.sh stop             # Parar servidor
./run.sh status           # Ver status
./run.sh test             # Testar áudio

# Scripts específicos
./scripts/setup_respeaker.sh   # Configurar ReSpeaker HAT
./scripts/setup_usb_gadget.sh  # Modo USB Gadget
./scripts/download_models.sh   # Baixar modelos
```

---

## 📊 Performance

### Raspberry Pi Zero 2W (com swap de 16GB)

| Operação | Tempo |
|----------|-------|
| Transcrição 10s áudio (tiny) | ~3-5s |
| Resumo 200 palavras (TinyLlama) | ~5-8s |
| Latência total | ~8-15s |

### Raspberry Pi 4 (4GB RAM)

| Operação | Tempo |
|----------|-------|
| Transcrição 10s áudio (tiny) | ~0.5s |
| Resumo 200 palavras (TinyLlama) | ~1-2s |
| Latência total | ~2-3s |

---

## 📁 Estrutura do Projeto

```
benchmarkarm/
├── config/
│   ├── config.yaml           # Configuração principal
│   └── config.example.yaml   # Exemplo de configuração
├── external/
│   ├── whisper.cpp/          # Whisper compilado para ARM
│   └── llama.cpp/            # LLama.cpp para LLM local
├── models/                   # Modelos LLM (.gguf)
├── scripts/
│   ├── install.sh            # Instalação automática
│   ├── setup_respeaker.sh    # Setup ReSpeaker HAT
│   ├── setup_usb_gadget.sh   # Setup USB Gadget
│   └── download_models.sh    # Download de modelos
├── src/
│   ├── audio/
│   │   ├── capture.py        # Captura de áudio
│   │   ├── continuous_listener.py  # Escuta contínua
│   │   └── vad.py            # Detecção de voz
│   ├── llm/
│   │   ├── local.py          # LLM local (llama.cpp)
│   │   └── api.py            # APIs externas
│   ├── transcription/
│   │   └── whisper.py        # Interface Whisper
│   ├── utils/
│   │   ├── config.py         # Gerenciamento de config
│   │   ├── cache.py          # Sistema de cache
│   │   └── batch_processor.py # Processador em lote
│   └── web/
│       ├── server.py         # Servidor Flask
│       ├── templates/        # HTML
│       └── static/           # CSS/JS
├── run.sh                    # Script principal
└── requirements.txt          # Dependências Python
```

---

## 🔌 API REST

### Endpoints Principais

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/api/listener/start` | POST | Iniciar escuta contínua |
| `/api/listener/stop` | POST | Parar escuta |
| `/api/listener/status` | GET | Status da escuta |
| `/api/listener/segments` | GET | Transcrições recentes |
| `/api/models/status` | GET | Status dos modelos |
| `/api/models/download/whisper/<model>` | POST | Baixar modelo Whisper |
| `/api/models/download/llm/<model>` | POST | Baixar modelo LLM |
| `/api/files/transcriptions` | GET | Listar transcrições |
| `/api/files/transcriptions/<file>` | GET | Ler transcrição |
| `/api/files/transcriptions/<file>` | DELETE | Deletar transcrição |
| `/api/files/search?q=termo` | GET | Buscar nas transcrições |
| `/api/config` | GET/POST | Ler/salvar configuração |

---

## ❓ Troubleshooting

### "Módulos de áudio não disponíveis"
```bash
# Verificar se PyAudio está instalado
pip install pyaudio
# Se falhar, instalar dependências
sudo apt-get install portaudio19-dev
```

### "llama.cpp não encontrado"
```bash
# Verificar se foi compilado
ls external/llama.cpp/build/bin/
# Deve ter: llama-cli ou main
```

### Swap insuficiente para LLM
```bash
# Aumentar swap
sudo swapoff /swapfile
sudo dd if=/dev/zero of=/swapfile bs=1M count=16384
sudo mkswap /swapfile
sudo swapon /swapfile
```

### Modelo não aparece como instalado
```bash
# Verificar arquivos de modelo
ls -la models/
ls -la external/whisper.cpp/models/
```

---

## 📄 Licença

MIT License - Veja [LICENSE](LICENSE) para detalhes.

---

## 🤝 Contribuindo

1. Fork o projeto
2. Crie sua branch (`git checkout -b feature/nova-feature`)
3. Commit suas mudanças (`git commit -m 'Add nova feature'`)
4. Push para a branch (`git push origin feature/nova-feature`)
5. Abra um Pull Request

---

## 📞 Suporte

- **Issues**: [GitHub Issues](https://github.com/marvinmvns/benchmarkarm/issues)
- **Documentação**: Este README

---

<p align="center">
  Feito com ❤️ para Raspberry Pi
</p>
