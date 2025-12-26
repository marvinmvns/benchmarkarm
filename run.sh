#!/bin/bash
# =============================================================================
# Raspberry Pi Voice Processor - Script Mestre
# Um único comando para instalar, configurar e iniciar tudo
# =============================================================================
# Uso: ./run.sh [comando]
# Comandos: install, setup, start, status, test, help
# =============================================================================

set -e

# Cores
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
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Banner
show_banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║     🎙️  Raspberry Pi Voice Processor                     ║"
    echo "║     Escuta Contínua + Transcrição + Resumo               ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# Verificar se está no Raspberry Pi
check_pi() {
    if grep -q "Raspberry" /proc/device-tree/model 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

# Verificar dependências básicas
check_deps() {
    local missing=0
    
    if [ ! -d "venv" ]; then
        log_warn "Ambiente virtual não encontrado"
        missing=1
    fi
    
    if [ ! -f "config/config.yaml" ]; then
        log_warn "Arquivo de configuração não encontrado"
        missing=1
    fi
    
    return $missing
}

# Instalar tudo
do_install() {
    log_info "=== Instalação Completa ==="
    
    # Verificar se já está instalado
    if [ -d "venv" ] && [ -d "external/whisper.cpp" ]; then
        read -p "Projeto já instalado. Reinstalar? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Instalação cancelada"
            return 0
        fi
    fi
    
    # Executar instalação principal
    if [ -f "scripts/install.sh" ]; then
        bash scripts/install.sh "$@"
    else
        log_error "Script de instalação não encontrado!"
        exit 1
    fi
}

# Configurar ReSpeaker
do_setup_audio() {
    log_info "=== Configuração de Áudio ==="
    
    if check_pi; then
        if [ -f "scripts/setup_respeaker.sh" ]; then
            sudo bash scripts/setup_respeaker.sh "$@"
        else
            log_error "Script de setup ReSpeaker não encontrado!"
            exit 1
        fi
    else
        log_warn "Não é um Raspberry Pi. Pulando configuração do ReSpeaker."
    fi
}

# Testar áudio
do_test_audio() {
    log_info "=== Teste de Áudio ==="
    
    if [ -f "scripts/test_respeaker.sh" ]; then
        bash scripts/test_respeaker.sh
    else
        log_error "Script de teste não encontrado!"
        exit 1
    fi
}

# Iniciar servidor web
do_start() {
    log_info "=== Iniciando Servidor ==="
    
    # Ativar ambiente virtual
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
    else
        log_error "Ambiente virtual não encontrado. Execute: ./run.sh install"
        exit 1
    fi
    
    # Obter IP
    IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
    PORT="${1:-8080}"
    
    echo ""
    log_success "Servidor iniciando em:"
    echo -e "  ${GREEN}http://${IP}:${PORT}${NC}"
    echo ""
    log_info "Pressione Ctrl+C para parar"
    echo ""
    
    # Iniciar servidor
    python3 -m src.web.server --host 0.0.0.0 --port "$PORT"
}

# Iniciar em background
do_start_bg() {
    log_info "=== Iniciando em Background ==="
    
    if systemctl is-active --quiet voice-processor 2>/dev/null; then
        log_info "Serviço já está rodando"
        systemctl status voice-processor --no-pager
    else
        if [ -f "/etc/systemd/system/voice-processor.service" ]; then
            sudo systemctl start voice-processor
            log_success "Serviço iniciado!"
            sleep 2
            systemctl status voice-processor --no-pager
        else
            log_warn "Serviço systemd não configurado. Usando nohup..."
            source venv/bin/activate
            nohup python3 -m src.web.server --host 0.0.0.0 --port 8080 > logs/server.log 2>&1 &
            echo $! > .server.pid
            log_success "Servidor iniciado em background (PID: $(cat .server.pid))"
        fi
    fi
}

# Parar servidor
do_stop() {
    log_info "=== Parando Servidor ==="

    if systemctl is-active --quiet voice-processor 2>/dev/null; then
        sudo systemctl stop voice-processor
        log_success "Serviço parado"
    elif [ -f ".server.pid" ]; then
        kill $(cat .server.pid) 2>/dev/null || true
        rm -f .server.pid
        log_success "Servidor parado"
    else
        log_warn "Nenhum servidor rodando"
    fi
}

# Reiniciar servidor
do_restart() {
    log_info "=== Reiniciando Servidor ==="
    do_stop
    sleep 2
    do_start_bg
}

# Ver logs
do_logs() {
    log_info "=== Logs do Servidor ==="

    if systemctl is-active --quiet voice-processor 2>/dev/null; then
        sudo journalctl -u voice-processor -f --no-pager
    elif [ -f "logs/server.log" ]; then
        tail -f logs/server.log
    else
        log_warn "Nenhum log disponível"
    fi
}

# Status do sistema
do_status() {
    log_info "=== Status do Sistema ==="
    echo ""
    
    # Verificar instalação
    echo -e "${BLUE}Instalação:${NC}"
    [ -d "venv" ] && echo "  ✅ Ambiente virtual" || echo "  ❌ Ambiente virtual"
    [ -d "external/whisper.cpp" ] && echo "  ✅ whisper.cpp" || echo "  ❌ whisper.cpp"
    [ -d "external/llama.cpp" ] && echo "  ✅ llama.cpp" || echo "  ❌ llama.cpp"
    [ -f "config/config.yaml" ] && echo "  ✅ Configuração" || echo "  ❌ Configuração"
    echo ""
    
    # Verificar serviço
    echo -e "${BLUE}Serviço:${NC}"
    if systemctl is-active --quiet voice-processor 2>/dev/null; then
        echo "  ✅ voice-processor rodando"
    elif [ -f ".server.pid" ] && kill -0 $(cat .server.pid) 2>/dev/null; then
        echo "  ✅ Servidor rodando (PID: $(cat .server.pid))"
    else
        echo "  ⏸️  Servidor parado"
    fi
    echo ""
    
    # Verificar áudio
    echo -e "${BLUE}Áudio:${NC}"
    if arecord -l 2>/dev/null | grep -qi seeed; then
        echo "  ✅ ReSpeaker detectado"
    elif arecord -l 2>/dev/null | grep -q "card"; then
        echo "  ⚠️  Microfone disponível (não é ReSpeaker)"
    else
        echo "  ❌ Nenhum dispositivo de áudio"
    fi
    echo ""
    
    # IP
    IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
    echo -e "${BLUE}Acesso:${NC}"
    echo "  http://${IP}:8080"
    echo ""
}

# Setup completo (install + audio)
do_full_setup() {
    show_banner
    log_info "=== Setup Completo ==="
    echo ""
    
    # 1. Instalação
    do_install
    
    # 2. Configurar áudio
    echo ""
    read -p "Configurar ReSpeaker agora? [Y/n] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        do_setup_audio
        
        echo ""
        log_warn "Reboot necessário para aplicar configurações de áudio."
        read -p "Reiniciar agora? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            sudo reboot
        fi
    fi
    
    echo ""
    log_success "Setup completo!"
    log_info "Inicie o servidor com: ./run.sh start"
}

# Ajuda
show_help() {
    show_banner
    echo "Uso: ./run.sh [comando]"
    echo ""
    echo "Comandos:"
    echo "  install     Instalar todas as dependências"
    echo "  setup       Configurar ReSpeaker HAT"
    echo "  test        Testar dispositivo de áudio"
    echo "  start       Iniciar servidor web (foreground)"
    echo "  start-bg    Iniciar servidor em background"
    echo "  stop        Parar servidor"
    echo "  restart     Reiniciar servidor"
    echo "  logs        Ver logs em tempo real"
    echo "  status      Ver status do sistema"
    echo "  full        Setup completo (install + setup)"
    echo "  help        Mostrar esta ajuda"
    echo ""
    echo "Exemplos:"
    echo "  ./run.sh full          # Primeira instalação"
    echo "  ./run.sh start         # Iniciar servidor"
    echo "  ./run.sh start 3000    # Iniciar na porta 3000"
    echo "  ./run.sh restart       # Reiniciar o servidor"
    echo "  ./run.sh logs          # Ver logs em tempo real"
    echo ""
}

# Main
case "${1:-}" in
    install)
        shift
        do_install "$@"
        ;;
    setup|audio)
        shift
        do_setup_audio "$@"
        ;;
    test)
        do_test_audio
        ;;
    start)
        shift
        do_start "$@"
        ;;
    start-bg|bg)
        do_start_bg
        ;;
    stop)
        do_stop
        ;;
    restart)
        do_restart
        ;;
    logs)
        do_logs
        ;;
    status)
        do_status
        ;;
    full)
        do_full_setup
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        show_banner
        if check_deps; then
            # Se tudo instalado, mostrar status e perguntar o que fazer
            do_status
            echo "Comandos: ./run.sh [install|setup|start|status|help]"
        else
            # Se não instalado, sugerir instalação
            log_warn "Projeto não configurado completamente."
            echo ""
            echo "Para primeira instalação:"
            echo "  ./run.sh full"
            echo ""
            echo "Para ver ajuda:"
            echo "  ./run.sh help"
        fi
        ;;
esac
