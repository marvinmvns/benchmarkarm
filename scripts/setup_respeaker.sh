#!/bin/bash
# =============================================================================
# Setup do ReSpeaker HAT para Raspberry Pi
# Suporta: ReSpeaker 2-Mics Pi HAT, ReSpeaker 4-Mic Array
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Verificar se é Raspberry Pi
if ! grep -q "Raspberry" /proc/device-tree/model 2>/dev/null; then
    log_warn "Não é um Raspberry Pi. Pulando setup do ReSpeaker."
    exit 0
fi

log_info "=== Configurando ReSpeaker HAT ==="

# Detectar versão do kernel
KERNEL_VERSION=$(uname -r)
log_info "Kernel: $KERNEL_VERSION"

# Verificar se I2C está habilitado
if ! lsmod | grep -q i2c_dev; then
    log_info "Habilitando I2C..."
    sudo raspi-config nonint do_i2c 0
fi

# Verificar se SPI está habilitado
if ! lsmod | grep -q spi_bcm2835; then
    log_info "Habilitando SPI..."
    sudo raspi-config nonint do_spi 0
fi

# Instalar dependências
log_info "Instalando dependências de áudio..."
sudo apt-get install -y -qq \
    i2c-tools \
    libasound2-plugins \
    alsa-utils

# Clonar driver do ReSpeaker (se necessário)
SEEED_DIR="/tmp/seeed-voicecard"
if [ ! -d "$SEEED_DIR" ]; then
    log_info "Baixando drivers do ReSpeaker..."
    git clone --depth 1 https://github.com/respeaker/seeed-voicecard.git "$SEEED_DIR"
fi

cd "$SEEED_DIR"

# Verificar se já está instalado
if aplay -l 2>/dev/null | grep -q "seeed"; then
    log_success "ReSpeaker já está configurado!"
    exit 0
fi

# Instalar driver
log_info "Instalando driver do ReSpeaker..."
sudo ./install.sh || {
    log_warn "Instalação do driver pode requerer kernel headers"
    log_info "Tentando método alternativo..."

    # Método alternativo: usar device tree overlay
    if [ -f /boot/config.txt ]; then
        # Para ReSpeaker 2-Mics
        if ! grep -q "seeed-2mic-voicecard" /boot/config.txt; then
            echo "dtoverlay=seeed-2mic-voicecard" | sudo tee -a /boot/config.txt
        fi
    elif [ -f /boot/firmware/config.txt ]; then
        # Raspberry Pi OS mais recente
        if ! grep -q "seeed-2mic-voicecard" /boot/firmware/config.txt; then
            echo "dtoverlay=seeed-2mic-voicecard" | sudo tee -a /boot/firmware/config.txt
        fi
    fi
}

# Configurar ALSA
log_info "Configurando ALSA..."
cat << 'EOF' | sudo tee /etc/asound.conf
# Configuração ALSA para ReSpeaker
pcm.!default {
    type asym
    playback.pcm "playback"
    capture.pcm "capture"
}

pcm.playback {
    type plug
    slave.pcm "hw:seeed2micvoicec"
}

pcm.capture {
    type plug
    slave.pcm "hw:seeed2micvoicec"
}

ctl.!default {
    type hw
    card seeed2micvoicec
}
EOF

# Configuração alternativa para diferentes versões
cat << 'EOF' > ~/.asoundrc
# Configuração local ALSA
pcm.!default {
    type asym
    playback.pcm "plughw:0,0"
    capture.pcm "plughw:0,0"
}

ctl.!default {
    type hw
    card 0
}
EOF

# Testar configuração
log_info "Testando dispositivo de áudio..."
if arecord -l 2>/dev/null | grep -q -E "(seeed|bcm2835)"; then
    log_success "Dispositivo de áudio detectado!"
    arecord -l
else
    log_warn "Dispositivo não detectado. Reinicie o Raspberry Pi."
fi

log_success "=== Setup do ReSpeaker concluído! ==="
log_info "Reinicie o sistema para aplicar as alterações: sudo reboot"
