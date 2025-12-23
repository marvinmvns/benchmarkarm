#!/bin/bash
# =============================================================================
# Setup do ReSpeaker HAT para Raspberry Pi
# Compatível com Raspberry Pi OS Bookworm (Kernel 6.1+)
#
# Suporta: ReSpeaker 2-Mics Pi HAT V1.0/V2.0, ReSpeaker 4-Mic Array
#
# NOTA: Este script usa o método moderno com Device Tree Overlays.
#       NÃO é necessário instalar o driver seeed-voicecard antigo.
#       O kernel Bookworm já inclui os drivers necessários:
#       - snd-soc-wm8960
#       - snd-soc-simple-card
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

# Detectar modelo do Pi
PI_MODEL=$(cat /proc/device-tree/model 2>/dev/null || echo "Unknown")
log_info "Modelo detectado: $PI_MODEL"

# Detectar versão do kernel
KERNEL_VERSION=$(uname -r)
log_info "Kernel: $KERNEL_VERSION"

log_info "=== Configurando ReSpeaker HAT (Método Moderno para Bookworm) ==="

# =============================================================================
# Determinar arquivo de configuração correto
# =============================================================================
if [ -f /boot/firmware/config.txt ]; then
    # Raspberry Pi OS Bookworm Desktop
    BOOT_CONFIG="/boot/firmware/config.txt"
    OVERLAYS_DIR="/boot/firmware/overlays"
elif [ -f /boot/config.txt ]; then
    # Raspberry Pi OS Lite ou versões antigas
    BOOT_CONFIG="/boot/config.txt"
    OVERLAYS_DIR="/boot/overlays"
else
    log_error "Arquivo config.txt não encontrado!"
    exit 1
fi

log_info "Usando config: $BOOT_CONFIG"
log_info "Overlays dir: $OVERLAYS_DIR"

# =============================================================================
# Verificar e habilitar I2C
# =============================================================================
log_info "Verificando I2C..."

if ! grep -q "^dtparam=i2c_arm=on" "$BOOT_CONFIG"; then
    log_info "Habilitando I2C..."
    sudo raspi-config nonint do_i2c 0 2>/dev/null || {
        echo "dtparam=i2c_arm=on" | sudo tee -a "$BOOT_CONFIG"
    }
fi

# =============================================================================
# Instalar dependências
# =============================================================================
log_info "Instalando dependências..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    i2c-tools \
    libasound2-plugins \
    alsa-utils \
    device-tree-compiler \
    git

# =============================================================================
# Selecionar tipo de ReSpeaker (pode ser passado como argumento)
# =============================================================================
RESPEAKER_TYPE="${1:-}"

if [ -z "$RESPEAKER_TYPE" ]; then
    echo ""
    log_info "Selecione o tipo de ReSpeaker HAT:"
    echo "  1) ReSpeaker 2-Mic Pi HAT V1.0"
    echo "  2) ReSpeaker 2-Mic Pi HAT V2.0 (mais comum)"
    echo "  3) ReSpeaker 4-Mic Array"
    echo ""
    read -p "Escolha [1-3] (default: 2): " respeaker_choice

    case $respeaker_choice in
        1) RESPEAKER_TYPE="2mic-v1" ;;
        3) RESPEAKER_TYPE="4mic" ;;
        *) RESPEAKER_TYPE="2mic-v2" ;;
    esac
fi

case $RESPEAKER_TYPE in
    "2mic-v1"|"1")
        OVERLAY_NAME="seeed-2mic-voicecard"
        OVERLAY_DTS="seeed-2mic-voicecard-overlay.dts"
        CARD_NAME="seeed2micvoicec"
        ;;
    "4mic"|"3")
        OVERLAY_NAME="seeed-4mic-voicecard"
        OVERLAY_DTS="seeed-4mic-voicecard-overlay.dts"
        CARD_NAME="seeed4micvoicec"
        ;;
    *)
        OVERLAY_NAME="respeaker-2mic-v2_0"
        OVERLAY_DTS="respeaker-2mic-v2_0-overlay.dts"
        CARD_NAME="seeed2micvoicec"
        ;;
esac

log_info "Configurando: $OVERLAY_NAME"

# =============================================================================
# Baixar e compilar Device Tree Overlay
# =============================================================================
OVERLAY_DIR="/tmp/seeed-overlays"
SKIP_COMPILE=false

# Verificar se overlay já existe
if [ -f "$OVERLAYS_DIR/${OVERLAY_NAME}.dtbo" ]; then
    log_info "Overlay já existe em $OVERLAYS_DIR"
    read -p "Deseja recompilar? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Pulando compilação do overlay..."
        SKIP_COMPILE=true
    fi
fi

if [ "$SKIP_COMPILE" != "true" ]; then
    log_info "Baixando overlays..."

    rm -rf "$OVERLAY_DIR"
    
    # Tentar repositório oficial Seeed primeiro
    if git clone --depth 1 https://github.com/Seeed-Studio/seeed-linux-dtoverlays.git "$OVERLAY_DIR" 2>/dev/null; then
        log_success "Usando repositório oficial Seeed"
        OVERLAY_SRC="$OVERLAY_DIR/overlays/rpi"
    else
        log_warn "Repositório oficial falhou. Tentando fork HinTak..."
        
        # Fallback: Fork HinTak (melhor suporte para kernels novos)
        if git clone --depth 1 https://github.com/HinTak/seeed-voicecard.git "$OVERLAY_DIR" 2>/dev/null; then
            log_success "Usando fork HinTak/seeed-voicecard"
            OVERLAY_SRC="$OVERLAY_DIR"
            
            # O HinTak tem instalador próprio
            log_info "Executando instalador do HinTak..."
            cd "$OVERLAY_DIR"
            
            if sudo ./install.sh 2mic 2>/dev/null || sudo ./install.sh; then
                log_success "Driver instalado via HinTak/seeed-voicecard"
                SKIP_COMPILE=true
                OVERLAY_INSTALLED=true
            else
                log_warn "Instalador falhou, tentando compilação manual..."
            fi
        else
            log_error "Falha ao baixar overlays! Verifique sua conexão."
            exit 1
        fi
    fi

    if [ "$SKIP_COMPILE" != "true" ]; then
        cd "$OVERLAY_SRC"

        # Verificar se o arquivo DTS existe
        if [ ! -f "$OVERLAY_DTS" ]; then
            log_warn "Arquivo $OVERLAY_DTS não encontrado!"
            log_info "Tentando alternativas..."

            # Listar arquivos disponíveis
            ls -la *.dts 2>/dev/null | head -10

            # Tentar encontrar alternativa
            if [ -f "respeaker-2mic-v2_0-overlay.dts" ]; then
                OVERLAY_DTS="respeaker-2mic-v2_0-overlay.dts"
                OVERLAY_NAME="respeaker-2mic-v2_0"
            elif [ -f "seeed-2mic-voicecard-overlay.dts" ]; then
                OVERLAY_DTS="seeed-2mic-voicecard-overlay.dts"
                OVERLAY_NAME="seeed-2mic-voicecard"
            elif [ -f "seeed-2mic-voicecard.dts" ]; then
                OVERLAY_DTS="seeed-2mic-voicecard.dts"
                OVERLAY_NAME="seeed-2mic-voicecard"
            else
                log_error "Nenhum overlay compatível encontrado!"
                log_info "Tentando instalação via fork HinTak..."
                
                # Última tentativa: usar HinTak diretamente
                rm -rf "$OVERLAY_DIR"
                git clone --depth 1 https://github.com/HinTak/seeed-voicecard.git "$OVERLAY_DIR"
                cd "$OVERLAY_DIR"
                sudo ./install.sh 2mic || sudo ./install.sh || {
                    log_error "Todas as tentativas de instalação falharam!"
                    exit 1
                }
                log_success "Instalado via HinTak/seeed-voicecard"
                SKIP_COMPILE=true
                OVERLAY_INSTALLED=true
            fi
            log_info "Usando: $OVERLAY_DTS"
        fi

        if [ "$SKIP_COMPILE" != "true" ]; then
            log_info "Compilando overlay: $OVERLAY_DTS"
            dtc -@ -I dts -O dtb -o "${OVERLAY_NAME}.dtbo" "$OVERLAY_DTS" 2>/dev/null || \
            dtc -I dts -O dtb -o "${OVERLAY_NAME}.dtbo" "$OVERLAY_DTS"

            if [ ! -f "${OVERLAY_NAME}.dtbo" ]; then
                log_error "Falha ao compilar overlay!"
                exit 1
            fi

            log_info "Instalando overlay em $OVERLAYS_DIR"
            sudo cp "${OVERLAY_NAME}.dtbo" "$OVERLAYS_DIR/"

            log_success "Overlay compilado e instalado!"
        fi
    fi
fi

# =============================================================================
# Configurar config.txt
# =============================================================================
log_info "Configurando $BOOT_CONFIG..."

# Remover overlays antigos do ReSpeaker (evitar conflitos)
sudo sed -i '/dtoverlay=seeed-2mic-voicecard/d' "$BOOT_CONFIG" 2>/dev/null || true
sudo sed -i '/dtoverlay=seeed-4mic-voicecard/d' "$BOOT_CONFIG" 2>/dev/null || true
sudo sed -i '/dtoverlay=respeaker-2mic/d' "$BOOT_CONFIG" 2>/dev/null || true
sudo sed -i '/dtoverlay=googlevoicehat-soundcard/d' "$BOOT_CONFIG" 2>/dev/null || true

# Adicionar seção ReSpeaker se não existir
if ! grep -q "# ReSpeaker HAT Configuration" "$BOOT_CONFIG"; then
    echo "" | sudo tee -a "$BOOT_CONFIG" > /dev/null
    echo "# ReSpeaker HAT Configuration" | sudo tee -a "$BOOT_CONFIG" > /dev/null
fi

# Adicionar overlay
if ! grep -q "dtoverlay=${OVERLAY_NAME}" "$BOOT_CONFIG"; then
    log_info "Adicionando dtoverlay=${OVERLAY_NAME}"
    echo "dtoverlay=${OVERLAY_NAME}" | sudo tee -a "$BOOT_CONFIG" > /dev/null
fi

# Garantir que I2S está habilitado
if ! grep -q "^dtparam=i2s=on" "$BOOT_CONFIG"; then
    echo "dtparam=i2s=on" | sudo tee -a "$BOOT_CONFIG" > /dev/null
fi

# =============================================================================
# Configurar ALSA
# =============================================================================
log_info "Configurando ALSA..."

# Configuração global ALSA
sudo tee /etc/asound.conf > /dev/null << ALSAEOF
# =============================================================================
# Configuração ALSA para ReSpeaker HAT
# Gerado automaticamente - $(date)
# Card: $CARD_NAME
# =============================================================================

# Definir ReSpeaker como dispositivo padrão
defaults.pcm.card $CARD_NAME
defaults.ctl.card $CARD_NAME

# Configuração PCM assimétrica (captura e reprodução separadas)
pcm.!default {
    type asym
    playback.pcm "playback"
    capture.pcm "capture"
}

pcm.playback {
    type plug
    slave.pcm "hw:$CARD_NAME,0"
}

pcm.capture {
    type plug
    slave.pcm "hw:$CARD_NAME,0"
}

# Controle de mixer
ctl.!default {
    type hw
    card $CARD_NAME
}

# Alias para acesso direto
pcm.seeed {
    type plug
    slave.pcm "hw:$CARD_NAME,0"
}

ctl.seeed {
    type hw
    card $CARD_NAME
}
ALSAEOF

# Configuração local do usuário
mkdir -p ~/.config/alsa 2>/dev/null || true
cat > ~/.asoundrc << USERALSAEOF
# Configuração local ALSA para ReSpeaker
# Card: $CARD_NAME

pcm.!default {
    type asym
    playback.pcm "plughw:$CARD_NAME,0"
    capture.pcm "plughw:$CARD_NAME,0"
}

ctl.!default {
    type hw
    card $CARD_NAME
}
USERALSAEOF

# =============================================================================
# Verificar configuração
# =============================================================================
echo ""
log_info "Configuração do $BOOT_CONFIG:"
grep -E "(dtoverlay|dtparam=i2s|dtparam=i2c)" "$BOOT_CONFIG" | grep -v "^#" | tail -10

# =============================================================================
# Testar se o dispositivo já está disponível
# =============================================================================
echo ""
log_info "Verificando dispositivo de áudio..."

if arecord -l 2>/dev/null | grep -q -E "(seeed|wm8960|$CARD_NAME)"; then
    log_success "Dispositivo ReSpeaker detectado!"
    echo ""
    arecord -l

    echo ""
    log_info "Testando captura de áudio (3 segundos)..."
    timeout 5 arecord -D "plughw:$CARD_NAME,0" -f S16_LE -r 16000 -c 1 -d 3 /tmp/test_audio.wav 2>/dev/null && {
        log_success "Captura de áudio funcionando!"
        rm -f /tmp/test_audio.wav
    } || {
        log_warn "Teste de captura falhou. Verifique após reiniciar."
    }
else
    log_warn "Dispositivo ReSpeaker não detectado ainda."
    log_info "Isso é normal se você ainda não reiniciou o sistema."
fi

# =============================================================================
# Verificar WM8960 via I2C
# =============================================================================
echo ""
log_info "Verificando chip WM8960 via I2C..."

if command -v i2cdetect &> /dev/null; then
    # WM8960 normalmente está no endereço 0x1a ou 0x1b
    I2C_OUTPUT=$(i2cdetect -y 1 2>/dev/null || echo "")
    if echo "$I2C_OUTPUT" | grep -q -E "1a|1b|18"; then
        log_success "Chip WM8960 detectado no barramento I2C!"
    else
        log_warn "Chip WM8960 não detectado. Verifique a conexão do HAT."
        log_info "Saída do i2cdetect:"
        echo "$I2C_OUTPUT"
    fi
fi

# =============================================================================
# Verificar logs do kernel
# =============================================================================
echo ""
log_info "Verificando logs do kernel para WM8960..."
dmesg 2>/dev/null | grep -i -E "(wm8960|seeed|voicecard)" | tail -5 || \
    log_info "Nenhum log do WM8960 ainda (normal antes do reboot)"

# =============================================================================
# Limpar arquivos temporários
# =============================================================================
rm -rf "$OVERLAY_DIR" 2>/dev/null || true

# =============================================================================
# Mensagem final
# =============================================================================
echo ""
log_success "=== Setup do ReSpeaker concluído! ==="
echo ""
log_info "Resumo:"
echo "  Overlay: $OVERLAY_NAME"
echo "  Card: $CARD_NAME"
echo "  Config: $BOOT_CONFIG"
echo ""
log_info "Próximos passos:"
echo "  1. Reinicie o Raspberry Pi: sudo reboot"
echo "  2. Após reiniciar, verifique com: arecord -l"
echo "  3. Teste o microfone:"
echo "     arecord -D plughw:$CARD_NAME,0 -f S16_LE -r 16000 -d 5 test.wav"
echo "  4. Reproduza o teste: aplay test.wav"
echo ""
log_warn "IMPORTANTE: Reinicie o sistema para aplicar as alterações!"

# Perguntar se deseja reiniciar (apenas se interativo)
if [ -t 0 ]; then
    read -p "Deseja reiniciar agora? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Reiniciando em 3 segundos..."
        sleep 3
        sudo reboot
    fi
fi
