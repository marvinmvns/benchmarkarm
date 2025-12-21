#!/bin/bash
# =============================================================================
# Download de Modelos para Raspberry Pi Voice Processor
# =============================================================================

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODELS_DIR="$PROJECT_DIR/models"
EXTERNAL_DIR="$PROJECT_DIR/external"

mkdir -p "$MODELS_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }

echo "=== Download de Modelos ==="
echo ""
echo "Selecione os modelos para baixar:"
echo ""
echo "=== WHISPER (Transcrição) ==="
echo "1) tiny   (75MB)  - Mais rápido, menos preciso (recomendado para Pi Zero 2W)"
echo "2) base   (142MB) - Bom equilíbrio"
echo "3) small  (466MB) - Mais preciso, mais lento"
echo ""
echo "=== LLM (Resumo) ==="
echo "4) TinyLlama 1.1B Q4  (670MB)  - Rápido, bom para resumos"
echo "5) Phi-2 Q4           (1.6GB)  - Mais capaz, mais lento"
echo "6) Gemma 2B Q4        (1.5GB)  - Alternativa"
echo ""
echo "0) Sair"
echo ""

download_whisper_model() {
    local model=$1
    local whisper_cpp="$EXTERNAL_DIR/whisper.cpp"

    if [ ! -d "$whisper_cpp" ]; then
        log_info "whisper.cpp não encontrado. Execute install.sh primeiro."
        return 1
    fi

    cd "$whisper_cpp"
    log_info "Baixando modelo Whisper $model..."
    bash models/download-ggml-model.sh "$model"

    # Criar link simbólico
    ln -sf "$whisper_cpp/models/ggml-$model.bin" "$MODELS_DIR/whisper-$model.bin"
    log_success "Whisper $model instalado!"
}

download_llm_model() {
    local model=$1
    local url=$2
    local filename=$3

    if [ -f "$MODELS_DIR/$filename" ]; then
        log_info "Modelo $model já existe."
        read -p "Baixar novamente? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            return 0
        fi
    fi

    log_info "Baixando $model (~$(echo $url | grep -oP '\d+\.?\d*GB' || echo 'tamanho desconhecido'))..."
    wget -q --show-progress -O "$MODELS_DIR/$filename" "$url"
    log_success "$model instalado!"
}

while true; do
    read -p "Opção: " choice
    case $choice in
        1)
            download_whisper_model "tiny"
            ;;
        2)
            download_whisper_model "base"
            ;;
        3)
            download_whisper_model "small"
            ;;
        4)
            download_llm_model "TinyLlama 1.1B Q4" \
                "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf" \
                "tinyllama-1.1b-q4.gguf"
            ;;
        5)
            download_llm_model "Phi-2 Q4" \
                "https://huggingface.co/TheBloke/phi-2-GGUF/resolve/main/phi-2.Q4_K_M.gguf" \
                "phi-2-q4.gguf"
            ;;
        6)
            download_llm_model "Gemma 2B Q4" \
                "https://huggingface.co/google/gemma-2b-it-GGUF/resolve/main/gemma-2b-it.Q4_K_M.gguf" \
                "gemma-2b-q4.gguf"
            ;;
        0)
            echo "Saindo..."
            exit 0
            ;;
        *)
            echo "Opção inválida"
            ;;
    esac
    echo ""
done
