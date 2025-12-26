"""
Processador em Lote de Transcrições.

Processa arquivos .wav pendentes, transcreve com Whisper,
salva como .txt e remove os arquivos de áudio originais.

Integração com JobManager:
- Tracking persistente de jobs
- Retry automático de jobs falhos
- Recuperação de jobs pendentes no restart
"""

import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..transcription.job_manager import JobManager

logger = logging.getLogger(__name__)


@dataclass
class ProcessingStats:
    """Estatísticas de processamento."""
    pending_files: int = 0
    processed_files: int = 0
    failed_files: int = 0
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    is_running: bool = False
    current_file: Optional[str] = None


@dataclass
class TranscriptionFile:
    """Representação de um arquivo de transcrição."""
    name: str
    path: str
    size: int
    created: datetime
    audio_duration: Optional[float] = None
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "size": self.size,
            "created": self.created.isoformat(),
            "audio_duration": self.audio_duration,
        }


class BatchProcessor:
    """
    Processador em lote de arquivos de áudio.

    Funcionalidades:
    - Escaneia diretório por arquivos .wav pendentes
    - Transcreve com Whisper
    - Salva resultado como .txt com metadados
    - Remove .wav após sucesso
    - Executa periodicamente ou quando CPU está baixo

    Integração com JobManager:
    - Retry automático de jobs falhos
    - Recuperação de jobs pendentes no restart
    - Monitoramento de saúde dos servidores WhisperAPI
    """

    def __init__(
        self,
        audio_dir: str = "~/audio-recordings",
        interval_minutes: int = 5,
        max_files_per_run: int = 10,
        cpu_threshold: float = 30.0,
        config_path: Optional[str] = None,
        use_job_manager: bool = True,
    ):
        """
        Inicializa o processador.

        Args:
            audio_dir: Diretório com arquivos de áudio
            interval_minutes: Intervalo entre execuções (minutos)
            max_files_per_run: Máximo de arquivos por execução
            cpu_threshold: Processar se CPU abaixo deste % (além do intervalo)
            config_path: Caminho do arquivo de configuração
            use_job_manager: Usar JobManager para tracking inteligente
        """
        self.audio_dir = Path(os.path.expanduser(audio_dir))
        self.interval_minutes = interval_minutes
        self.max_files_per_run = max_files_per_run
        self.cpu_threshold = cpu_threshold
        self.config_path = config_path
        self.use_job_manager = use_job_manager

        # Estado
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stats = ProcessingStats()
        self._failed_files: List[str] = []

        # Componentes (lazy loaded)
        self._transcriber = None
        self._job_manager: Optional["JobManager"] = None

        # Callbacks
        self._on_file_processed: Optional[Callable] = None
        self._on_error: Optional[Callable] = None

        # Inicializar JobManager se habilitado
        if use_job_manager:
            try:
                from ..transcription.job_manager import get_job_manager
                self._job_manager = get_job_manager()
                logger.info("🧠 BatchProcessor integrado com JobManager")
            except Exception as e:
                logger.warning(f"JobManager não disponível: {e}")
                self._job_manager = None

        logger.info(f"BatchProcessor inicializado: dir={self.audio_dir}")
    
    def _get_transcriber(self):
        """Obtém transcritor Whisper (lazy loading) - respeita provider configurado."""
        if self._transcriber is None:
            try:
                from ..transcription.whisper import get_transcriber
                from ..utils.config import load_config

                config = load_config(self.config_path)
                whisper_config = config.whisper

                # CRÍTICO: Usar factory function que respeita o provider (local, whisperapi, openai)
                config_dict = {
                    'provider': getattr(whisper_config, 'provider', 'local'),
                    'model': whisper_config.model,
                    'language': whisper_config.language,
                    'use_cpp': whisper_config.use_cpp,
                    'threads': whisper_config.threads,
                    'beam_size': whisper_config.beam_size,
                    'quantization': whisper_config.quantization,
                    'stream_mode': getattr(whisper_config, 'stream_mode', False),
                    # WhisperAPI settings - use correct config attribute names
                    'whisperapi_url': getattr(whisper_config, 'whisperapi_url', 'http://127.0.0.1:3001'),
                    'whisperapi_urls': getattr(whisper_config, 'whisperapi_urls', []),
                    'whisperapi_timeout': getattr(whisper_config, 'whisperapi_timeout', 300),
                }

                self._transcriber = get_transcriber(config_dict)
                logger.info(f"BatchProcessor usando Whisper provider: {config_dict.get('provider', 'local')}")
                if config_dict['provider'] == 'whisperapi':
                    logger.info(f"WhisperAPI URL: {config_dict['whisperapi_url']}")
            except Exception as e:
                logger.error(f"Erro ao criar transcritor: {e}")
                raise
        return self._transcriber
    
    def _get_cpu_usage(self) -> float:
        """Retorna uso de CPU em porcentagem."""
        try:
            with open("/proc/stat", "r") as f:
                line = f.readline()
                parts = line.split()
                idle = int(parts[4])
                total = sum(int(p) for p in parts[1:])
                
            time.sleep(0.1)
            
            with open("/proc/stat", "r") as f:
                line = f.readline()
                parts = line.split()
                idle2 = int(parts[4])
                total2 = sum(int(p) for p in parts[1:])
            
            idle_delta = idle2 - idle
            total_delta = total2 - total
            
            if total_delta == 0:
                return 0.0
            
            return 100.0 * (1.0 - idle_delta / total_delta)
        except Exception:
            return 50.0  # Retorna valor médio se não conseguir ler
    
    def _should_process(self) -> bool:
        """Verifica se deve processar agora."""
        # Verificar se tem arquivos pendentes
        pending = self.get_pending_files()
        if not pending:
            return False
        
        # Verificar intervalo
        if self._stats.last_run:
            elapsed = (datetime.now() - self._stats.last_run).total_seconds()
            if elapsed >= self.interval_minutes * 60:
                return True
        else:
            return True  # Primeira execução
        
        # Verificar CPU baixo
        cpu = self._get_cpu_usage()
        if cpu < self.cpu_threshold:
            logger.debug(f"CPU baixo ({cpu:.1f}%), processando...")
            return True
        
        return False
    
    def get_pending_files(self) -> List[Path]:
        """Retorna lista de arquivos .wav pendentes, ordenados por data."""
        if not self.audio_dir.exists():
            return []
        
        wav_files = list(self.audio_dir.glob("*.wav"))
        
        # Ordenar por data de modificação (mais antigos primeiro)
        wav_files.sort(key=lambda f: f.stat().st_mtime)
        
        return wav_files
    
    def get_transcription_files(self) -> List[TranscriptionFile]:
        """Retorna lista de arquivos .txt de transcrição."""
        if not self.audio_dir.exists():
            return []
        
        txt_files = list(self.audio_dir.glob("*.txt"))
        result = []
        
        for f in txt_files:
            try:
                stat = f.stat()
                
                # Tentar extrair duração do conteúdo
                duration = None
                try:
                    content = f.read_text(encoding="utf-8")
                    for line in content.split("\n"):
                        if line.startswith("# Duração:"):
                            duration = float(line.split(":")[1].strip().rstrip("s"))
                            break
                except Exception:
                    pass
                
                result.append(TranscriptionFile(
                    name=f.name,
                    path=str(f),
                    size=stat.st_size,
                    created=datetime.fromtimestamp(stat.st_mtime),
                    audio_duration=duration,
                ))
            except Exception as e:
                logger.warning(f"Erro ao ler arquivo {f}: {e}")
        
        # Ordenar por data (mais recentes primeiro)
        result.sort(key=lambda x: x.created, reverse=True)
        
        return result
    
    def read_transcription(self, filename: str) -> Optional[str]:
        """Lê conteúdo de um arquivo de transcrição."""
        filepath = self.audio_dir / filename
        
        if not filepath.exists():
            return None
        
        if not filepath.suffix == ".txt":
            return None
        
        try:
            return filepath.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Erro ao ler {filename}: {e}")
            return None
    
    def delete_transcription(self, filename: str) -> bool:
        """Deleta um arquivo de transcrição."""
        filepath = self.audio_dir / filename
        
        if not filepath.exists():
            return False
        
        if not filepath.suffix == ".txt":
            return False
        
        try:
            filepath.unlink()
            logger.info(f"Arquivo deletado: {filename}")
            return True
        except Exception as e:
            logger.error(f"Erro ao deletar {filename}: {e}")
            return False
    
    def _validate_audio_has_speech(self, wav_path: Path) -> tuple:
        """
        Valida se o arquivo de áudio contém fala antes de enviar para transcrição.

        Args:
            wav_path: Caminho do arquivo .wav

        Returns:
            Tuple (has_speech: bool, confidence: float, duration: float)
        """
        try:
            import wave
            import numpy as np
            from ..audio.vad import VoiceActivityDetector

            # Ler arquivo WAV
            with wave.open(str(wav_path), 'rb') as wav:
                sample_rate = wav.getframerate()
                n_frames = wav.getnframes()
                duration = n_frames / sample_rate
                audio_bytes = wav.readframes(n_frames)

            # Converter para numpy array
            audio = np.frombuffer(audio_bytes, dtype=np.int16)

            # Usar VAD para verificar se há fala
            vad = VoiceActivityDetector(
                sample_rate=sample_rate,
                aggressiveness=2,  # Moderado
                min_speech_duration=0.3,
            )

            result = vad.is_speech(audio, return_details=True)

            logger.debug(
                f"VAD {wav_path.name}: speech={result.is_speech}, "
                f"confidence={result.confidence:.2f}, energy={result.energy:.0f}"
            )

            return result.is_speech, result.confidence, duration

        except Exception as e:
            logger.warning(f"Erro na validação VAD de {wav_path.name}: {e}")
            # Em caso de erro, assumir que tem fala para não descartar
            return True, 0.5, 0.0

    def process_file(self, wav_path: Path) -> bool:
        """
        Processa um arquivo .wav individual.

        Inclui validação VAD para evitar processar arquivos sem fala.

        Args:
            wav_path: Caminho do arquivo .wav

        Returns:
            True se processado com sucesso
        """
        logger.info(f"📝 Processando: {wav_path.name}")
        self._stats.current_file = wav_path.name

        # 1. Validar se há fala no áudio antes de enviar para transcrição
        has_speech, confidence, duration = self._validate_audio_has_speech(wav_path)

        if not has_speech:
            logger.info(
                f"⏭️ Pulando {wav_path.name}: sem fala detectada "
                f"(confidence={confidence:.2f}, duration={duration:.1f}s)"
            )
            # Remover arquivo sem fala para economizar espaço
            try:
                wav_path.unlink()
                logger.debug(f"🗑️ Arquivo sem fala removido: {wav_path.name}")
            except Exception:
                pass
            return True  # Considera "processado" pois não tinha conteúdo útil

        logger.debug(f"✅ VAD OK: {wav_path.name} (confidence={confidence:.2f})")

        retries = 3
        delay = 1.0

        try:
            for attempt in range(retries):
                try:
                    # Transcrever
                    transcriber = self._get_transcriber()
                    result = transcriber.transcribe(str(wav_path))
                    
                    # Criar conteúdo do .txt com metadados
                    txt_content = self._format_transcription(
                        wav_name=wav_path.name,
                        text=result.text,
                        duration=result.duration,
                        model=result.model,
                        language=result.language,
                        processing_time=result.processing_time,
                    )
                
                    # Salvar .txt
                    txt_path = wav_path.with_suffix(".txt")
                    txt_path.write_text(txt_content, encoding="utf-8")
                    logger.info(f"✅ Salvo: {txt_path.name}")
                    
                    # Remover .wav
                    wav_path.unlink()
                    logger.info(f"🗑️ Removido: {wav_path.name}")
                    
                    self._stats.processed_files += 1
                    
                    if self._on_file_processed:
                        self._on_file_processed(wav_path.name, txt_path.name)
                    
                    return True
                    
                except Exception as e:
                    logger.warning(f"Tentativa {attempt+1}/{retries} falhou para {wav_path.name}: {e}")
                    if attempt < retries - 1:
                        time.sleep(delay)
                        delay *= 2
                    else:
                        logger.error(f"❌ Erro ao processar após retries: {e}")
                        self._stats.failed_files += 1
                        self._failed_files.append(wav_path.name)
                        if self._on_error:
                            self._on_error(wav_path.name, str(e))
            
            return False
            
        finally:
            self._stats.current_file = None
    
    def _format_transcription(
        self,
        wav_name: str,
        text: str,
        duration: float,
        model: str,
        language: str,
        processing_time: float,
    ) -> str:
        """Formata transcrição com metadados."""
        now = datetime.now()
        
        content = f"""# Transcrição: {wav_name}
# Data: {now.strftime('%Y-%m-%d %H:%M:%S')}
# Timestamp: {now.isoformat()}
# Duração: {duration:.1f}s
# Modelo: {model}
# Idioma: {language}
# Tempo de processamento: {processing_time:.2f}s

{text.strip()}
"""
        return content
    
    def process_pending(self, max_files: Optional[int] = None) -> int:
        """
        Processa arquivos pendentes.
        
        Args:
            max_files: Máximo de arquivos (usa padrão se None)
            
        Returns:
            Número de arquivos processados com sucesso
        """
        if self._stats.is_running:
            logger.warning("Processamento já em andamento")
            return 0
        
        max_files = max_files or self.max_files_per_run
        pending = self.get_pending_files()
        
        if not pending:
            logger.info("Nenhum arquivo pendente")
            return 0
        
        self._stats.is_running = True
        self._stats.last_run = datetime.now()
        processed = 0
        
        try:
            for wav_path in pending[:max_files]:
                if self.process_file(wav_path):
                    processed += 1
        finally:
            self._stats.is_running = False
            self._stats.pending_files = len(self.get_pending_files())
        
        logger.info(f"✅ Processamento concluído: {processed}/{len(pending[:max_files])} arquivos")
        return processed
    
    def start(self) -> None:
        """Inicia processamento periódico em background."""
        if self._running:
            logger.warning("Processador já está rodando")
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        
        logger.info("🔄 Processador em lote iniciado")
    
    def stop(self) -> None:
        """Para o processamento periódico."""
        if not self._running:
            return
        
        self._running = False
        
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        
        logger.info("⏹️ Processador em lote parado")
    
    def _run_loop(self) -> None:
        """Loop principal de processamento."""
        check_interval = 30  # Verificar a cada 30 segundos
        retry_check_counter = 0

        while self._running:
            try:
                # Atualizar próxima execução
                if self._stats.last_run:
                    next_run = datetime.fromtimestamp(
                        self._stats.last_run.timestamp() + self.interval_minutes * 60
                    )
                    self._stats.next_run = next_run

                # Verificar se deve processar arquivos pendentes
                if self._should_process():
                    self.process_pending()

                # Atualizar contagem de pendentes
                self._stats.pending_files = len(self.get_pending_files())

                # Verificar jobs pendentes de retry a cada 5 ciclos (2.5 min)
                retry_check_counter += 1
                if retry_check_counter >= 5:
                    retry_check_counter = 0
                    self._process_pending_retries()

            except Exception as e:
                logger.error(f"Erro no loop de processamento: {e}")

            # Aguardar
            time.sleep(check_interval)

    def _process_pending_retries(self) -> int:
        """
        Processa jobs pendentes de retry do JobManager.

        Returns:
            Número de jobs reprocessados
        """
        if not self._job_manager:
            return 0

        try:
            pending_jobs = self._job_manager.get_pending_jobs()
            retried = 0

            for job in pending_jobs:
                # Só processar jobs com estado "retrying" e arquivo existente
                if job.state == "retrying":
                    audio_path = Path(job.audio_path)

                    if audio_path.exists():
                        logger.info(f"🔄 Retry automático: {audio_path.name}")
                        try:
                            if self.process_file(audio_path):
                                retried += 1
                        except Exception as e:
                            logger.error(f"Retry falhou para {audio_path.name}: {e}")
                    else:
                        # Arquivo não existe mais, marcar como falho permanentemente
                        self._job_manager.mark_job_failed(
                            job.id,
                            f"Arquivo não encontrado: {job.audio_path}",
                            can_retry=False,
                        )

            if retried > 0:
                logger.info(f"✅ {retried} jobs reprocessados com sucesso")

            return retried

        except Exception as e:
            logger.error(f"Erro ao processar retries: {e}")
            return 0

    def recover_pending_jobs(self) -> int:
        """
        Recupera jobs pendentes do JobManager após restart.

        Verifica jobs que estavam "submitted" ou "processing" e
        re-submete se o arquivo ainda existe.

        Returns:
            Número de jobs recuperados
        """
        if not self._job_manager:
            return 0

        try:
            in_progress = self._job_manager.get_in_progress_jobs()
            recovered = 0

            for job in in_progress:
                audio_path = Path(job.audio_path)

                if audio_path.exists():
                    logger.info(f"🔄 Recuperando job: {audio_path.name}")

                    # Marcar como retrying para reprocessar
                    self._job_manager.mark_job_failed(
                        job.id,
                        "Recuperado após restart",
                        can_retry=True,
                    )
                    recovered += 1
                else:
                    # Arquivo não existe, marcar como falho
                    self._job_manager.mark_job_failed(
                        job.id,
                        f"Arquivo não encontrado após restart: {job.audio_path}",
                        can_retry=False,
                    )

            if recovered > 0:
                logger.info(f"📋 {recovered} jobs marcados para retry após restart")

            return recovered

        except Exception as e:
            logger.error(f"Erro ao recuperar jobs: {e}")
            return 0

    def get_job_manager_stats(self) -> dict:
        """
        Retorna estatísticas do JobManager.

        Returns:
            Dict com estatísticas ou mensagem de erro
        """
        if not self._job_manager:
            return {"error": "JobManager não disponível"}

        return self._job_manager.stats

    def get_server_status(self) -> List[dict]:
        """
        Retorna status dos servidores WhisperAPI.

        Returns:
            Lista com status de cada servidor
        """
        if not self._job_manager:
            return []

        return self._job_manager.server_status
    
    @property
    def status(self) -> dict:
        """Retorna status atual do processador com informações do JobManager."""
        self._stats.pending_files = len(self.get_pending_files())

        status_dict = {
            "running": self._running,
            "is_processing": self._stats.is_running,
            "pending_files": self._stats.pending_files,
            "processed_files": self._stats.processed_files,
            "failed_files": self._stats.failed_files,
            "last_run": self._stats.last_run.isoformat() if self._stats.last_run else None,
            "next_run": self._stats.next_run.isoformat() if self._stats.next_run else None,
            "current_file": self._stats.current_file,
            "interval_minutes": self.interval_minutes,
            "cpu_threshold": self.cpu_threshold,
            "audio_dir": str(self.audio_dir),
        }

        # Adicionar estatísticas do JobManager se disponível
        if self._job_manager:
            job_stats = self._job_manager.stats
            status_dict["job_manager"] = {
                "enabled": True,
                "total_jobs": job_stats.get("total_jobs", 0),
                "completed_jobs": job_stats.get("completed_jobs", 0),
                "failed_jobs": job_stats.get("failed_jobs", 0),
                "pending_jobs": job_stats.get("pending_jobs", 0),
                "in_progress_jobs": job_stats.get("in_progress_jobs", 0),
                "healthy_servers": job_stats.get("healthy_servers", 0),
                "total_servers": job_stats.get("total_servers", 0),
            }
        else:
            status_dict["job_manager"] = {"enabled": False}

        return status_dict


# Instância global
_global_processor: Optional[BatchProcessor] = None


def get_batch_processor(
    audio_dir: Optional[str] = None,
    config_path: Optional[str] = None,
) -> BatchProcessor:
    """
    Obtém instância global do processador.
    
    Args:
        audio_dir: Diretório de áudio (usa padrão se None)
        config_path: Caminho da configuração
        
    Returns:
        Instância do BatchProcessor
    """
    global _global_processor
    
    if _global_processor is None:
        _global_processor = BatchProcessor(
            audio_dir=audio_dir or "~/audio-recordings",
            config_path=config_path,
        )
    
    return _global_processor


def start_batch_processing(config_path: Optional[str] = None) -> BatchProcessor:
    """Inicia processamento em lote."""
    processor = get_batch_processor(config_path=config_path)
    processor.start()
    return processor


def stop_batch_processing() -> None:
    """Para processamento em lote."""
    global _global_processor
    
    if _global_processor:
        _global_processor.stop()
        _global_processor = None
