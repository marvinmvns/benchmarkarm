#!/bin/bash
# =============================================================================
# Teste e Configuração do Dispositivo de Áudio
# Verifica ReSpeaker ou permite selecionar outro microfone
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Diretório do projeto
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_FILE="$PROJECT_DIR/config/config.yaml"

echo ""
echo "=============================================="
echo "  Teste e Configuração de Áudio"
echo "=============================================="
echo ""

# 1. Listar todos os dispositivos de gravação
log_info "Dispositivos de áudio disponíveis:"
echo ""

DEVICES=()
INDEX=0

# Parsear saída de arecord -l
while IFS= read -r line; do
    if [[ "$line" =~ ^card\ ([0-9]+):\ ([^,]+),\ device\ ([0-9]+):\ (.+)$ ]]; then
        CARD="${BASH_REMATCH[1]}"
        CARD_NAME="${BASH_REMATCH[2]}"
        DEV="${BASH_REMATCH[3]}"
        DEV_NAME="${BASH_REMATCH[4]}"
        DEVICE="plughw:$CARD,$DEV"
        DEVICES+=("$DEVICE")
        
        # Destacar se for ReSpeaker
        if [[ "$CARD_NAME" =~ [Ss]eeed || "$DEV_NAME" =~ [Rr]e[Ss]peaker ]]; then
            echo -e "  ${GREEN}[$INDEX]${NC} $DEVICE - ${CYAN}$CARD_NAME${NC} - $DEV_NAME ${GREEN}(ReSpeaker!)${NC}"
        else
            echo -e "  [$INDEX] $DEVICE - $CARD_NAME - $DEV_NAME"
        fi
        ((INDEX++))
    fi
done < <(arecord -l 2>/dev/null)

# Adicionar opção default
DEVICES+=("default")
echo -e "  [$INDEX] default - Dispositivo padrão do sistema"
((INDEX++))

if [ ${#DEVICES[@]} -eq 1 ]; then
    log_error "Nenhum dispositivo de gravação encontrado!"
    log_info "Verifique se o microfone está conectado."
    exit 1
fi

echo ""

# 2. Seleção do dispositivo
SELECTED_DEVICE=""
if [ ${#DEVICES[@]} -eq 2 ]; then
    # Só tem 1 dispositivo + default
    SELECTED_DEVICE="${DEVICES[0]}"
    log_info "Usando único dispositivo disponível: $SELECTED_DEVICE"
else
    # Deixar usuário escolher
    read -p "Selecione o dispositivo [0-$((INDEX-1))] (default: 0): " choice
    choice=${choice:-0}
    
    if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -lt "${#DEVICES[@]}" ]; then
        SELECTED_DEVICE="${DEVICES[$choice]}"
    else
        log_error "Opção inválida!"
        exit 1
    fi
fi

echo ""
log_info "Dispositivo selecionado: $SELECTED_DEVICE"

# 3. Teste de gravação
echo ""
log_info "Gravando 3 segundos de áudio de teste..."
echo ""
echo -e "${YELLOW}>>> FALE ALGO AGORA! (3 segundos) <<<${NC}"
echo ""

TEST_FILE="/tmp/audio_test_$$.wav"

if arecord -D "$SELECTED_DEVICE" -f S16_LE -r 16000 -c 1 -d 3 "$TEST_FILE" 2>/dev/null; then
    # Verificar tamanho do arquivo
    FILE_SIZE=$(stat -c%s "$TEST_FILE" 2>/dev/null || echo "0")
    
    if [ "$FILE_SIZE" -gt 1000 ]; then
        log_success "Áudio gravado com sucesso! ($FILE_SIZE bytes)"
    else
        log_error "Arquivo de áudio muito pequeno. O microfone pode não estar funcionando."
        rm -f "$TEST_FILE"
        exit 1
    fi
else
    log_error "Falha ao gravar áudio com $SELECTED_DEVICE"
    rm -f "$TEST_FILE"
    exit 1
fi

# 4. Reproduzir o áudio (opcional)
echo ""
read -p "Deseja ouvir a gravação? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log_info "Reproduzindo..."
    aplay "$TEST_FILE" 2>/dev/null || log_warn "Não foi possível reproduzir o áudio"
fi

rm -f "$TEST_FILE"

# 5. Salvar configuração
echo ""
read -p "Salvar este dispositivo na configuração? [Y/n] " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    # Extrair número do card
    if [[ "$SELECTED_DEVICE" =~ ^plughw:([0-9]+), ]]; then
        CARD_NUM="${BASH_REMATCH[1]}"
    else
        CARD_NUM=""
    fi
    
    if [ -f "$CONFIG_FILE" ]; then
        # Atualizar config.yaml
        if grep -q "^audio:" "$CONFIG_FILE"; then
            # Verificar se device existe
            if grep -q "device:" "$CONFIG_FILE"; then
                sed -i "s|device:.*|device: $CARD_NUM  # Configurado por test_respeaker.sh|" "$CONFIG_FILE"
            else
                sed -i "/^audio:/a\  device: $CARD_NUM  # Configurado por test_respeaker.sh" "$CONFIG_FILE"
            fi
            log_success "Configuração atualizada em $CONFIG_FILE"
        else
            log_warn "Seção 'audio' não encontrada em $CONFIG_FILE"
        fi
    else
        log_warn "Arquivo de configuração não encontrado: $CONFIG_FILE"
    fi
    
    # Criar arquivo de device para referência rápida
    echo "$SELECTED_DEVICE" > "$PROJECT_DIR/.audio_device"
    log_success "Dispositivo salvo em $PROJECT_DIR/.audio_device"
fi

echo ""
log_success "=============================================="
log_success "  Teste concluído com sucesso!"
log_success "=============================================="
echo ""
log_info "Dispositivo de áudio: $SELECTED_DEVICE"
log_info "Você pode iniciar o servidor: ./start.sh"
echo ""
