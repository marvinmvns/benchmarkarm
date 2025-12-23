"""
Processador em Lote de Transcrições.

Processa arquivos .wav pendentes, transcreve com Whisper,
salva como .txt e remove os arquivos de áudio originais.
"""

import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Callable

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
    """
    
    def __init__(
        self,
        audio_dir: str = "~/audio-recordings",
        interval_minutes: int = 5,
        max_files_per_run: int = 10,
        cpu_threshold: float = 30.0,
        config_path: Optional[str] = None,
    ):
        """
        Inicializa o processador.
        
        Args:
            audio_dir: Diretório com arquivos de áudio
            interval_minutes: Intervalo entre execuções (minutos)
            max_files_per_run: Máximo de arquivos por execução
            cpu_threshold: Processar se CPU abaixo deste % (além do intervalo)
            config_path: Caminho do arquivo de configuração
        """
        self.audio_dir = Path(os.path.expanduser(audio_dir))
        self.interval_minutes = interval_minutes
        self.max_files_per_run = max_files_per_run
        self.cpu_threshold = cpu_threshold
        self.config_path = config_path
        
        # Estado
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stats = ProcessingStats()
        self._failed_files: List[str] = []
        
        # Componentes (lazy loaded)
        self._transcriber = None
        
        # Callbacks
        self._on_file_processed: Optional[Callable] = None
        self._on_error: Optional[Callable] = None
        
        logger.info(f"BatchProcessor inicializado: dir={self.audio_dir}")
    
    def _get_transcriber(self):
        """Obtém transcritor Whisper (lazy loading)."""
        if self._transcriber is None:
            try:
                from ..transcription.whisper import WhisperTranscriber
                from ..utils.config import load_config
                
                config = load_config(self.config_path)
                self._transcriber = WhisperTranscriber(
                    model=config.whisper.model,
                    language=config.whisper.language,
                    use_cpp=config.whisper.use_cpp,
                    threads=config.whisper.threads,
                    beam_size=config.whisper.beam_size,
                    quantization=config.whisper.quantization,
                    stream_mode=getattr(config.whisper, 'stream_mode', False),
                )
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
    
    def process_file(self, wav_path: Path) -> bool:
        """
        Processa um arquivo .wav individual.
        
        Args:
            wav_path: Caminho do arquivo .wav
            
        Returns:
            True se processado com sucesso
        """
        logger.info(f"📝 Processando: {wav_path.name}")
        self._stats.current_file = wav_path.name
        
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
            logger.error(f"❌ Erro ao processar {wav_path.name}: {e}")
            self._stats.failed_files += 1
            self._failed_files.append(str(wav_path))
            
            if self._on_error:
                self._on_error(wav_path.name, e)
            
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
        
        while self._running:
            try:
                # Atualizar próxima execução
                if self._stats.last_run:
                    next_run = datetime.fromtimestamp(
                        self._stats.last_run.timestamp() + self.interval_minutes * 60
                    )
                    self._stats.next_run = next_run
                
                # Verificar se deve processar
                if self._should_process():
                    self.process_pending()
                
                # Atualizar contagem de pendentes
                self._stats.pending_files = len(self.get_pending_files())
                
            except Exception as e:
                logger.error(f"Erro no loop de processamento: {e}")
            
            # Aguardar
            time.sleep(check_interval)
    
    @property
    def status(self) -> dict:
        """Retorna status atual do processador."""
        self._stats.pending_files = len(self.get_pending_files())
        
        return {
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
