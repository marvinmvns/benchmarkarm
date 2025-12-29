"""
Pipeline de processamento de voz.
Integra captura de áudio, transcrição e LLM.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional, Callable, Literal

from .audio.capture import AudioCapture, AudioBuffer
from .audio.vad import VoiceActivityDetector, validate_audio_has_speech, validate_audio_file_has_speech
from .transcription.whisper import WhisperTranscriber, TranscriptionResult, get_transcriber
from .llm.base import LLMProvider, LLMResponse
from .llm.local import LocalLLM
from .llm.api import OpenAIProvider, AnthropicProvider, OllamaProvider, ChatMockProvider
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
            'whisperapi_urls': getattr(whisper_config, 'whisperapi_urls', []),  # Lista de servidores para Round Robin
            'whisperapi_timeout': getattr(whisper_config, 'whisperapi_timeout', 300),
        }
        self.transcriber = get_transcriber(config_dict)
        urls_count = len(config_dict.get('whisperapi_urls', [])) or 1
        logger.info(f"Transcritor inicializado: {config_dict.get('provider', 'local')} ({urls_count} servidores)")

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
                use_server_mode=getattr(local_cfg, 'use_server_mode', True),
                server_port=getattr(local_cfg, 'server_port', 8080),
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
        elif provider == "chatmock":
            chatmock_cfg = llm_config.chatmock
            self.llm = ChatMockProvider(
                model=chatmock_cfg.model,
                max_tokens=chatmock_cfg.max_tokens,
                temperature=chatmock_cfg.temperature,
                base_url=chatmock_cfg.base_url,
                reasoning_effort=chatmock_cfg.reasoning_effort,
                enable_web_search=chatmock_cfg.enable_web_search,
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
        skip_vad: bool = False,
    ) -> TranscriptionResult:
        """
        Transcreve áudio.

        Args:
            audio: Buffer de áudio
            language: Idioma (usa configuração se None)
            skip_vad: Se True, pula validação VAD (use quando já validado)

        Returns:
            Resultado da transcrição
        """
        # Validação VAD é apenas informativa no pipeline
        # Não bloqueia transcrição - deixa o servidor decidir
        if not skip_vad and self.config.audio.vad_enabled:
            has_speech, confidence, duration, energy = validate_audio_has_speech(
                audio.data, sample_rate=audio.sample_rate
            )
            if not has_speech:
                logger.info(
                    f"🔍 VAD (Pipeline): baixa confiança de fala "
                    f"(confidence={confidence:.2f}, energy={energy:.0f}), "
                    f"prosseguindo com transcrição mesmo assim"
                )
                # NÃO retorna vazio - continua com transcrição
                # O servidor/transcriber decide se há conteúdo útil


        # Verificar cache
        if self.cache:
            cache_key = f"transcribe:{hash(audio.data.tobytes())}"
            cached = self.cache.get(cache_key)
            if cached:
                logger.debug("Transcrição obtida do cache")
                return TranscriptionResult(**cached)

        # Transcrever com fallback para local se API falhar
        result = None
        used_fallback = False
        
        try:
            result = self.transcriber.transcribe(audio, language)
        except Exception as e:
            error_str = str(e).lower()
            
            # Erros de conexão ou job perdido que justificam fallback para local
            is_connection_error = any(x in error_str for x in [
                'connection refused', 'connection error', 'timeout',
                'errno 111', 'unreachable', 'network', 'refused',
                'job not found', 'job não encontrado'
            ])
            
            if (is_connection_error or isinstance(e, ValueError)) and self.config.whisper.provider != "local":
                logger.warning(f"⚠️ WhisperAPI falhou ({e}), tentando fallback para local...")
                
                try:
                    # Criar transcriber local temporário
                    local_transcriber = get_transcriber(
                        provider="local",
                        model="tiny",  # Modelo mais leve para fallback rápido
                        model_path=self.config.whisper.local.model_path,
                        language=language or self.config.whisper.language,
                    )
                    
                    result = local_transcriber.transcribe(audio, language)
                    used_fallback = True
                    logger.info("✅ Fallback para Whisper local bem sucedido!")
                    
                except Exception as fallback_error:
                    logger.error(f"❌ Fallback para local também falhou: {fallback_error}")
                    raise RuntimeError(f"Transcrição falhou (API e local): {e} / {fallback_error}")
            else:
                # Erro não é de conexão ou já é local, re-raise
                raise
        
        if result is None:
            raise RuntimeError("Transcrição retornou resultado nulo")
        
        # Marcar se usou fallback
        if used_fallback:
            result.model = f"{result.model} (fallback)"

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
        status_callback: Optional[Callable[[str, dict], None]] = None,
    ) -> ProcessingResult:
        """
        Processa áudio completo: gravação -> transcrição -> LLM.

        Args:
            audio: Buffer de áudio (se None, grava novo)
            generate_summary: Se deve gerar resumo
            summary_style: Estilo do resumo
            custom_prompt: Prompt customizado para LLM
            status_callback: Função callback(stage_name, details_dict)

        Returns:
            Resultado completo do processamento
        """
        start_time = time.time()

        # Gravar se necessário
        if audio is None:
            if status_callback:
                status_callback("recording", {})
            logger.info("Iniciando gravação...")
            audio = self.record()
            logger.info(f"Gravação concluída: {audio.duration:.1f}s")

        # Transcrever
        if status_callback:
            status_callback("transcribing", {
                "provider": self.config.whisper.provider,
                "model": self.config.whisper.model,
                "duration": round(audio.duration, 1)
            })
        logger.info("Transcrevendo áudio...")
        transcription = self.transcribe(audio)
        logger.info(f"Transcrição concluída: {len(transcription.text)} caracteres")

        # Processar com LLM
        llm_response = None
        if self.llm and generate_summary and transcription.text.strip():
            if status_callback:
                status_callback("llm_processing", {
                    "provider": self.config.llm.provider,
                })
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
        skip_vad: bool = False,
    ) -> ProcessingResult:
        """
        Processa arquivo de áudio.

        Args:
            file_path: Caminho do arquivo WAV
            generate_summary: Se deve gerar resumo
            summary_style: Estilo do resumo
            skip_vad: Se True, pula validação VAD

        Returns:
            Resultado do processamento
        """
        # Validação VAD antes de carregar o arquivo completo
        if not skip_vad and self.config.audio.vad_enabled:
            has_speech, confidence, duration, energy = validate_audio_file_has_speech(
                file_path, aggressiveness=2, min_speech_duration=0.3
            )
            if not has_speech:
                logger.info(
                    f"⏭️ VAD (process_file): Arquivo sem fala detectada "
                    f"(confidence={confidence:.2f}, energy={energy:.0f})"
                )
                # Retornar resultado vazio sem carregar o arquivo
                empty_transcription = TranscriptionResult(
                    text="",
                    language=self.config.whisper.language,
                    duration=duration,
                    processing_time=0.0,
                    model=self.config.whisper.model,
                    segments=[],
                )
                return ProcessingResult(
                    audio_duration=duration,
                    transcription=empty_transcription,
                    llm_response=None,
                    total_time=0.0,
                    cached=False,
                )

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
