"""
Gerenciamento de configuração do Voice Processor.
"""

import os
import re
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field

import yaml


def expand_env_vars(value: str) -> str:
    """Expande variáveis de ambiente no formato ${VAR}."""
    if not isinstance(value, str):
        return value

    pattern = re.compile(r'\$\{([^}]+)\}')

    def replace(match):
        var_name = match.group(1)
        return os.environ.get(var_name, "")

    return pattern.sub(replace, value)


def process_config_values(obj: Any) -> Any:
    """Processa valores de configuração recursivamente."""
    if isinstance(obj, dict):
        return {k: process_config_values(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [process_config_values(v) for v in obj]
    elif isinstance(obj, str):
        return expand_env_vars(obj)
    return obj


@dataclass
class AudioConfig:
    """Configuração de áudio."""
    device: str = ""
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 1024
    max_duration: int = 30
    silence_duration: float = 2.0
    vad_enabled: bool = True
    vad_aggressiveness: int = 2
    min_speech_duration: float = 0.5


@dataclass
class WhisperConfig:
    """Configuração do Whisper."""
    provider: str = "local"                  # local, openai, whisperapi
    model: str = "tiny"
    language: str = "pt"
    use_cpp: bool = True
    threads: int = 4
    quantization: str = "q5_0"
    beam_size: int = 1
    suppress_blank: bool = True
    stream_mode: bool = False                # Modo streaming (transcrição em tempo real)
    # OpenAI Whisper API
    openai_api_key: str = ""
    openai_model: str = "whisper-1"
    # WhisperAPI (servidor externo)
    whisperapi_url: str = "http://127.0.0.1:3001"
    whisperapi_timeout: int = 300            # Timeout em segundos


@dataclass
class LocalLLMConfig:
    """Configuração do LLM local."""
    model: str = "tinyllama"
    model_path: str = ""
    context_size: int = 512
    threads: int = 4
    max_tokens: int = 150
    temperature: float = 0.3
    quantization: str = "q4_0"


@dataclass
class OpenAIConfig:
    """Configuração da API OpenAI."""
    api_key: str = ""
    model: str = "gpt-4o-mini"
    max_tokens: int = 200
    temperature: float = 0.3


@dataclass
class AnthropicConfig:
    """Configuração da API Anthropic."""
    api_key: str = ""
    model: str = "claude-3-haiku-20240307"
    max_tokens: int = 200
    temperature: float = 0.3


@dataclass
class OllamaConfig:
    """Configuração do Ollama."""
    host: str = "http://localhost:11434"
    model: str = "tinyllama"
    max_tokens: int = 200


@dataclass
class ChatMockConfig:
    """Configuração do ChatMock (API compatível OpenAI local)."""
    base_url: str = "http://127.0.0.1:8000/v1"
    model: str = "gpt-5"
    max_tokens: int = 500
    temperature: float = 0.3
    reasoning_effort: str = "medium"  # minimal, low, medium, high, xhigh
    enable_web_search: bool = False


@dataclass
class LLMConfig:
    """Configuração completa do LLM."""
    provider: str = "local"
    local: LocalLLMConfig = field(default_factory=LocalLLMConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    anthropic: AnthropicConfig = field(default_factory=AnthropicConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    chatmock: ChatMockConfig = field(default_factory=ChatMockConfig)


@dataclass
class PromptsConfig:
    """Configuração de prompts."""
    summarize: str = "Resuma o seguinte texto:\n{text}\n\nResumo:"
    extract_actions: str = "Extraia as ações:\n{text}\n\nAções:"
    custom: str = ""


@dataclass
class SystemConfig:
    """Configuração do sistema."""
    cache_enabled: bool = True
    cache_dir: str = "~/.cache/voice-processor"
    cache_ttl: int = 3600
    log_level: str = "INFO"
    log_file: str = ""
    low_memory_mode: bool = True
    memory_logs_enabled: bool = True   # Logs em memória (desativar economiza RAM)
    timeout: int = 60
    # CPU Limiter - evita congelamento do Pi
    cpu_limit_enabled: bool = True      # Habilitar limitador de CPU
    cpu_limit_percent: int = 85         # Percentual máximo de CPU (70-95)
    cpu_check_interval: float = 1.0     # Intervalo de verificação em segundos


@dataclass
class HardwareConfig:
    """Configuração de hardware."""
    respeaker_type: str = "2mic"
    led_enabled: bool = True
    button_gpio: int = 17


@dataclass
class USBReceiverConfig:
    """
    Configuração do modo USB Receiver (Placa de Som USB).
    
    Transforma o Raspberry Pi em uma placa de som USB que recebe
    áudio de dispositivos externos, armazena e processa automaticamente.
    
    Por padrão, a aplicação escuta e transcreve tudo automaticamente.
    """
    enabled: bool = True                            # Habilitado por padrão
    save_directory: str = "~/audio-recordings"      # Diretório para salvar gravações
    auto_transcribe: bool = True                    # Transcrever automaticamente
    auto_summarize: bool = True                     # Gerar resumo automaticamente
    min_audio_duration: float = 3.0                 # Duração mínima para processar (segundos)
    max_audio_duration: float = 300.0               # Duração máxima (5 minutos)
    silence_split: bool = True                      # Dividir gravação por silêncio
    silence_threshold: float = 2.0                  # Segundos de silêncio para dividir
    sample_rate: int = 44100                        # Taxa de amostragem USB (CD quality)
    channels: int = 2                               # Stereo para compatibilidade USB
    process_on_disconnect: bool = True              # Processar quando USB desconectar
    keep_original_audio: bool = True                # Manter arquivo original após processar
    continuous_listen: bool = True                  # Escuta contínua por padrão
    usb_gadget_enabled: bool = False                # USB Gadget desabilitado por padrão (requer setup)
    auto_start: bool = False                        # Auto-iniciar escuta ao abrir a aplicação
    auto_process: bool = False                      # Auto-iniciar processamento em lote


@dataclass
class Config:
    """Configuração principal do Voice Processor."""
    mode: str = "hybrid"
    audio: AudioConfig = field(default_factory=AudioConfig)
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    prompts: PromptsConfig = field(default_factory=PromptsConfig)
    system: SystemConfig = field(default_factory=SystemConfig)
    hardware: HardwareConfig = field(default_factory=HardwareConfig)
    usb_receiver: USBReceiverConfig = field(default_factory=USBReceiverConfig)

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        """Cria configuração a partir de dicionário."""
        audio_data = data.get("audio", {})
        vad_data = audio_data.pop("vad", {}) if "vad" in audio_data else {}

        audio = AudioConfig(
            device=audio_data.get("device", ""),
            sample_rate=audio_data.get("sample_rate", 16000),
            channels=audio_data.get("channels", 1),
            chunk_size=audio_data.get("chunk_size", 1024),
            max_duration=audio_data.get("max_duration", 30),
            silence_duration=audio_data.get("silence_duration", 2.0),
            vad_enabled=vad_data.get("enabled", True),
            vad_aggressiveness=vad_data.get("aggressiveness", 2),
            min_speech_duration=vad_data.get("min_speech_duration", 0.5),
        )

        whisper_data = data.get("whisper", {})
        whisper = WhisperConfig(**{k: v for k, v in whisper_data.items() if k in WhisperConfig.__dataclass_fields__})

        llm_data = data.get("llm", {})
        local_data = llm_data.get("local", {})
        openai_data = llm_data.get("openai", {})
        anthropic_data = llm_data.get("anthropic", {})
        ollama_data = llm_data.get("ollama", {})

        llm = LLMConfig(
            provider=llm_data.get("provider", "local"),
            local=LocalLLMConfig(**{k: v for k, v in local_data.items() if k in LocalLLMConfig.__dataclass_fields__}),
            openai=OpenAIConfig(**{k: v for k, v in openai_data.items() if k in OpenAIConfig.__dataclass_fields__}),
            anthropic=AnthropicConfig(**{k: v for k, v in anthropic_data.items() if k in AnthropicConfig.__dataclass_fields__}),
            ollama=OllamaConfig(**{k: v for k, v in ollama_data.items() if k in OllamaConfig.__dataclass_fields__}),
        )

        prompts_data = data.get("prompts", {})
        prompts = PromptsConfig(**{k: v for k, v in prompts_data.items() if k in PromptsConfig.__dataclass_fields__})

        system_data = data.get("system", {})
        system = SystemConfig(**{k: v for k, v in system_data.items() if k in SystemConfig.__dataclass_fields__})

        hardware_data = data.get("hardware", {})
        hardware = HardwareConfig(**{k: v for k, v in hardware_data.items() if k in HardwareConfig.__dataclass_fields__})

        usb_receiver_data = data.get("usb_receiver", {})
        usb_receiver = USBReceiverConfig(**{k: v for k, v in usb_receiver_data.items() if k in USBReceiverConfig.__dataclass_fields__})

        return cls(
            mode=data.get("mode", "hybrid"),
            audio=audio,
            whisper=whisper,
            llm=llm,
            prompts=prompts,
            system=system,
            hardware=hardware,
            usb_receiver=usb_receiver,
        )


def load_config(config_path: Optional[str] = None) -> Config:
    """
    Carrega configuração do arquivo YAML.

    Args:
        config_path: Caminho do arquivo de configuração.
                    Se None, procura em locais padrão.

    Returns:
        Objeto Config com as configurações carregadas.
    """
    if config_path is None:
        # Procurar em locais padrão
        possible_paths = [
            Path("config/config.yaml"),
            Path("config.yaml"),
            Path.home() / ".config" / "voice-processor" / "config.yaml",
            Path("/etc/voice-processor/config.yaml"),
        ]

        for path in possible_paths:
            if path.exists():
                config_path = str(path)
                break
        else:
            # Retorna configuração padrão
            return Config()

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de configuração não encontrado: {config_path}")

    with open(path, "r", encoding="utf-8") as f:
        raw_config = yaml.safe_load(f)

    # Processar variáveis de ambiente
    processed_config = process_config_values(raw_config)

    return Config.from_dict(processed_config)


def get_project_root() -> Path:
    """Retorna o diretório raiz do projeto."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "config").is_dir() or (parent / "src").is_dir():
            return parent
    return current.parent.parent.parent
