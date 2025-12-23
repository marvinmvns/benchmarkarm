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

# Parâmetros de linha de comando
SWAP_SIZE=""
ENABLE_POWER_SAVE=false
SKIP_MODELS=false
NON_INTERACTIVE=false

usage() {
    echo "Uso: $0 [opções]"
    echo ""
    echo "Opções:"
    echo "  --swap SIZE       Criar swap com SIZE (ex: 16G, 8G, 4G)"
    echo "  --power-save      Habilitar modo de economia de energia"
    echo "  --skip-models     Pular download de modelos"
    echo "  --non-interactive Modo não-interativo (aceita defaults)"
    echo "  -h, --help        Mostrar esta ajuda"
    echo ""
    echo "Exemplos:"
    echo "  ./install.sh --swap 16G --power-save"
    echo "  ./install.sh --swap 8G --non-interactive"
}

# Parsear argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        --swap)
            SWAP_SIZE="$2"
            shift 2
            ;;
        --power-save)
            ENABLE_POWER_SAVE=true
            shift
            ;;
        --skip-models)
            SKIP_MODELS=true
            shift
            ;;
        --non-interactive)
            NON_INTERACTIVE=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            log_error "Opção desconhecida: $1"
            usage
            exit 1
            ;;
    esac
done

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

# =============================================================================
# Função para criar SWAP
# =============================================================================
create_swap() {
    local size=$1
    local swap_file="/swapfile"

    log_info "Configurando swap de $size..."

    # Verificar se já existe swap
    if swapon --show | grep -q "$swap_file"; then
        log_info "Swap já existe. Removendo para reconfigurar..."
        sudo swapoff "$swap_file" 2>/dev/null || true
        sudo rm -f "$swap_file"
    fi

    # Desabilitar dphys-swapfile se existir (Raspberry Pi OS)
    if systemctl is-active --quiet dphys-swapfile 2>/dev/null; then
        log_info "Desabilitando dphys-swapfile..."
        sudo systemctl stop dphys-swapfile
        sudo systemctl disable dphys-swapfile
    fi

    # Converter tamanho para MB
    local size_mb
    if [[ "$size" =~ ^([0-9]+)[Gg]$ ]]; then
        size_mb=$((${BASH_REMATCH[1]} * 1024))
    elif [[ "$size" =~ ^([0-9]+)[Mm]$ ]]; then
        size_mb=${BASH_REMATCH[1]}
    else
        size_mb=$size
    fi

    log_info "Criando arquivo swap de ${size_mb}MB..."
    log_warn "Isso pode demorar alguns minutos..."

    # Criar arquivo swap
    sudo dd if=/dev/zero of="$swap_file" bs=1M count="$size_mb" status=progress

    # Configurar permissões
    sudo chmod 600 "$swap_file"

    # Formatar como swap
    sudo mkswap "$swap_file"

    # Ativar swap
    sudo swapon "$swap_file"

    # Adicionar ao fstab para persistência
    if ! grep -q "$swap_file" /etc/fstab; then
        echo "$swap_file none swap sw 0 0" | sudo tee -a /etc/fstab
    fi

    # Configurar swappiness para uso com LLMs (mais agressivo)
    echo "vm.swappiness=60" | sudo tee /etc/sysctl.d/99-swap.conf
    sudo sysctl vm.swappiness=60

    log_success "Swap de $size configurado!"
    swapon --show
}

# =============================================================================
# Função para configurar economia de energia
# =============================================================================
setup_power_save() {
    log_info "Configurando economia de energia..."

    # Criar arquivo de configuração do sistema
    local power_conf="/etc/voice-processor-power.conf"

    sudo tee "$power_conf" > /dev/null << 'POWEREOF'
# Voice Processor Power Management Configuration
# Gerado automaticamente pelo script de instalação

# CPU Governor padrão (powersave, ondemand, performance)
CPU_GOVERNOR=powersave

# Frequência máxima da CPU em MHz (600, 800, 1000)
CPU_MAX_FREQ=600

# Desabilitar HDMI quando não usado
DISABLE_HDMI=true

# Desabilitar LED de atividade
DISABLE_ACT_LED=true

# Desabilitar LED de energia
DISABLE_PWR_LED=true

# WiFi power save
WIFI_POWER_SAVE=true

# Desabilitar Bluetooth
DISABLE_BLUETOOTH=true
POWEREOF

    # Criar script de inicialização de energia
    sudo tee /usr/local/bin/voice-processor-power.sh > /dev/null << 'PWRSCRIPT'
#!/bin/bash
# Voice Processor Power Management Startup Script

source /etc/voice-processor-power.conf 2>/dev/null || exit 0

# Aplicar governor de CPU
if [ -n "$CPU_GOVERNOR" ]; then
    for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
        echo "$CPU_GOVERNOR" > "$cpu" 2>/dev/null || true
    done
fi

# Aplicar frequência máxima
if [ -n "$CPU_MAX_FREQ" ]; then
    freq_khz=$((CPU_MAX_FREQ * 1000))
    for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_max_freq; do
        echo "$freq_khz" > "$cpu" 2>/dev/null || true
    done
fi

# Desabilitar HDMI
if [ "$DISABLE_HDMI" = "true" ]; then
    /usr/bin/tvservice -o 2>/dev/null || vcgencmd display_power 0 2>/dev/null || true
fi

# LEDs
if [ "$DISABLE_ACT_LED" = "true" ]; then
    echo none > /sys/class/leds/ACT/trigger 2>/dev/null || true
    echo 0 > /sys/class/leds/ACT/brightness 2>/dev/null || true
fi

if [ "$DISABLE_PWR_LED" = "true" ]; then
    echo none > /sys/class/leds/PWR/trigger 2>/dev/null || true
    echo 0 > /sys/class/leds/PWR/brightness 2>/dev/null || true
fi

# WiFi Power Save
if [ "$WIFI_POWER_SAVE" = "true" ]; then
    iw wlan0 set power_save on 2>/dev/null || true
fi

# Bluetooth
if [ "$DISABLE_BLUETOOTH" = "true" ]; then
    rfkill block bluetooth 2>/dev/null || true
    systemctl stop bluetooth 2>/dev/null || true
fi

echo "Voice Processor power settings applied"
PWRSCRIPT

    sudo chmod +x /usr/local/bin/voice-processor-power.sh

    # Criar serviço systemd
    sudo tee /etc/systemd/system/voice-processor-power.service > /dev/null << 'SVCEOF'
[Unit]
Description=Voice Processor Power Management
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/voice-processor-power.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
SVCEOF

    # Habilitar serviço
    sudo systemctl daemon-reload
    sudo systemctl enable voice-processor-power.service
    sudo systemctl start voice-processor-power.service

    # Configurações adicionais no config.txt
    if [ -f /boot/config.txt ]; then
        BOOT_CONFIG="/boot/config.txt"
    elif [ -f /boot/firmware/config.txt ]; then
        BOOT_CONFIG="/boot/firmware/config.txt"
    else
        BOOT_CONFIG=""
    fi

    if [ -n "$BOOT_CONFIG" ]; then
        log_info "Atualizando $BOOT_CONFIG para economia de energia..."

        # Adicionar configurações se não existirem
        if ! grep -q "# Voice Processor Power Settings" "$BOOT_CONFIG"; then
            sudo tee -a "$BOOT_CONFIG" > /dev/null << 'BOOTEOF'

# Voice Processor Power Settings
# Desabilitar LEDs
dtparam=act_led_trigger=none
dtparam=act_led_activelow=off
dtparam=pwr_led_trigger=none
dtparam=pwr_led_activelow=off

# Desabilitar Bluetooth (economiza ~30mA)
dtoverlay=disable-bt

# Desabilitar WiFi power LED
dtparam=eth_led0=4
dtparam=eth_led1=4
BOOTEOF
        fi
    fi

    log_success "Economia de energia configurada!"
    log_info "Reinicie o sistema para aplicar todas as configurações"
}

# =============================================================================
# Perguntar sobre swap se não especificado
# =============================================================================
if [ -z "$SWAP_SIZE" ] && $IS_PI && ! $NON_INTERACTIVE; then
    echo ""
    log_info "=== Configuração de Swap ==="
    echo "Para rodar LLMs locais, é recomendado criar um arquivo swap grande."
    echo "O Pi Zero 2W tem apenas 512MB de RAM."
    echo ""
    echo "Opções recomendadas:"
    echo "  1) 16G - Recomendado para LLMs maiores (Phi-2, Gemma)"
    echo "  2) 8G  - Bom para TinyLlama"
    echo "  3) 4G  - Mínimo para operação básica"
    echo "  4) Pular - Não criar swap adicional"
    echo ""
    read -p "Escolha [1-4] (default: 1): " swap_choice

    case $swap_choice in
        2) SWAP_SIZE="8G" ;;
        3) SWAP_SIZE="4G" ;;
        4) SWAP_SIZE="" ;;
        *) SWAP_SIZE="16G" ;;
    esac
fi

# Criar swap se especificado
if [ -n "$SWAP_SIZE" ]; then
    create_swap "$SWAP_SIZE"
fi

# =============================================================================
# Perguntar sobre economia de energia se não especificado
# =============================================================================
if ! $ENABLE_POWER_SAVE && $IS_PI && ! $NON_INTERACTIVE; then
    echo ""
    read -p "Deseja habilitar modo de economia de energia? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        ENABLE_POWER_SAVE=true
    fi
fi

# Configurar economia de energia se solicitado
if $ENABLE_POWER_SAVE && $IS_PI; then
    setup_power_save
fi

# =============================================================================
# Instalação principal
# =============================================================================

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
    libatlas3-base \
    git \
    cmake \
    build-essential \
    wget \
    curl \
    sqlite3

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
    if ! $SKIP_MODELS; then
        log_info "Baixando modelo Whisper tiny..."
        bash models/download-ggml-model.sh tiny
    fi

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
mkdir -p models logs cache data

# Setup ReSpeaker (se disponível)
if $IS_PI; then
    log_info "Configurando ReSpeaker HAT..."
    bash scripts/setup_respeaker.sh || log_warn "ReSpeaker setup pode precisar de reinício"
fi

# Baixar modelo TinyLlama (opcional)
if ! $SKIP_MODELS && ! $NON_INTERACTIVE; then
    log_info ""
    read -p "Deseja baixar o modelo TinyLlama (~700MB)? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Baixando TinyLlama quantizado..."
        TINYLLAMA_URL="https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
        wget -q --show-progress -O models/tinyllama-1.1b-q4.gguf "$TINYLLAMA_URL" || log_warn "Falha ao baixar TinyLlama"
    fi
fi

# Criar arquivo de configuração se não existir
if [ ! -f "config/config.yaml" ]; then
    cp config/config.example.yaml config/config.yaml
    log_info "Arquivo de configuração criado: config/config.yaml"
fi

# Criar diretório de cache para fila offline
mkdir -p ~/.cache/voice-processor

# =============================================================================
# Mensagem final
# =============================================================================
log_success "=== Instalação concluída! ==="
echo ""
log_info "Resumo da instalação:"
if [ -n "$SWAP_SIZE" ]; then
    echo "  ✓ Swap de $SWAP_SIZE configurado"
fi
if $ENABLE_POWER_SAVE; then
    echo "  ✓ Economia de energia habilitada"
fi
echo "  ✓ whisper.cpp instalado"
echo "  ✓ llama.cpp instalado"
echo "  ✓ Ambiente Python configurado"
echo ""
log_info "Para usar:"
echo "  1. Ative o ambiente virtual: source venv/bin/activate"
echo "  2. Configure: nano config/config.yaml"
echo "  3. Execute: python3 src/main.py"
echo ""
log_info "Para modo contínuo: python3 src/main.py --continuous"
log_info "Para teste rápido: python3 src/main.py --test"
echo ""
if $ENABLE_POWER_SAVE; then
    log_warn "Reinicie o sistema para aplicar todas as configurações de energia:"
    echo "  sudo reboot"
fi
