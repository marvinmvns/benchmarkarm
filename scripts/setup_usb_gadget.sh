#!/bin/bash
# =============================================================================
# Setup USB Audio Gadget para Raspberry Pi Zero 2W
# =============================================================================
# Este script configura o Raspberry Pi para funcionar como uma
# placa de som USB (USB Audio Gadget) quando conectado a um PC.
#
# REQUISITOS:
#   - Raspberry Pi Zero 2W (ou Pi 4/5 com USB-C)
#   - Conexão via porta USB (não a porta de energia)
#
# COMO USAR:
#   1. Execute este script com sudo: sudo ./setup_usb_gadget.sh
#   2. Reinicie o Raspberry Pi: sudo reboot
#   3. Conecte o Pi ao PC via cabo USB
#   4. O PC reconhecerá o Pi como uma placa de som USB
#
# PARA DESATIVAR:
#   Execute: sudo ./setup_usb_gadget.sh --disable
#
# =============================================================================

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funções de log
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Verificar se é root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "Este script precisa ser executado como root"
        echo "Use: sudo $0"
        exit 1
    fi
}

# Verificar modelo do Raspberry Pi
check_pi_model() {
    log_info "Verificando modelo do Raspberry Pi..."
    
    if [ -f /proc/device-tree/model ]; then
        MODEL=$(cat /proc/device-tree/model)
        log_info "Modelo detectado: $MODEL"
        
        # Verificar se é um modelo compatível
        if [[ "$MODEL" == *"Zero 2"* ]] || [[ "$MODEL" == *"Pi 4"* ]] || [[ "$MODEL" == *"Pi 5"* ]]; then
            log_success "Modelo compatível com USB Gadget!"
        elif [[ "$MODEL" == *"Zero"* ]]; then
            log_success "Pi Zero detectado - compatível com USB Gadget"
        else
            log_warn "Modelo pode não suportar USB Gadget. Continuando mesmo assim..."
        fi
    else
        log_warn "Não foi possível detectar o modelo. Continuando..."
    fi
}

# Fazer backup dos arquivos de configuração
backup_configs() {
    log_info "Fazendo backup dos arquivos de configuração..."
    
    BACKUP_DIR="/boot/backup_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    
    if [ -f /boot/config.txt ]; then
        cp /boot/config.txt "$BACKUP_DIR/"
        log_success "Backup de config.txt criado"
    fi
    
    if [ -f /boot/cmdline.txt ]; then
        cp /boot/cmdline.txt "$BACKUP_DIR/"
        log_success "Backup de cmdline.txt criado"
    fi
    
    # Para Raspberry Pi OS Bookworm (nova estrutura)
    if [ -f /boot/firmware/config.txt ]; then
        cp /boot/firmware/config.txt "$BACKUP_DIR/"
        log_success "Backup de firmware/config.txt criado"
    fi
    
    if [ -f /boot/firmware/cmdline.txt ]; then
        cp /boot/firmware/cmdline.txt "$BACKUP_DIR/"
        log_success "Backup de firmware/cmdline.txt criado"
    fi
    
    echo "$BACKUP_DIR" > /tmp/usb_gadget_backup_dir
    log_info "Backups salvos em: $BACKUP_DIR"
}

# Determinar caminhos corretos (Bullseye vs Bookworm)
get_boot_paths() {
    if [ -f /boot/firmware/config.txt ]; then
        # Raspberry Pi OS Bookworm
        CONFIG_TXT="/boot/firmware/config.txt"
        CMDLINE_TXT="/boot/firmware/cmdline.txt"
    else
        # Raspberry Pi OS Bullseye ou anterior
        CONFIG_TXT="/boot/config.txt"
        CMDLINE_TXT="/boot/cmdline.txt"
    fi
    
    log_info "Usando: $CONFIG_TXT e $CMDLINE_TXT"
}

# Configurar config.txt
configure_config_txt() {
    log_info "Configurando $CONFIG_TXT..."
    
    # Adicionar dtoverlay=dwc2 se não existir
    if ! grep -q "^dtoverlay=dwc2" "$CONFIG_TXT"; then
        echo "" >> "$CONFIG_TXT"
        echo "# USB Gadget Mode (Audio)" >> "$CONFIG_TXT"
        echo "dtoverlay=dwc2" >> "$CONFIG_TXT"
        log_success "Adicionado: dtoverlay=dwc2"
    else
        log_info "dtoverlay=dwc2 já está configurado"
    fi
}

# Configurar cmdline.txt
configure_cmdline_txt() {
    log_info "Configurando $CMDLINE_TXT..."
    
    # Ler conteúdo atual
    CMDLINE=$(cat "$CMDLINE_TXT")
    
    # Adicionar modules-load=dwc2,g_audio após rootwait
    if ! echo "$CMDLINE" | grep -q "modules-load=dwc2"; then
        # Inserir após rootwait
        NEW_CMDLINE=$(echo "$CMDLINE" | sed 's/rootwait/rootwait modules-load=dwc2,g_audio/')
        
        # Se não encontrou rootwait, adicionar no final
        if [ "$NEW_CMDLINE" = "$CMDLINE" ]; then
            NEW_CMDLINE="$CMDLINE modules-load=dwc2,g_audio"
        fi
        
        echo "$NEW_CMDLINE" > "$CMDLINE_TXT"
        log_success "Adicionado: modules-load=dwc2,g_audio"
    else
        log_info "Módulos USB Gadget já estão configurados"
    fi
}

# Criar script de configuração do gadget de áudio
create_audio_gadget_script() {
    log_info "Criando script de configuração do USB Audio Gadget..."
    
    GADGET_SCRIPT="/usr/local/bin/usb-audio-gadget"
    
    cat > "$GADGET_SCRIPT" << 'EOF'
#!/bin/bash
# Configura USB Audio Gadget com parâmetros específicos

# Carregar módulo g_audio com configurações
modprobe g_audio \
    c_srate=44100 \
    c_ssize=2 \
    c_chmask=3 \
    p_srate=44100 \
    p_ssize=2 \
    p_chmask=3

echo "USB Audio Gadget configurado!"
echo "  - Sample Rate: 44100 Hz"
echo "  - Sample Size: 16-bit"
echo "  - Channels: Stereo"
EOF
    
    chmod +x "$GADGET_SCRIPT"
    log_success "Script criado: $GADGET_SCRIPT"
}

# Criar serviço systemd para iniciar automaticamente
create_systemd_service() {
    log_info "Criando serviço systemd..."
    
    SERVICE_FILE="/etc/systemd/system/usb-audio-gadget.service"
    
    cat > "$SERVICE_FILE" << 'EOF'
[Unit]
Description=USB Audio Gadget
After=sysinit.target
DefaultDependencies=no

[Service]
Type=oneshot
ExecStart=/usr/local/bin/usb-audio-gadget
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
    
    systemctl daemon-reload
    systemctl enable usb-audio-gadget.service
    
    log_success "Serviço systemd criado e habilitado"
}

# Desabilitar USB Gadget
disable_usb_gadget() {
    log_info "Desabilitando USB Audio Gadget..."
    
    get_boot_paths
    
    # Remover de config.txt
    if [ -f "$CONFIG_TXT" ]; then
        sed -i '/# USB Gadget Mode/d' "$CONFIG_TXT"
        sed -i '/^dtoverlay=dwc2$/d' "$CONFIG_TXT"
        log_success "Removido dtoverlay=dwc2 de config.txt"
    fi
    
    # Remover de cmdline.txt
    if [ -f "$CMDLINE_TXT" ]; then
        sed -i 's/ modules-load=dwc2,g_audio//g' "$CMDLINE_TXT"
        sed -i 's/modules-load=dwc2,g_audio //g' "$CMDLINE_TXT"
        log_success "Removido modules-load de cmdline.txt"
    fi
    
    # Desabilitar serviço
    if systemctl is-enabled usb-audio-gadget.service &>/dev/null; then
        systemctl disable usb-audio-gadget.service
        log_success "Serviço systemd desabilitado"
    fi
    
    log_success "USB Audio Gadget desabilitado!"
    log_warn "Reinicie o sistema para aplicar as mudanças: sudo reboot"
}

# Verificar status
check_status() {
    echo ""
    log_info "=== Status do USB Audio Gadget ==="
    echo ""
    
    # Verificar módulos carregados
    if lsmod | grep -q "g_audio"; then
        log_success "Módulo g_audio carregado"
    else
        log_warn "Módulo g_audio não carregado"
    fi
    
    if lsmod | grep -q "dwc2"; then
        log_success "Módulo dwc2 carregado"
    else
        log_warn "Módulo dwc2 não carregado"
    fi
    
    # Verificar dispositivo de áudio
    echo ""
    log_info "Dispositivos de áudio disponíveis:"
    arecord -l 2>/dev/null || echo "arecord não disponível"
    
    echo ""
}

# Mostrar ajuda
show_help() {
    echo "USB Audio Gadget Setup Script"
    echo ""
    echo "Uso: $0 [opção]"
    echo ""
    echo "Opções:"
    echo "  (sem opções)   Configura USB Audio Gadget"
    echo "  --disable      Remove configuração do USB Gadget"
    echo "  --status       Mostra status atual"
    echo "  --help         Mostra esta ajuda"
    echo ""
    echo "Após configurar, reinicie o sistema: sudo reboot"
}

# Main
main() {
    echo ""
    echo "============================================="
    echo "   USB Audio Gadget Setup - Pi Zero 2W"
    echo "============================================="
    echo ""
    
    case "${1:-}" in
        --disable)
            check_root
            disable_usb_gadget
            ;;
        --status)
            check_status
            ;;
        --help|-h)
            show_help
            ;;
        "")
            check_root
            check_pi_model
            backup_configs
            get_boot_paths
            configure_config_txt
            configure_cmdline_txt
            create_audio_gadget_script
            create_systemd_service
            
            echo ""
            log_success "============================================="
            log_success "   Configuração concluída com sucesso!"
            log_success "============================================="
            echo ""
            log_warn "IMPORTANTE: Reinicie o Raspberry Pi para ativar"
            echo ""
            echo "   sudo reboot"
            echo ""
            log_info "Após reiniciar:"
            echo "   1. Conecte o Pi ao PC via cabo USB (porta de dados)"
            echo "   2. O PC reconhecerá como 'USB Audio Device'"
            echo "   3. Configure o áudio do PC para usar esta saída"
            echo ""
            ;;
        *)
            log_error "Opção desconhecida: $1"
            show_help
            exit 1
            ;;
    esac
}

main "$@"
