#!/bin/bash
# =============================================================================
# Raspberry Pi Voice Processor - Script de Instalação
# Otimizado para Raspberry Pi Zero 2W com ReSpeaker HAT
# =============================================================================

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Detectar arquitetura
ARCH=$(uname -m)
IS_PI=false
IS_PI_ZERO=false

if [[ "$ARCH" == "aarch64" ]] || [[ "$ARCH" == "armv7l" ]] || [[ "$ARCH" == "armv6l" ]]; then
    IS_PI=true
    if grep -q "Zero 2" /proc/device-tree/model 2>/dev/null; then
        IS_PI_ZERO=true
        log_info "Detectado: Raspberry Pi Zero 2W"
    else
        log_info "Detectado: Raspberry Pi (ARM)"
    fi
else
    log_warn "Não é Raspberry Pi. Algumas funcionalidades podem não estar disponíveis."
fi

# Diretório do projeto
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

log_info "=== Instalação do Raspberry Pi Voice Processor ==="
log_info "Diretório: $PROJECT_DIR"

# Atualizar sistema
log_info "Atualizando sistema..."
sudo apt-get update -qq

# Instalar dependências do sistema
log_info "Instalando dependências do sistema..."
sudo apt-get install -y -qq \
    python3-pip \
    python3-venv \
    python3-dev \
    portaudio19-dev \
    libsndfile1 \
    libffi-dev \
    libasound2-dev \
    libatlas-base-dev \
    git \
    cmake \
    build-essential \
    wget \
    curl

# Criar ambiente virtual
log_info "Criando ambiente virtual Python..."
python3 -m venv venv
source venv/bin/activate

# Atualizar pip
pip install --upgrade pip wheel setuptools -q

# Instalar dependências Python
log_info "Instalando dependências Python..."
pip install -r requirements.txt -q

# Instalar whisper.cpp para ARM
log_info "Instalando whisper.cpp..."
WHISPER_CPP_DIR="$PROJECT_DIR/external/whisper.cpp"
if [ ! -d "$WHISPER_CPP_DIR" ]; then
    mkdir -p "$PROJECT_DIR/external"
    git clone --depth 1 https://github.com/ggerganov/whisper.cpp.git "$WHISPER_CPP_DIR"
    cd "$WHISPER_CPP_DIR"

    # Compilar com otimizações para ARM
    if $IS_PI; then
        log_info "Compilando whisper.cpp para ARM..."
        if $IS_PI_ZERO; then
            # Pi Zero 2W - Cortex-A53
            make clean
            CFLAGS="-mcpu=cortex-a53 -mfpu=neon-fp-armv8 -O3" make -j2
        else
            # Pi 3/4/5
            make clean
            CFLAGS="-O3" make -j4
        fi
    else
        make -j$(nproc)
    fi

    # Baixar modelo tiny
    log_info "Baixando modelo Whisper tiny..."
    bash models/download-ggml-model.sh tiny

    cd "$PROJECT_DIR"
    log_success "whisper.cpp instalado"
else
    log_info "whisper.cpp já instalado"
fi

# Instalar llama.cpp para LLM local
log_info "Instalando llama.cpp..."
LLAMA_CPP_DIR="$PROJECT_DIR/external/llama.cpp"
if [ ! -d "$LLAMA_CPP_DIR" ]; then
    git clone --depth 1 https://github.com/ggerganov/llama.cpp.git "$LLAMA_CPP_DIR"
    cd "$LLAMA_CPP_DIR"

    if $IS_PI; then
        log_info "Compilando llama.cpp para ARM..."
        if $IS_PI_ZERO; then
            make clean
            CFLAGS="-mcpu=cortex-a53 -O3" make -j2
        else
            make clean
            make -j4
        fi
    else
        make -j$(nproc)
    fi

    cd "$PROJECT_DIR"
    log_success "llama.cpp instalado"
else
    log_info "llama.cpp já instalado"
fi

# Criar diretórios necessários
mkdir -p models logs cache

# Setup ReSpeaker (se disponível)
if $IS_PI; then
    log_info "Configurando ReSpeaker HAT..."
    bash scripts/setup_respeaker.sh || log_warn "ReSpeaker setup pode precisar de reinício"
fi

# Baixar modelo TinyLlama (opcional, perguntar)
log_info ""
read -p "Deseja baixar o modelo TinyLlama (~700MB)? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log_info "Baixando TinyLlama quantizado..."
    TINYLLAMA_URL="https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
    wget -q --show-progress -O models/tinyllama-1.1b-q4.gguf "$TINYLLAMA_URL" || log_warn "Falha ao baixar TinyLlama"
fi

# Criar arquivo de configuração se não existir
if [ ! -f "config/config.yaml" ]; then
    cp config/config.example.yaml config/config.yaml
    log_info "Arquivo de configuração criado: config/config.yaml"
fi

# Mensagem final
log_success "=== Instalação concluída! ==="
echo ""
log_info "Para usar:"
echo "  1. Ative o ambiente virtual: source venv/bin/activate"
echo "  2. Configure: nano config/config.yaml"
echo "  3. Execute: python3 src/main.py"
echo ""
log_info "Para modo contínuo: python3 src/main.py --continuous"
log_info "Para teste rápido: python3 src/main.py --test"
