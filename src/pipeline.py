"""
Pipeline de processamento de voz.
Integra captura de áudio, transcrição e LLM.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional, Callable, Literal

from .audio.capture import AudioCapture, AudioBuffer
from .audio.vad import VoiceActivityDetector
from .transcription.whisper import WhisperTranscriber, TranscriptionResult, get_transcriber
from .llm.base import LLMProvider, LLMResponse
from .llm.local import LocalLLM
from .llm.api import OpenAIProvider, AnthropicProvider, OllamaProvider
from .utils.config import Config, load_config
from .utils.cache import Cache, get_cache

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Resultado completo do processamento."""
    audio_duration: float
    transcription: TranscriptionResult
    llm_response: Optional[LLMResponse] = None
    total_time: float = 0.0
    cached: bool = False

    @property
    def text(self) -> str:
        """Texto transcrito."""
        return self.transcription.text

    @property
    def summary(self) -> Optional[str]:
        """Resumo gerado (se disponível)."""
        return self.llm_response.text if self.llm_response else None

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "audio_duration": self.audio_duration,
            "transcription": self.transcription.to_dict(),
            "llm_response": self.llm_response.to_dict() if self.llm_response else None,
            "total_time": self.total_time,
            "cached": self.cached,
        }


class VoiceProcessor:
    """
    Processador de voz principal.

    Pipeline:
    1. Captura de áudio (ReSpeaker)
    2. VAD (detecção de fala)
    3. Transcrição (Whisper)
    4. Processamento LLM (resumo, extração, etc.)
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        config_path: Optional[str] = None,
    ):
        """
        Inicializa o processador.

        Args:
            config: Configuração (se None, carrega do arquivo)
            config_path: Caminho do arquivo de configuração
        """
        self.config = config or load_config(config_path)

        # Inicializar componentes
        self._init_audio()
        self._init_vad()
        self._init_transcriber()
        self._init_llm()
        self._init_cache()

        logger.info(f"VoiceProcessor inicializado (modo: {self.config.mode})")

    def _init_audio(self) -> None:
        """Inicializa captura de áudio."""
        audio_config = self.config.audio
        self.audio = AudioCapture(
            device=audio_config.device,
            sample_rate=audio_config.sample_rate,
            channels=audio_config.channels,
            chunk_size=audio_config.chunk_size,
            max_duration=audio_config.max_duration,
        )

    def _init_vad(self) -> None:
        """Inicializa detector de voz."""
        audio_config = self.config.audio
        if audio_config.vad_enabled:
            self.vad = VoiceActivityDetector(
                sample_rate=audio_config.sample_rate,
                aggressiveness=audio_config.vad_aggressiveness,
                min_speech_duration=audio_config.min_speech_duration,
            )
        else:
            self.vad = None

    def _init_transcriber(self) -> None:
        """Inicializa transcritor Whisper baseado no provider configurado."""
        whisper_config = self.config.whisper
        # Usar factory function que respeita o provider (local, whisperapi, openai)
        config_dict = {
            'provider': getattr(whisper_config, 'provider', 'local'),
            'model': whisper_config.model,
            'language': whisper_config.language,
            'use_cpp': whisper_config.use_cpp,
            'threads': max(1, whisper_config.threads),  # Mínimo 1 thread para usar swap
            'beam_size': whisper_config.beam_size,
            'stream_mode': getattr(whisper_config, 'stream_mode', False),
            'whisperapi_url': getattr(whisper_config, 'whisperapi_url', 'http://127.0.0.1:3001'),
            'whisperapi_timeout': getattr(whisper_config, 'whisperapi_timeout', 300),
        }
        self.transcriber = get_transcriber(config_dict)
        logger.info(f"Transcritor inicializado: {config_dict.get('provider', 'local')}")

    def _init_llm(self) -> None:
        """Inicializa provedor LLM."""
        llm_config = self.config.llm
        provider = llm_config.provider

        if provider == "local":
            local_cfg = llm_config.local
            self.llm = LocalLLM(
                model=local_cfg.model,
                model_path=local_cfg.model_path or None,
                context_size=local_cfg.context_size,
                threads=local_cfg.threads,
                max_tokens=local_cfg.max_tokens,
                temperature=local_cfg.temperature,
            )
        elif provider == "openai":
            openai_cfg = llm_config.openai
            self.llm = OpenAIProvider(
                model=openai_cfg.model,
                max_tokens=openai_cfg.max_tokens,
                temperature=openai_cfg.temperature,
                api_key=openai_cfg.api_key or None,
            )
        elif provider == "anthropic":
            anthropic_cfg = llm_config.anthropic
            self.llm = AnthropicProvider(
                model=anthropic_cfg.model,
                max_tokens=anthropic_cfg.max_tokens,
                temperature=anthropic_cfg.temperature,
                api_key=anthropic_cfg.api_key or None,
            )
        elif provider == "ollama":
            ollama_cfg = llm_config.ollama
            self.llm = OllamaProvider(
                model=ollama_cfg.model,
                max_tokens=ollama_cfg.max_tokens,
                host=ollama_cfg.host,
            )
        else:
            logger.warning(f"Provedor LLM desconhecido: {provider}")
            self.llm = None

    def _init_cache(self) -> None:
        """Inicializa cache."""
        system_config = self.config.system
        if system_config.cache_enabled:
            self.cache = Cache(
                cache_dir=system_config.cache_dir,
                ttl=system_config.cache_ttl,
                enabled=True,
            )
        else:
            self.cache = None

    def record(
        self,
        duration: Optional[float] = None,
        stop_on_silence: bool = True,
    ) -> AudioBuffer:
        """
        Grava áudio.

        Args:
            duration: Duração máxima em segundos
            stop_on_silence: Parar quando detectar silêncio

        Returns:
            Buffer de áudio gravado
        """
        return self.audio.record(
            duration=duration,
            stop_on_silence=stop_on_silence,
            silence_duration=self.config.audio.silence_duration,
            vad=self.vad,
        )

    def transcribe(
        self,
        audio: AudioBuffer,
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        """
        Transcreve áudio.

        Args:
            audio: Buffer de áudio
            language: Idioma (usa configuração se None)

        Returns:
            Resultado da transcrição
        """
        # Verificar cache
        if self.cache:
            cache_key = f"transcribe:{hash(audio.data.tobytes())}"
            cached = self.cache.get(cache_key)
            if cached:
                logger.debug("Transcrição obtida do cache")
                return TranscriptionResult(**cached)

        # Transcrever
        result = self.transcriber.transcribe(audio, language)

        # Salvar no cache
        if self.cache:
            self.cache.set(cache_key, result.to_dict())

        return result

    def summarize(
        self,
        text: str,
        style: str = "concise",
    ) -> LLMResponse:
        """
        Resume texto usando LLM.

        Args:
            text: Texto a resumir
            style: Estilo do resumo

        Returns:
            Resposta do LLM
        """
        if self.llm is None:
            raise RuntimeError("LLM não configurado")

        # Verificar cache
        if self.cache:
            cache_key = f"summarize:{hash(text)}:{style}"
            cached = self.cache.get(cache_key)
            if cached:
                logger.debug("Resumo obtido do cache")
                cached["cached"] = True
                return LLMResponse(**cached)

        # Gerar resumo
        response = self.llm.summarize(text, style=style)

        # Salvar no cache
        if self.cache:
            self.cache.set(cache_key, response.to_dict())

        return response

    def process(
        self,
        audio: Optional[AudioBuffer] = None,
        generate_summary: bool = True,
        summary_style: str = "concise",
        custom_prompt: Optional[str] = None,
    ) -> ProcessingResult:
        """
        Processa áudio completo: gravação -> transcrição -> LLM.

        Args:
            audio: Buffer de áudio (se None, grava novo)
            generate_summary: Se deve gerar resumo
            summary_style: Estilo do resumo
            custom_prompt: Prompt customizado para LLM

        Returns:
            Resultado completo do processamento
        """
        start_time = time.time()

        # Gravar se necessário
        if audio is None:
            logger.info("Iniciando gravação...")
            audio = self.record()
            logger.info(f"Gravação concluída: {audio.duration:.1f}s")

        # Transcrever
        logger.info("Transcrevendo áudio...")
        transcription = self.transcribe(audio)
        logger.info(f"Transcrição concluída: {len(transcription.text)} caracteres")

        # Processar com LLM
        llm_response = None
        if self.llm and generate_summary and transcription.text.strip():
            logger.info("Processando com LLM...")

            if custom_prompt:
                llm_response = self.llm.custom_prompt(
                    custom_prompt,
                    transcription.text,
                )
            else:
                llm_response = self.summarize(
                    transcription.text,
                    style=summary_style,
                )

            logger.info("Processamento LLM concluído")

        total_time = time.time() - start_time

        return ProcessingResult(
            audio_duration=audio.duration,
            transcription=transcription,
            llm_response=llm_response,
            total_time=total_time,
        )

    def process_file(
        self,
        file_path: str,
        generate_summary: bool = True,
        summary_style: str = "concise",
    ) -> ProcessingResult:
        """
        Processa arquivo de áudio.

        Args:
            file_path: Caminho do arquivo WAV
            generate_summary: Se deve gerar resumo
            summary_style: Estilo do resumo

        Returns:
            Resultado do processamento
        """
        audio = AudioBuffer.from_file(file_path)
        return self.process(
            audio=audio,
            generate_summary=generate_summary,
            summary_style=summary_style,
        )

    def continuous_listen(
        self,
        callback: Callable[[ProcessingResult], None],
        min_duration: float = 1.0,
        generate_summary: bool = False,
    ) -> None:
        """
        Escuta continuamente e processa fala detectada.

        Args:
            callback: Função chamada com resultado de cada processamento
            min_duration: Duração mínima de áudio para processar
            generate_summary: Se deve gerar resumo para cada segmento
        """
        logger.info("Iniciando escuta contínua...")

        try:
            while True:
                # Gravar
                audio = self.record()

                # Pular se muito curto
                if audio.duration < min_duration:
                    continue

                # Processar
                result = self.process(
                    audio=audio,
                    generate_summary=generate_summary,
                )

                # Callback
                if result.transcription.text.strip():
                    callback(result)

        except KeyboardInterrupt:
            logger.info("Escuta contínua interrompida")

    def get_status(self) -> dict:
        """Retorna status do processador."""
        return {
            "mode": self.config.mode,
            "audio": {
                "sample_rate": self.config.audio.sample_rate,
                "vad_enabled": self.vad is not None,
            },
            "whisper": {
                "model": self.config.whisper.model,
                "use_cpp": self.config.whisper.use_cpp,
            },
            "llm": {
                "provider": self.config.llm.provider,
                "available": self.llm.is_available() if self.llm else False,
            },
            "cache": {
                "enabled": self.cache is not None,
                "stats": self.cache.get_stats() if self.cache else None,
            },
        }

    def cleanup(self) -> None:
        """Limpa recursos."""
        if self.audio:
            self.audio.close()
        if self.cache:
            self.cache.cleanup_expired()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False
