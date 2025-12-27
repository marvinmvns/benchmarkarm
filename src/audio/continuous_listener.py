"""
Módulo de Escuta Contínua.

Escuta o microfone (ReSpeaker HAT) continuamente e transcreve
automaticamente todo áudio detectado com Whisper e LLM.
"""

import logging
import os
import signal
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, List

from ..audio.capture import AudioCapture, AudioBuffer
from ..audio.vad import VoiceActivityDetector
from ..utils.config import Config, load_config, USBReceiverConfig

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionSegment:
    """Segmento de transcrição."""
    timestamp: datetime
    audio_duration: float
    text: str
    summary: Optional[str] = None
    audio_file: Optional[str] = None
    processing_time: float = 0.0
    server_url: Optional[str] = None  # Servidor WhisperAPI que processou
    server_name: Optional[str] = None  # Nome amigável do servidor
    success: bool = True  # Se a transcrição foi bem-sucedida
    retry_count: int = 0  # Número de tentativas até sucesso
    error_message: Optional[str] = None  # Mensagem de erro se falhou

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "audio_duration": self.audio_duration,
            "text": self.text,
            "summary": self.summary,
            "audio_file": self.audio_file,
            "processing_time": self.processing_time,
            "server_url": self.server_url,
            "server_name": self.server_name,
            "success": self.success,
            "retry_count": self.retry_count,
            "error_message": self.error_message,
        }


class ContinuousListener:
    """
    Escuta contínua com transcrição automática.
    
    Usa o ReSpeaker HAT para capturar áudio ambiente,
    detecta fala com VAD, e processa automaticamente
    com Whisper e LLM.
    
    Exemplo de uso:
        listener = ContinuousListener()
        listener.start()  # Começa a escutar em background
        
        # ... aplicação continua rodando ...
        
        listener.stop()   # Para a escuta
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        config_path: Optional[str] = None,
        on_transcription: Optional[Callable[[TranscriptionSegment], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ):
        """
        Inicializa o listener.
        
        Args:
            config: Configuração (se None, carrega do arquivo)
            config_path: Caminho do arquivo de configuração
            on_transcription: Callback quando uma transcrição é completada
            on_error: Callback quando ocorre um erro
        """
        self.config = config or load_config(config_path)
        self.usb_config: USBReceiverConfig = self.config.usb_receiver
        
        self._on_transcription = on_transcription
        self._on_error = on_error
        
        # Estado
        self._running = False
        self._paused = False
        self._thread: Optional[threading.Thread] = None
        self._segments: List[TranscriptionSegment] = []
        
        # Componentes (inicializados sob demanda)
        self._audio: Optional[AudioCapture] = None
        self._vad: Optional[VoiceActivityDetector] = None
        self._processor = None  # VoiceProcessor lazy-loaded
        
        # Diretório de gravações
        if self.usb_config.use_ram_storage:
            # Tentar usar /dev/shm/ (Shared Memory) para evitar escrita em SD
            ram_path = Path("/dev/shm")
            if ram_path.exists():
                self._save_dir = ram_path / "voice-processor"
                logger.info("💾 Usando RAM (/dev/shm) para gravação temporária")
            else:
                self._save_dir = Path("/tmp/voice-processor")
                logger.warning("⚠️ /dev/shm não encontrado, usando /tmp para gravação temporária")
        else:
            self._save_dir = Path(os.path.expanduser(self.usb_config.save_directory))
        
        logger.info("ContinuousListener inicializado")

    def _init_components(self) -> None:
        """Inicializa componentes de áudio."""
        audio_config = self.config.audio
        
        # Captura de áudio usando ReSpeaker
        self._audio = AudioCapture(
            device=audio_config.device,
            sample_rate=audio_config.sample_rate,
            channels=audio_config.channels,
            chunk_size=audio_config.chunk_size,
            max_duration=int(self.usb_config.max_audio_duration),
        )
        
        # VAD para detectar fala
        if audio_config.vad_enabled:
            self._vad = VoiceActivityDetector(
                sample_rate=audio_config.sample_rate,
                aggressiveness=audio_config.vad_aggressiveness,
                min_speech_duration=audio_config.min_speech_duration,
            )
        
        # Criar diretório de gravações
        self._save_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Componentes inicializados. Gravações em: {self._save_dir}")

    def _get_processor(self):
        """Obtém VoiceProcessor (lazy loading)."""
        if self._processor is None:
            from ..pipeline import VoiceProcessor
            self._processor = VoiceProcessor(config=self.config)
        return self._processor

    def start(self) -> None:
        """Inicia escuta contínua em background."""
        if self._running:
            logger.warning("Listener já está rodando")
            return
        
        if not self.usb_config.enabled:
            logger.warning("Escuta contínua não está habilitada na configuração")
            return
        
        if not self.usb_config.continuous_listen:
            logger.warning("Modo de escuta contínua não está ativo")
            return
        
        try:
            logger.info("🚀 Inicializando componentes de áudio...")
            self._init_components()
            logger.info("✅ Componentes inicializados com sucesso")
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar componentes: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return
        
        self._running = True
        self._paused = False
        
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        
        logger.info("🎧 Escuta contínua iniciada - Thread ativa")

    def stop(self) -> None:
        """Para a escuta contínua."""
        if not self._running:
            return
        
        self._running = False
        
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        
        if self._audio:
            self._audio.close()
            self._audio = None
        
        logger.info("🛑 Escuta contínua parada")

    def pause(self) -> None:
        """Pausa a escuta (não processa novos áudios)."""
        self._paused = True
        logger.info("⏸️ Escuta pausada")

    def resume(self) -> None:
        """Retoma a escuta."""
        self._paused = False
        logger.info("▶️ Escuta retomada")

    def _listen_loop(self) -> None:
        """Loop principal de escuta."""
        logger.info("Loop de escuta iniciado")
        
        while self._running:
            try:
                if self._paused:
                    time.sleep(0.5)
                    continue
                
                # Gravar áudio até detectar silêncio
                audio = self._audio.record(
                    duration=self.usb_config.max_audio_duration,
                    stop_on_silence=self.usb_config.silence_split,
                    silence_duration=self.usb_config.silence_threshold,
                    vad=self._vad,
                )
                
                # Verificar duração mínima
                if audio.duration < self.usb_config.min_audio_duration:
                    logger.debug(f"Áudio muito curto: {audio.duration:.1f}s < {self.usb_config.min_audio_duration}s")
                    continue

                # Verificar se há fala (validação VAD do AudioBuffer)
                if hasattr(audio, 'has_speech') and not audio.has_speech:
                    logger.debug(
                        f"⏭️ Áudio sem fala detectada (VAD), pulando processamento "
                        f"(confidence={getattr(audio, 'vad_confidence', 0):.2f})"
                    )
                    continue

                # Processar áudio
                self._process_audio(audio)
                
            except Exception as e:
                logger.error(f"Erro no loop de escuta: {e}")
                if self._on_error:
                    self._on_error(e)
                time.sleep(1)  # Evitar loop de erro rápido
        
        logger.info("Loop de escuta encerrado")

    def _process_audio(self, audio: AudioBuffer) -> None:
        """Processa um segmento de áudio."""
        start_time = time.time()
        timestamp = datetime.now()

        logger.info(f"📝 Processando áudio: {audio.duration:.1f}s")

        # Nome do arquivo para salvar
        filename = f"audio_{timestamp.strftime('%Y%m%d_%H%M%S')}.wav"
        audio_file_path = str(self._save_dir / filename)

        # Sempre salvar áudio primeiro (para garantir que não se perca)
        # Será removido após transcrição bem sucedida
        audio_file = None
        try:
            audio.save(audio_file_path)
            audio_file = audio_file_path
            logger.debug(f"Áudio salvo: {audio_file}")
        except Exception as e:
            logger.error(f"Erro ao salvar áudio: {e}")

        # Transcrever
        text = ""
        summary = None
        transcription_success = False
        server_url = None
        server_name = None
        error_message = None

        if self.usb_config.auto_transcribe:
            try:
                processor = self._get_processor()
                transcription = processor.transcribe(audio)
                text = transcription.text.strip() if transcription.text else ""

                # Extrair informações do servidor
                server_url = getattr(transcription, 'server_url', None)
                server_name = getattr(transcription, 'server_name', None)

                # Se não houver texto, apenas limpar o arquivo e não registrar
                if not text or text.startswith("[Erro"):
                    logger.info(f"⏭️ Áudio sem texto útil - descartando: {filename}")
                    if audio_file:
                        try:
                            Path(audio_file).unlink()
                            logger.debug(f"🗑️ Áudio sem texto removido: {filename}")
                        except Exception:
                            pass
                    return  # Não registra nada

                transcription_success = True

                logger.info(
                    f"✅ Transcrição ({server_name or 'local'}): "
                    f"{text[:100]}..." if len(text) > 100 else f"✅ Transcrição ({server_name or 'local'}): {text}"
                )

                # Gerar resumo (opcional - não falha processamento se der erro)
                if self.usb_config.auto_summarize and text and processor.llm:
                    try:
                        response = processor.summarize(text)
                        summary = response.text
                        logger.info(f"📋 Resumo: {summary[:100]}..." if len(summary) > 100 else f"📋 Resumo: {summary}")
                    except Exception as e:
                        logger.warning(f"⚠️ Erro ao gerar resumo (sem internet ou LLM indisponível): {e}")
                        # Continua sem resumo - transcrição já foi salva

                # SEMPRE remover .wav após transcrição bem sucedida (arquivos são grandes)
                if transcription_success and audio_file:
                    try:
                        Path(audio_file).unlink()
                        logger.debug(f"🗑️ Áudio removido após transcrição bem-sucedida: {filename}")
                        audio_file = None
                    except Exception as cleanup_error:
                        logger.warning(f"Erro ao remover áudio: {cleanup_error}")

            except Exception as e:
                logger.error(f"❌ Erro na transcrição: {e}")
                error_message = str(e)
                text = f"[Erro na transcrição: {e}]"
                # Áudio permanece salvo para processamento posterior pelo batch_processor
                logger.info("📂 Áudio mantido para reprocessamento posterior")

        processing_time = time.time() - start_time

        # Criar segmento com todas as informações
        segment = TranscriptionSegment(
            timestamp=timestamp,
            audio_duration=audio.duration,
            text=text,
            summary=summary,
            audio_file=audio_file,
            processing_time=processing_time,
            server_url=server_url,
            server_name=server_name,
            success=transcription_success,
            error_message=error_message,
        )

        # Armazenar e notificar
        self._segments.append(segment)

        # Salvar no banco de dados persistente
        try:
            from ..utils.transcription_store import get_transcription_store, TranscriptionRecord
            store = get_transcription_store()
            record = TranscriptionRecord(
                id=str(uuid.uuid4()),
                timestamp=timestamp,
                duration_seconds=audio.duration,
                text=text,
                summary=summary,
                audio_file=audio_file,
                language=self.config.whisper.language or "pt",
                processed_by=server_name or self.config.whisper.provider or "local",
            )
            store.save(record)
            logger.debug(f"Transcrição salva no banco: {record.id}")
        except Exception as e:
            logger.warning(f"Erro ao salvar transcrição no banco: {e}")

        # Limitar histórico em memória
        if len(self._segments) > 100:
            self._segments = self._segments[-50:]

        # Callback
        if self._on_transcription:
            self._on_transcription(segment)

        status_emoji = "✅" if transcription_success else "❌"
        logger.info(f"{status_emoji} Processamento concluído em {processing_time:.1f}s")

    def get_segments(
        self,
        limit: int = 20,
        filter_status: Optional[str] = None,
    ) -> List[TranscriptionSegment]:
        """
        Retorna os últimos segmentos transcritos.

        Args:
            limit: Número máximo de segmentos a retornar
            filter_status: Filtro de status ('success', 'error', ou None para todos)

        Returns:
            Lista de segmentos filtrados
        """
        segments = self._segments

        if filter_status == 'success':
            segments = [s for s in segments if s.success]
        elif filter_status == 'error':
            segments = [s for s in segments if not s.success]

        return segments[-limit:]

    def get_segments_by_server(self, server_name: str, limit: int = 20) -> List[TranscriptionSegment]:
        """
        Retorna segmentos processados por um servidor específico.

        Args:
            server_name: Nome do servidor (ex: 'whisper-121')
            limit: Número máximo de segmentos

        Returns:
            Lista de segmentos do servidor
        """
        segments = [s for s in self._segments if s.server_name == server_name]
        return segments[-limit:]

    def get_segment_stats(self) -> dict:
        """
        Retorna estatísticas dos segmentos.

        Returns:
            Dict com contagens de sucesso/erro e por servidor
        """
        total = len(self._segments)
        success = sum(1 for s in self._segments if s.success)
        errors = total - success

        # Contar por servidor
        server_counts = {}
        for seg in self._segments:
            server = seg.server_name or 'unknown'
            server_counts[server] = server_counts.get(server, 0) + 1

        return {
            "total": total,
            "success": success,
            "errors": errors,
            "success_rate": (success / total * 100) if total > 0 else 0,
            "by_server": server_counts,
        }

    def clear_segments(self) -> None:
        """Limpa o histórico de segmentos."""
        self._segments.clear()

    @property
    def is_running(self) -> bool:
        """Verifica se está rodando."""
        return self._running

    @property
    def is_paused(self) -> bool:
        """Verifica se está pausado."""
        return self._paused

    @property
    def status(self) -> dict:
        """Retorna status atual."""
        return {
            "running": self._running,
            "paused": self._paused,
            "segments_count": len(self._segments),
            "enabled": self.usb_config.enabled,
            "continuous_listen": self.usb_config.continuous_listen,
            "save_directory": str(self._save_dir),
        }


# Instância global para acesso fácil
_global_listener: Optional[ContinuousListener] = None


def get_listener(
    config: Optional[Config] = None,
    config_path: Optional[str] = None,
) -> ContinuousListener:
    """
    Obtém instância global do listener.
    
    Args:
        config: Configuração opcional
        config_path: Caminho da configuração
        
    Returns:
        Instância do ContinuousListener
    """
    global _global_listener
    
    if _global_listener is None:
        _global_listener = ContinuousListener(
            config=config,
            config_path=config_path,
        )
    
    return _global_listener


def start_listening(config_path: Optional[str] = None) -> ContinuousListener:
    """
    Inicia escuta contínua.
    
    Args:
        config_path: Caminho da configuração
        
    Returns:
        Instância do listener
    """
    listener = get_listener(config_path=config_path)
    listener.start()
    return listener


def stop_listening() -> None:
    """Para escuta contínua."""
    global _global_listener
    
    if _global_listener:
        _global_listener.stop()
        _global_listener = None
