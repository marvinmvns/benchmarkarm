#!/bin/bash
# Script de Validação de Otimizações
# Testa todas as otimizações implementadas nas Fases 1 e 2

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PASSED=0
FAILED=0
SKIPPED=0

print_header() {
    echo -e "${BLUE}"
    echo "═══════════════════════════════════════════════════════"
    echo "  $1"
    echo "═══════════════════════════════════════════════════════"
    echo -e "${NC}"
}

test_pass() {
    echo -e "${GREEN}✅ PASSOU:${NC} $1"
    ((PASSED++))
}

test_fail() {
    echo -e "${RED}❌ FALHOU:${NC} $1"
    ((FAILED++))
}

test_skip() {
    echo -e "${YELLOW}⏭️  PULADO:${NC} $1"
    ((SKIPPED++))
}

print_header "Validação de Otimizações - Fase 1 e 2"

# ============================================================================
# Teste 1: Audio Buffer Allocation
# ============================================================================
print_header "Teste 1: Audio Buffer Allocation"

if python3 -c "from src.audio.capture import quick_record" 2>/dev/null; then
    echo "Testando captura de áudio (10s)..."
    RESULT=$(python3 -c "
from src.audio.capture import quick_record
import time
start = time.time()
audio = quick_record(duration=10)
elapsed = time.time() - start
print(f'{elapsed:.2f}')
" 2>/dev/null || echo "ERROR")

    if [ "$RESULT" != "ERROR" ]; then
        ELAPSED=$(echo "$RESULT" | awk '{print $1}')
        if (( $(echo "$ELAPSED < 11.0" | bc -l) )); then
            test_pass "Captura de 10s em ${ELAPSED}s (esperado: <11s)"
        else
            test_fail "Captura de 10s em ${ELAPSED}s (muito lento)"
        fi
    else
        test_fail "Erro ao executar teste de captura"
    fi
else
    test_skip "Módulo de captura não disponível"
fi

# ============================================================================
# Teste 2: LLM Server Mode
# ============================================================================
print_header "Teste 2: LLM Server Mode"

# Verificar se servidor está configurado
if grep -q "use_server_mode: true" config/config.yaml 2>/dev/null || \
   grep -q "use_server_mode: true" config/config.example.yaml 2>/dev/null; then
    test_pass "Configuração de server mode encontrada"
else
    test_fail "Configuração de server mode NÃO encontrada"
fi

# Verificar código implementado
if grep -q "_start_server" src/llm/local.py 2>/dev/null; then
    test_pass "Métodos de servidor implementados em local.py"
else
    test_fail "Métodos de servidor NÃO encontrados"
fi

# ============================================================================
# Teste 3: Named Pipes for Whisper
# ============================================================================
print_header "Teste 3: Named Pipes for Whisper"

if grep -q "_transcribe_with_pipe" src/transcription/whisper.py 2>/dev/null; then
    test_pass "Método _transcribe_with_pipe implementado"
else
    test_fail "Método _transcribe_with_pipe NÃO encontrado"
fi

if grep -q "os.mkfifo" src/transcription/whisper.py 2>/dev/null; then
    test_pass "Named pipes (FIFO) implementado"
else
    test_fail "Named pipes NÃO implementado"
fi

# ============================================================================
# Teste 4: Request Queue (Web Server)
# ============================================================================
print_header "Teste 4: Request Queue no Web Server"

if grep -q "_processing_semaphore" src/web/server.py 2>/dev/null; then
    test_pass "Semáforo de processamento implementado"
else
    test_fail "Semáforo de processamento NÃO encontrado"
fi

if grep -q "require_processing_slot" src/web/server.py 2>/dev/null; then
    test_pass "Decorator require_processing_slot implementado"
else
    test_fail "Decorator require_processing_slot NÃO encontrado"
fi

# Testar web server (se estiver rodando)
if curl -s http://localhost:5000/api/config > /dev/null 2>&1; then
    test_pass "Web server está acessível"

    # Teste de carga (5 requests simultâneos)
    echo "Enviando 5 requests simultâneos para testar fila..."
    SUCCESS=0
    SERVICE_UNAVAILABLE=0

    for i in {1..5}; do
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:5000/api/test/llm 2>/dev/null || echo "000")
        if [ "$HTTP_CODE" == "200" ]; then
            ((SUCCESS++))
        elif [ "$HTTP_CODE" == "503" ]; then
            ((SERVICE_UNAVAILABLE++))
        fi
    done

    if [ $SUCCESS -le 2 ] && [ $SERVICE_UNAVAILABLE -ge 3 ]; then
        test_pass "Request queue funcionando ($SUCCESS OK, $SERVICE_UNAVAILABLE limitados)"
    else
        test_fail "Request queue pode não estar funcionando ($SUCCESS OK, $SERVICE_UNAVAILABLE limitados)"
    fi
else
    test_skip "Web server não está acessível (não está rodando?)"
fi

# ============================================================================
# Teste 5: Config Caching
# ============================================================================
print_header "Teste 5: Config Caching"

if [ -f "src/utils/config_manager.py" ]; then
    test_pass "Arquivo config_manager.py criado"
else
    test_fail "Arquivo config_manager.py NÃO encontrado"
fi

if grep -q "ConfigManager" src/utils/config_manager.py 2>/dev/null; then
    test_pass "Classe ConfigManager implementada"
else
    test_fail "Classe ConfigManager NÃO encontrada"
fi

# Testar endpoint de stats (se web server estiver rodando)
if curl -s http://localhost:5000/api/config/cache/stats > /dev/null 2>&1; then
    STATS=$(curl -s http://localhost:5000/api/config/cache/stats)
    test_pass "Endpoint /api/config/cache/stats acessível"
    echo "  Stats: $STATS"
else
    test_skip "Endpoint de cache stats não acessível"
fi

# ============================================================================
# Teste 6: VAD Result Caching
# ============================================================================
print_header "Teste 6: VAD Result Caching"

if grep -q "enable_cache" src/audio/vad.py 2>/dev/null; then
    test_pass "Parâmetro enable_cache adicionado"
else
    test_fail "Parâmetro enable_cache NÃO encontrado"
fi

if grep -q "_compute_audio_hash" src/audio/vad.py 2>/dev/null; then
    test_pass "Método _compute_audio_hash implementado"
else
    test_fail "Método _compute_audio_hash NÃO encontrado"
fi

if grep -q "get_cache_stats" src/audio/vad.py 2>/dev/null; then
    test_pass "Método get_cache_stats implementado"
else
    test_fail "Método get_cache_stats NÃO encontrado"
fi

# Teste funcional de VAD cache
if python3 -c "from src.audio.vad import VoiceActivityDetector" 2>/dev/null; then
    echo "Testando cache do VAD..."
    VAD_RESULT=$(python3 -c "
from src.audio.vad import VoiceActivityDetector
import numpy as np

vad = VoiceActivityDetector(enable_cache=True)
audio = np.random.randint(-1000, 1000, 16000, dtype=np.int16)

# 10 chamadas com mesmo áudio
for _ in range(10):
    _ = vad.is_speech(audio)

stats = vad.get_cache_stats()
hit_rate = float(stats['hit_rate'].rstrip('%'))
print(f'{hit_rate:.1f}')
" 2>/dev/null || echo "ERROR")

    if [ "$VAD_RESULT" != "ERROR" ]; then
        HIT_RATE=$(echo "$VAD_RESULT" | awk '{print $1}')
        if (( $(echo "$HIT_RATE > 80.0" | bc -l) )); then
            test_pass "VAD cache funcionando (hit rate: ${HIT_RATE}%)"
        else
            test_fail "VAD cache com hit rate baixo (${HIT_RATE}%)"
        fi
    else
        test_fail "Erro ao testar VAD cache"
    fi
else
    test_skip "Módulo VAD não disponível"
fi

# ============================================================================
# Resumo Final
# ============================================================================
echo ""
print_header "Resumo da Validação"

TOTAL=$((PASSED + FAILED + SKIPPED))

echo -e "${GREEN}✅ Passou:  $PASSED/$TOTAL${NC}"
echo -e "${RED}❌ Falhou:  $FAILED/$TOTAL${NC}"
echo -e "${YELLOW}⏭️  Pulado: $SKIPPED/$TOTAL${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ✅ TODOS OS TESTES PASSARAM! 🎉                      ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════╝${NC}"
    exit 0
else
    echo -e "${RED}╔═══════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  ❌ ALGUNS TESTES FALHARAM                            ║${NC}"
    echo -e "${RED}╚═══════════════════════════════════════════════════════╝${NC}"
    exit 1
fi
