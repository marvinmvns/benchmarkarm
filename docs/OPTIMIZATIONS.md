# Otimizações para Raspberry Pi Zero 2W

Este documento descreve todas as otimizações implementadas para garantir performance adequada no Raspberry Pi Zero 2W (512MB RAM + swap).

## Resumo das Otimizações

| Categoria | Quantidade | Arquivos Principais | Benefícios |
|-----------|------------|---------------------|------------|
| Memória | 4 | cache.py, server.py, batch_processor.py | Crescimento controlado, evicção LRU |
| CPU | 4 | cpu_limiter.py, server.py | Throttling, semáforos, prioridade |
| Energia | 3 | power.py, config.yaml | Modos de energia, monitoramento térmico |
| Rede | 3 | queue.py, pipeline.py | Resiliência offline, retry, fallback |
| Threading | 5 | server.py, batch_processor.py | Non-blocking, daemon threads |
| Configuração | 7 | config.yaml | Parâmetros ajustáveis |

---

## 1. Otimizações de Memória

### 1.1 MemoryLogHandler (Singleton com Buffer Limitado)
**Arquivo:** `src/web/server.py:53-141`

```python
class MemoryLogHandler(logging.Handler):
    _instance = None  # Singleton
    def __init__(self, max_entries: int = 200):
        self.log_entries: deque = deque(maxlen=max_entries)
```

- Buffer circular com máximo 200 entradas
- Singleton garante instância única
- Thread-safe com `_lock`
- **Economia:** ~2MB RAM máximo para logs

### 1.2 Sistema de Cache (Two-Tier)
**Arquivo:** `src/utils/cache.py:24-300`

- **Memória:** Acesso rápido, limite de 100 entradas
- **Disco:** Persistência, carregamento sob demanda
- **Evicção LRU:** Remove 20% mais antigos quando cheio
- **TTL:** Expiração automática configurável

```python
def _evict_oldest(self):
    """Remove 20% mais antigos da memória."""
    to_remove = int(len(self._memory_cache) * 0.2)
```

### 1.3 Lazy Loading de Componentes
**Arquivo:** `src/pipeline.py:80-182`

Componentes inicializados apenas quando necessários:
- AudioCapture (`_init_audio`)
- VoiceActivityDetector (`_init_vad`)
- WhisperTranscriber (`_init_transcriber`)
- LLMProvider (`_init_llm`)
- Cache (`_init_cache`)

**Benefício:** Economia de ~200MB+ RAM até primeiro uso.

---

## 2. Otimizações de CPU

### 2.1 CPU Limiter
**Arquivo:** `src/utils/cpu_limiter.py:27-200`

```python
class CPULimiter:
    def __init__(self, max_percent: int = 85):
        self.pause_event = threading.Event()
```

- **Threshold:** 85% CPU máximo
- **Pausa automática:** Congela processamento quando excede
- **Prioridade:** Usa `nice()` para reduzir prioridade
- **Subprocessos:** `nice -n 15` + `ionice -c 3`

### 2.2 Semáforo de Processamento
**Arquivo:** `src/web/server.py:20-50`

```python
_processing_semaphore = threading.Semaphore(2)

@require_processing_slot
def heavy_endpoint():
    # Máximo 2 processamentos simultâneos
```

- Limita a 2 processamentos paralelos
- Retorna HTTP 503 quando ocupado
- Previne OOM (Out of Memory)

### 2.3 Batch Processing Adaptativo
**Arquivo:** `src/utils/batch_processor.py:184-232`

- **CPU threshold:** Só processa se CPU < 30%
- **Intervalo:** 5 minutos entre runs
- **Limite:** Máximo 10 arquivos por execução

---

## 3. Otimizações de Energia

### 3.1 Modos de Energia
**Arquivo:** `src/utils/power.py:19-514`

| Modo | Consumo Estimado | Governor | Freq Max |
|------|------------------|----------|----------|
| Performance | ~1800mW | performance | - |
| Balanced | ~1200mW | ondemand | - |
| Power Save | ~800mW | powersave | 600MHz |
| Ultra Power Save | ~500mW | powersave | 400MHz |

### 3.2 Controles de Hardware
**Arquivo:** `src/web/server.py:1031-1115`

```python
# Desabilitar HDMI: ~30mA economia
vcgencmd display_power 0

# Desabilitar Bluetooth: ~20mA economia
systemctl stop bluetooth

# WiFi Power Save
iwconfig wlan0 power on
```

### 3.3 Throttling Térmico
**Arquivo:** `src/utils/power.py:436-514`

- **Threshold alto:** 70°C - reduz para power_save
- **Threshold crítico:** 80°C - reduz para ultra_power_save
- **Monitoramento:** Verificação contínua via vcgencmd

---

## 4. Otimizações de Rede

### 4.1 Fila Offline (SQLite)
**Arquivo:** `src/utils/queue.py:65-657`

- **Persistência:** SQLite com índices otimizados
- **Retry exponencial:** Base 30s, 2^retry multiplicador
- **Auto-processamento:** Quando conexão restaurada
- **Limite:** 1000 tarefas máximo

### 4.2 Fallback Local
**Arquivo:** `src/pipeline.py:239-276`

```python
except (ConnectionError, Timeout):
    # Fallback para Whisper local
    result = self._local_transcribe(audio_file)
```

- Detecta erros de conexão
- Usa Whisper tiny local como fallback
- Transparente para o usuário

---

## 5. Feature Toggles (UI)

### Toggles Disponíveis na Aba Geral

| Toggle | Config Path | Impacto |
|--------|-------------|---------|
| Cache de Transcrições | system.cache_enabled | ~2MB RAM |
| Logs em Memória | system.memory_logs_enabled | ~2MB RAM |
| Detecção de Voz (VAD) | audio.vad_enabled | CPU contínuo |
| Resumo Automático (LLM) | usb_receiver.auto_summarize | Alto CPU/RAM |
| LEDs ReSpeaker | hardware.led_enabled | ~5mA |
| Modo Baixa Memória | system.low_memory_mode | Otimizações agressivas |
| Limitador CPU | system.cpu_limit_enabled | Previne travamento |
| Economia de Energia | power_management.enabled | Controle de power |
| Desabilitar HDMI | power_management.disable_hdmi | ~30mA |
| Desabilitar Bluetooth | power_management.disable_bluetooth | ~20mA |
| WiFi Power Save | power_management.wifi_power_save | Variável |
| Escuta Contínua | usb_receiver.enabled | Alto CPU |
| Transcrição Automática | usb_receiver.auto_transcribe | Alto CPU |
| Batch Automático | usb_receiver.auto_process | CPU periódico |
| Whisper Streaming | whisper.stream_mode | Muito alto CPU |
| Auto-Refresh UI | web_interface.auto_refresh | API polling |

---

## 6. Configurações Recomendadas

### Máxima Economia (Bateria/Solar)

```yaml
power_management:
  enabled: true
  default_mode: ultra_power_save
  disable_hdmi: true
  disable_bluetooth: true
  wifi_power_save: true

system:
  low_memory_mode: true
  cache_enabled: false  # Economiza RAM

usb_receiver:
  enabled: false  # Só manual
  auto_transcribe: false
  auto_summarize: false

web_interface:
  auto_refresh: false  # Manual
```

**Consumo estimado:** ~500-700mW

### Balanceado (Uso Normal)

```yaml
power_management:
  enabled: true
  default_mode: balanced
  auto_adjust: true

system:
  low_memory_mode: true
  cache_enabled: true

usb_receiver:
  enabled: true
  auto_transcribe: true
  auto_summarize: false  # LLM usa muita RAM
```

**Consumo estimado:** ~800-1200mW

### Performance (Conectado à Energia)

```yaml
power_management:
  enabled: false

system:
  low_memory_mode: false
  cache_enabled: true

usb_receiver:
  enabled: true
  auto_transcribe: true
  auto_summarize: true
```

**Consumo estimado:** ~1500-1800mW

---

## 7. Monitoramento

### Endpoints de Status

```bash
# Status de energia
curl http://192.168.31.124:8080/api/power/status

# Status de hardware
curl http://192.168.31.124:8080/api/power/hardware/status

# Info do sistema
curl http://192.168.31.124:8080/api/system/info

# Status da fila offline
curl http://192.168.31.124:8080/api/queue/status
```

### Comandos vcgencmd

```bash
# Temperatura
vcgencmd measure_temp

# Frequência
vcgencmd measure_clock arm

# Voltagem
vcgencmd measure_volts core

# Throttling
vcgencmd get_throttled
```

---

## 8. Troubleshooting

### Alto Uso de Memória
1. Desative `cache_enabled`
2. Reduza `max_entries` do MemoryLogHandler
3. Ative `low_memory_mode`
4. Desative `auto_summarize` (LLM consome muita RAM)

### Throttling Térmico
1. Ative `power_management.enabled`
2. Use modo `power_save` ou `ultra_power_save`
3. Melhore ventilação/dissipador
4. Reduza `cpu_limit_percent`

### Processamento Lento
1. Aumente swap (16GB recomendado)
2. Use modelos menores (whisper-tiny, tinyllama)
3. Desative features não essenciais
4. Reduza `refresh_interval` da UI

---

*Última atualização: 2025-12-26*
