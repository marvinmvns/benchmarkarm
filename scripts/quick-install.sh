#!/bin/bash
# =============================================================================
# Raspberry Pi Voice Processor - Instalação Rápida
# Um único comando para instalar tudo automaticamente
# =============================================================================
# Uso: curl -sSL https://raw.githubusercontent.com/marvinmvns/benchmarkarm/main/scripts/quick-install.sh | bash

set -e

# Cores
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
echo "  Raspberry Pi Voice Processor - Instalação"
echo "=============================================="
echo ""

# Verificar se está rodando como root
if [ "$EUID" -eq 0 ]; then
    log_error "Não execute como root. Use um usuário normal."
    exit 1
fi

# Diretório de instalação
INSTALL_DIR="${HOME}/benchmarkarm"

# 1. Atualizar sistema
log_info "Atualizando sistema..."
sudo apt-get update -qq

# 2. Instalar dependências do sistema (com pacote correto para Pi OS moderno)
log_info "Instalando dependências do sistema..."
sudo apt-get install -y -qq \
    python3-pip \
    python3-venv \
    python3-dev \
    python3-pyaudio \
    portaudio19-dev \
    libsndfile1 \
    libffi-dev \
    libasound2-dev \
    git \
    cmake \
    build-essential \
    wget \
    curl \
    sqlite3 2>/dev/null || true

# Tentar instalar libatlas (nome pode variar)
sudo apt-get install -y -qq libatlas3-base 2>/dev/null || \
sudo apt-get install -y -qq libatlas-base-dev 2>/dev/null || \
log_warn "libatlas não disponível, numpy usará fallback"

# 3. Clonar ou atualizar repositório
log_info "Baixando código..."
if [ -d "$INSTALL_DIR" ]; then
    cd "$INSTALL_DIR"
    git pull origin main
else
    git clone https://github.com/marvinmvns/benchmarkarm.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# 4. Criar ambiente virtual
log_info "Configurando ambiente Python..."
python3 -m venv venv
source venv/bin/activate

# 5. Atualizar pip e instalar dependências
pip install --upgrade pip wheel setuptools -q
pip install -r requirements.txt -q 2>/dev/null || {
    log_warn "Algumas dependências podem ter falhado, tentando individualmente..."
    pip install flask pyyaml numpy scipy -q
}

# 6. Criar diretórios necessários
mkdir -p models logs cache data config ~/audio-recordings

# 7. Copiar configuração padrão
if [ ! -f "config/config.yaml" ]; then
    cp config/config.example.yaml config/config.yaml
    log_info "Configuração criada: config/config.yaml"
fi

# 8. Configurar ReSpeaker (se script existir)
if [ -f "scripts/setup_respeaker.sh" ]; then
    log_info "Configurando ReSpeaker HAT..."
    chmod +x scripts/setup_respeaker.sh
    sudo bash scripts/setup_respeaker.sh 2>/dev/null || log_warn "ReSpeaker setup pode precisar de reboot"
fi

# 9. Criar script de inicialização rápida
cat > "$INSTALL_DIR/start.sh" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
python3 -m src.web.server --host 0.0.0.0 --port 8080
EOF
chmod +x "$INSTALL_DIR/start.sh"

# 10. Criar serviço systemd (opcional)
sudo tee /etc/systemd/system/voice-processor.service > /dev/null << EOF
[Unit]
Description=Voice Processor Web Server
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python -m src.web.server --host 0.0.0.0 --port 8080
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable voice-processor.service 2>/dev/null || true

# Mensagem final
echo ""
log_success "=============================================="
log_success "  Instalação concluída!"
log_success "=============================================="
echo ""
log_info "Para iniciar manualmente:"
echo "  cd $INSTALL_DIR && ./start.sh"
echo ""
log_info "Ou usar o serviço systemd:"
echo "  sudo systemctl start voice-processor"
echo "  sudo systemctl status voice-processor"
echo ""
log_info "Acesse a interface web em:"
echo "  http://$(hostname -I | awk '{print $1}'):8080"
echo ""
log_warn "Se usar ReSpeaker, reinicie o sistema:"
echo "  sudo reboot"
echo ""
