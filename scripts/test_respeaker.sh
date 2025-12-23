#!/bin/bash
# =============================================================================
# Teste do ReSpeaker HAT
# Verifica se o microfone está funcionando
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

echo ""
echo "=============================================="
echo "  Teste do ReSpeaker HAT"
echo "=============================================="
echo ""

# 1. Verificar dispositivos de áudio
log_info "Verificando dispositivos de áudio..."
echo ""
arecord -l 2>/dev/null || {
    log_error "Nenhum dispositivo de gravação encontrado!"
    log_warn "O ReSpeaker pode não estar instalado corretamente."
    log_info "Execute: sudo ./scripts/setup_respeaker.sh"
    exit 1
}

echo ""

# 2. Verificar se seeed está presente
if arecord -l 2>/dev/null | grep -qi "seeed"; then
    log_success "ReSpeaker detectado!"
else
    log_warn "ReSpeaker não detectado explicitamente."
    log_info "Pode estar usando outro nome de dispositivo."
fi

# 3. Teste de gravação rápida
log_info "Gravando 3 segundos de áudio de teste..."
TEST_FILE="/tmp/respeaker_test.wav"

# Tentar diferentes dispositivos
DEVICE=""
if arecord -l 2>/dev/null | grep -q "seeed"; then
    DEVICE="plughw:seeed2micvoicec"
elif arecord -l 2>/dev/null | grep -q "card 0"; then
    DEVICE="plughw:0,0"
else
    DEVICE="default"
fi

log_info "Usando dispositivo: $DEVICE"
echo ""
echo ">>> FALE ALGO AGORA! (3 segundos) <<<"
echo ""

arecord -D "$DEVICE" -f S16_LE -r 16000 -c 1 -d 3 "$TEST_FILE" 2>/dev/null || {
    log_warn "Falha ao gravar com $DEVICE, tentando 'default'..."
    arecord -f S16_LE -r 16000 -c 1 -d 3 "$TEST_FILE" 2>/dev/null || {
        log_error "Não foi possível gravar áudio!"
        log_info "Verifique se o ReSpeaker está conectado corretamente."
        exit 1
    }
}

# 4. Verificar tamanho do arquivo
FILE_SIZE=$(stat -f%z "$TEST_FILE" 2>/dev/null || stat -c%s "$TEST_FILE" 2>/dev/null || echo "0")

if [ "$FILE_SIZE" -gt 1000 ]; then
    log_success "Áudio gravado com sucesso! ($FILE_SIZE bytes)"
else
    log_error "Arquivo de áudio muito pequeno. O microfone pode não estar funcionando."
    exit 1
fi

# 5. Reproduzir o áudio (opcional)
echo ""
read -p "Deseja ouvir a gravação? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log_info "Reproduzindo..."
    aplay "$TEST_FILE" 2>/dev/null || log_warn "Não foi possível reproduzir o áudio"
fi

# Limpar
rm -f "$TEST_FILE"

echo ""
log_success "=============================================="
log_success "  Teste concluído com sucesso!"
log_success "=============================================="
echo ""
log_info "O ReSpeaker está funcionando."
log_info "Você pode iniciar o servidor: ./start.sh"
echo ""
