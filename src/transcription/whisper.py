"""
Transcrição de áudio usando Whisper.
Suporta whisper.cpp (otimizado para ARM) e Whisper Python.
"""

import logging
import os
import subprocess
import tempfile
import time
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Literal, List
import json

import numpy as np

from ..audio.capture import AudioBuffer
from ..utils.cpu_limiter import get_cpu_limiter

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    """Resultado da transcrição."""
    text: str
    language: str
    duration: float
    processing_time: float
    model: str
    segments: list[dict] = None
    server_url: Optional[str] = None  # Servidor que processou a transcrição

    @property
    def words_per_second(self) -> float:
        """Palavras por segundo de processamento."""
        words = len(self.text.split())
        return words / self.processing_time if self.processing_time > 0 else 0

    @property
    def server_name(self) -> str:
        """Nome amigável do servidor (último octeto do IP)."""
        if not self.server_url:
            return "local"
        try:
            # Extrair IP do URL (ex: http://192.168.31.121:3001 -> 121)
            import re
            match = re.search(r'(\d+)\.(\d+)\.(\d+)\.(\d+)', self.server_url)
            if match:
                return f"whisper-{match.group(4)}"
            return self.server_url
        except Exception:
            return self.server_url or "unknown"

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "text": self.text,
            "language": self.language,
            "duration": self.duration,
            "processing_time": self.processing_time,
            "model": self.model,
            "segments": self.segments,
            "server_url": self.server_url,
            "server_name": self.server_name,
        }


class WhisperTranscriber:
    """
    Transcritor de áudio usando Whisper.

    Características:
    - Suporte a whisper.cpp (rápido, otimizado para ARM)
    - Fallback para Whisper Python
    - Cache de modelos
    - Suporte a múltiplos idiomas
    """

    # Mapeamento de modelos
    MODEL_SIZES = {
        "tiny": "ggml-tiny",
        "base": "ggml-base",
        "small": "ggml-small",
        "medium": "ggml-medium",
        "large": "ggml-large-v3",
    }

    def __init__(
        self,
        model: str = "tiny",
        language: str = "pt",
        use_cpp: bool = True,
        threads: int = 4,
        beam_size: int = 1,
        quantization: str = "q5_0",
        whisper_cpp_path: Optional[str] = None,
        models_path: Optional[str] = None,
        stream_mode: bool = False,
    ):
        """
        Inicializa o transcritor.

        Args:
            model: Modelo Whisper (tiny, base, small, medium, large)
            language: Código do idioma (pt, en, es, etc.)
            use_cpp: Usar whisper.cpp (recomendado para ARM)
            threads: Número de threads
            beam_size: Tamanho do beam search (1 = greedy, mais rápido)
            quantization: Quantização do modelo (f16, q8_0, q5_0, q4_0)
            whisper_cpp_path: Caminho para whisper.cpp
            models_path: Caminho para modelos
            stream_mode: Usar modo streaming (transcrição em tempo real)
        """
        self.model = model
        self.language = language
        self.use_cpp = use_cpp
        self.threads = threads
        self.beam_size = beam_size
        self.quantization = quantization
        self.stream_mode = stream_mode

        # Encontrar caminhos
        self._project_root = self._find_project_root()
        self.whisper_cpp_path = whisper_cpp_path or self._find_whisper_cpp()
        self.models_path = models_path or self._get_models_path()

        # Verificar disponibilidade
        self._cpp_available = self._check_cpp_available()
        self._python_model = None

        if use_cpp and not self._cpp_available:
            logger.warning(
                "whisper.cpp não disponível. "
                "Usando Whisper Python (mais lento)."
            )
            self.use_cpp = False

        logger.info(
            f"Transcritor inicializado: model={model}, "
            f"language={language}, use_cpp={self.use_cpp}, stream={stream_mode}"
        )

    def _find_project_root(self) -> Path:
        """Encontra diretório raiz do projeto."""
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "config").is_dir() or (parent / "external").is_dir():
                return parent
        return current.parent.parent.parent

    def _find_whisper_cpp(self) -> str:
        """Encontra executável do whisper.cpp."""
        possible_paths = [
            # Instalação com cmake (padrão atual)
            self._project_root / "external" / "whisper.cpp" / "build" / "bin" / "whisper-cli",
            self._project_root / "external" / "whisper.cpp" / "build" / "bin" / "main",
            # Instalação antiga com make
            self._project_root / "external" / "whisper.cpp" / "main",
            self._project_root / "external" / "whisper.cpp" / "whisper-cli",
            # Sistema
            Path.home() / "whisper.cpp" / "build" / "bin" / "whisper-cli",
            Path.home() / "whisper.cpp" / "main",
            Path("/usr/local/bin/whisper-cpp"),
            Path("/usr/local/bin/whisper-cli"),
        ]

        for path in possible_paths:
            if path.exists():
                logger.info(f"whisper.cpp encontrado: {path}")
                return str(path)

        # Fallback - retorna o caminho esperado mais comum
        return str(self._project_root / "external" / "whisper.cpp" / "build" / "bin" / "whisper-cli")

    def _get_models_path(self) -> str:
        """Retorna caminho dos modelos."""
        models_dir = self._project_root / "external" / "whisper.cpp" / "models"
        if not models_dir.exists():
            models_dir = self._project_root / "models"
        return str(models_dir)

    def _check_cpp_available(self) -> bool:
        """Verifica se whisper.cpp está disponível."""
        exe_path = Path(self.whisper_cpp_path)
        if not exe_path.exists():
            return False

        # Verificar se modelo existe
        model_file = self._get_model_path()
        return model_file.exists()

    def _get_model_path(self) -> Path:
        """Retorna caminho do modelo."""
        model_name = self.MODEL_SIZES.get(self.model, f"ggml-{self.model}")

        # Tentar com quantização primeiro
        if self.quantization:
            quant_model = f"{model_name}.{self.quantization}.bin"
            path = Path(self.models_path) / quant_model
            if path.exists():
                return path

        # Modelo sem quantização
        return Path(self.models_path) / f"{model_name}.bin"

    def transcribe(
        self,
        audio: AudioBuffer | np.ndarray | str,
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        """
        Transcreve áudio para texto.

        Args:
            audio: Buffer de áudio, array numpy ou caminho de arquivo
            language: Idioma (usa padrão se None)

        Returns:
            Resultado da transcrição
        """
        language = language or self.language
        start_time = time.time()

        # OTIMIZADO: Usar named pipe em vez de arquivo temporário (50-100ms mais rápido)
        # Se for arquivo existente, usar diretamente
        if isinstance(audio, str):
            if Path(audio).exists():
                # Obter duração do arquivo
                import wave
                with wave.open(audio, 'rb') as wav:
                    duration = wav.getnframes() / wav.getframerate()

                # Transcrever
                if self.use_cpp and self._cpp_available:
                    try:
                        result = self._transcribe_cpp(audio, language)
                    except RuntimeError as e:
                        error_msg = str(e)
                        if "código -9" in error_msg or "código -11" in error_msg:
                            logger.warning(
                                f"⚠️ whisper.cpp falhou com OOM. "
                                f"Tentando fallback para Whisper Python..."
                            )
                            result = self._transcribe_python(audio, language)
                        else:
                            raise
                else:
                    result = self._transcribe_python(audio, language)

                processing_time = time.time() - start_time

                return TranscriptionResult(
                    text=result["text"],
                    language=result.get("language", language),
                    duration=duration,
                    processing_time=processing_time,
                    model=self.model,
                    segments=result.get("segments"),
                )
            else:
                raise FileNotFoundError(f"Arquivo não encontrado: {audio}")

        # Para AudioBuffer ou np.ndarray, converter para formato correto
        if isinstance(audio, AudioBuffer):
            audio_array = audio.data
            duration = audio.duration
        elif isinstance(audio, np.ndarray):
            audio_array = audio
            duration = len(audio_array) / 16000  # Assume 16kHz
        else:
            raise TypeError(f"Tipo de áudio não suportado: {type(audio)}")

        # OTIMIZADO: Usar named pipe quando possível (evita disco)
        use_pipe = self.use_cpp and self._cpp_available and os.name != 'nt'  # Pipes não funcionam no Windows

        if use_pipe:
            result_dict = self._transcribe_with_pipe(audio_array, language)
        else:
            # Fallback: usar arquivo temporário
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name

            try:
                self._save_audio(audio_array, tmp_path)

                if self.use_cpp and self._cpp_available:
                    try:
                        result_dict = self._transcribe_cpp(tmp_path, language)
                    except RuntimeError as e:
                        error_msg = str(e)
                        if "código -9" in error_msg or "código -11" in error_msg:
                            logger.warning(
                                f"⚠️ whisper.cpp falhou com OOM. "
                                f"Tentando fallback para Whisper Python..."
                            )
                            result_dict = self._transcribe_python(tmp_path, language)
                        else:
                            raise
                else:
                    result_dict = self._transcribe_python(tmp_path, language)
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        processing_time = time.time() - start_time

        return TranscriptionResult(
            text=result_dict["text"],
            language=result_dict.get("language", language),
            duration=duration,
            processing_time=processing_time,
            model=self.model,
            segments=result_dict.get("segments"),
        )

    def _save_audio(self, audio: np.ndarray, path: str) -> None:
        """Salva array numpy como WAV."""
        import wave

        if audio.dtype != np.int16:
            if audio.dtype in (np.float32, np.float64):
                audio = (audio * 32767).astype(np.int16)
            else:
                audio = audio.astype(np.int16)

        with wave.open(path, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(audio.tobytes())

    def _transcribe_with_pipe(self, audio: np.ndarray, language: str) -> dict:
        """
        Transcreve usando whisper.cpp com named pipe (OTIMIZADO).
        Evita I/O de disco, 50-100ms mais rápido.
        """
        import threading

        # Criar named pipe (FIFO)
        pipe_path = f"/tmp/whisper_pipe_{os.getpid()}_{time.time_ns()}.wav"

        try:
            os.mkfifo(pipe_path)
        except FileExistsError:
            # Limpar pipe antigo se existir
            os.unlink(pipe_path)
            os.mkfifo(pipe_path)

        try:
            # Preparar comando whisper.cpp
            model_path = self._get_model_path()
            cmd = [
                self.whisper_cpp_path,
                "-m", str(model_path),
                "-f", pipe_path,  # Lê do pipe
                "-l", language,
                "-t", str(self.threads),
                "-bs", str(self.beam_size),
                "--no-timestamps",
                "-otxt",
                "--no-prints",
            ]

            # Iniciar whisper.cpp em thread separada (irá bloquear lendo do pipe)
            logger.debug(f"Executando whisper.cpp com named pipe: {pipe_path}")

            # Usar nice/ionice para reduzir prioridade
            nice_cmd = ["nice", "-n", "15", "ionice", "-c", "3"] + cmd

            # Verificar CPU antes de iniciar
            cpu_limiter = get_cpu_limiter()
            cpu_limiter.wait_if_overloaded(timeout=120)

            # Iniciar processo (irá bloquear esperando dados no pipe)
            process = subprocess.Popen(
                nice_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Thread para escrever áudio no pipe
            def write_audio():
                try:
                    # Abrir pipe para escrita (bloqueia até whisper.cpp abrir para leitura)
                    with open(pipe_path, 'wb') as pipe:
                        # Escrever WAV completo no pipe
                        import wave
                        import io

                        # Criar WAV em memória
                        wav_buffer = io.BytesIO()
                        with wave.open(wav_buffer, 'wb') as wav:
                            wav.setnchannels(1)
                            wav.setsampwidth(2)
                            wav.setframerate(16000)

                            # Converter áudio para int16 se necessário
                            if audio.dtype != np.int16:
                                if audio.dtype in (np.float32, np.float64):
                                    audio_int16 = (audio * 32767).astype(np.int16)
                                else:
                                    audio_int16 = audio.astype(np.int16)
                            else:
                                audio_int16 = audio

                            wav.writeframes(audio_int16.tobytes())

                        # Escrever no pipe
                        pipe.write(wav_buffer.getvalue())
                except Exception as e:
                    logger.error(f"Erro ao escrever no pipe: {e}")

            # Iniciar thread de escrita
            writer_thread = threading.Thread(target=write_audio, daemon=True)
            writer_thread.start()

            # Aguardar whisper.cpp terminar
            try:
                stdout, stderr = process.communicate(timeout=600)  # 10 minutos
            except subprocess.TimeoutExpired:
                process.kill()
                raise RuntimeError("Timeout na transcrição com named pipe")

            # Aguardar thread de escrita
            writer_thread.join(timeout=5)

            # Verificar erro
            if process.returncode != 0:
                error_details = (
                    f"whisper.cpp falhou (código {process.returncode})\n"
                    f"  STDERR: {stderr or '(vazio)'}\n"
                    f"  STDOUT: {stdout[:500] if stdout else '(vazio)'}"
                )
                logger.error(f"Erro whisper.cpp com named pipe:\n{error_details}")
                raise RuntimeError(f"whisper.cpp falhou:\n{error_details}")

            # Extrair texto do output
            text = stdout.strip()

            # Remover linhas de debug se houver
            lines = text.split('\n')
            text_lines = [
                line for line in lines
                if not line.startswith('[') and line.strip()
            ]
            text = ' '.join(text_lines).strip()

            logger.info(f"✅ Transcrição concluída (pipe): {len(text)} caracteres")

            return {
                "text": text,
                "language": language,
            }

        finally:
            # Limpar pipe
            try:
                if os.path.exists(pipe_path):
                    os.unlink(pipe_path)
            except OSError as e:
                logger.warning(f"Erro ao remover pipe {pipe_path}: {e}")

    def _transcribe_cpp(self, audio_path: str, language: str) -> dict:
        """Transcreve usando whisper.cpp."""
        model_path = self._get_model_path()

        cmd = [
            self.whisper_cpp_path,
            "-m", str(model_path),
            "-f", audio_path,
            "-l", language,
            "-t", str(self.threads),
            "-bs", str(self.beam_size),
            "--no-timestamps",
            "-otxt",
        ]

        # Opções adicionais para performance
        cmd.extend([
            "--no-prints",  # Menos output
        ])

        logger.debug(f"Executando whisper.cpp: {' '.join(cmd)}")

        try:
            # Verificar se executável existe
            exe_path = Path(self.whisper_cpp_path)
            if not exe_path.exists():
                error_msg = f"Executável whisper.cpp não encontrado: {self.whisper_cpp_path}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            # Verificar se modelo existe
            if not model_path.exists():
                error_msg = f"Modelo Whisper não encontrado: {model_path}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            # Verificar se arquivo de áudio existe
            if not Path(audio_path).exists():
                error_msg = f"Arquivo de áudio não encontrado: {audio_path}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            logger.info(f"🎙️ Transcrevendo com whisper.cpp: modelo={self.model}, arquivo={Path(audio_path).name}")

            # Esperar se CPU estiver sobrecarregada (evita congelamento)
            cpu_limiter = get_cpu_limiter()
            cpu_limiter.wait_if_overloaded(timeout=120)

            # Usar nice/ionice para reduzir prioridade
            nice_cmd = ["nice", "-n", "15", "ionice", "-c", "3"] + cmd

            result = subprocess.run(
                nice_cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minutos - permite usar swap no Pi Zero
            )

            if result.returncode != 0:
                error_details = (
                    f"whisper.cpp falhou (código {result.returncode})\n"
                    f"  Executável: {self.whisper_cpp_path}\n"
                    f"  Modelo: {model_path}\n"
                    f"  Arquivo: {audio_path}\n"
                    f"  Comando: {' '.join(cmd)}\n"
                    f"  STDERR: {result.stderr or '(vazio)'}\n"
                    f"  STDOUT: {result.stdout[:500] if result.stdout else '(vazio)'}"
                )
                logger.error(f"Erro whisper.cpp:\n{error_details}")
                raise RuntimeError(f"whisper.cpp falhou:\n{error_details}")

            # Extrair texto do output
            text = result.stdout.strip()

            # Remover linhas de debug se houver
            lines = text.split('\n')
            text_lines = [
                line for line in lines
                if not line.startswith('[') and line.strip()
            ]
            text = ' '.join(text_lines).strip()

            logger.info(f"✅ Transcrição concluída: {len(text)} caracteres")

            return {
                "text": text,
                "language": language,
            }

        except subprocess.TimeoutExpired:
            logger.error(f"Timeout na transcrição (>120s): {audio_path}")
            raise RuntimeError("Timeout na transcrição")

    def _transcribe_python(self, audio_path: str, language: str) -> dict:
        """Transcreve usando Whisper Python."""
        # Carregar modelo se necessário
        if self._python_model is None:
            self._load_python_model()

        # Transcrever
        result = self._python_model.transcribe(
            audio_path,
            language=language if language else None,
            beam_size=self.beam_size,
            fp16=False,  # CPU não suporta fp16 bem
            task="transcribe",
        )

        return {
            "text": result["text"].strip(),
            "language": result.get("language", language),
            "segments": result.get("segments"),
        }

    def _load_python_model(self) -> None:
        """Carrega modelo Whisper Python."""
        try:
            import whisper
            logger.info(f"Carregando modelo Whisper {self.model}...")
            self._python_model = whisper.load_model(self.model)
        except ImportError:
            raise ImportError(
                "Whisper não instalado. Execute: pip install openai-whisper"
            )


class FasterWhisperTranscriber:
    """
    Transcritor usando Faster-Whisper (CTranslate2).
    Mais rápido que Whisper original, bom para Pi 4+.
    """

    def __init__(
        self,
        model: str = "tiny",
        language: str = "pt",
        device: str = "cpu",
        compute_type: str = "int8",
        threads: int = 4,
    ):
        """
        Inicializa Faster-Whisper.

        Args:
            model: Modelo (tiny, base, small, medium, large-v3)
            language: Idioma
            device: Dispositivo (cpu, cuda)
            compute_type: Tipo de computação (int8, float16, float32)
            threads: Número de threads
        """
        self.model_name = model
        self.language = language
        self.device = device
        self.compute_type = compute_type
        self.threads = threads
        self._model = None

    def _load_model(self):
        """Carrega modelo sob demanda."""
        if self._model is not None:
            return

        try:
            from faster_whisper import WhisperModel

            logger.info(f"Carregando Faster-Whisper {self.model_name}...")
            self._model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
                cpu_threads=self.threads,
            )
        except ImportError:
            raise ImportError(
                "faster-whisper não instalado. Execute: pip install faster-whisper"
            )

    def transcribe(
        self,
        audio: AudioBuffer | np.ndarray | str,
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        """Transcreve áudio."""
        self._load_model()

        language = language or self.language
        start_time = time.time()

        # Preparar áudio
        if isinstance(audio, AudioBuffer):
            audio_data = audio.data.astype(np.float32) / 32768.0
            duration = audio.duration
        elif isinstance(audio, np.ndarray):
            if audio.dtype == np.int16:
                audio_data = audio.astype(np.float32) / 32768.0
            else:
                audio_data = audio
            duration = len(audio_data) / 16000
        else:
            audio_data = audio
            duration = 0  # Será calculado

        # Transcrever
        segments, info = self._model.transcribe(
            audio_data,
            language=language,
            beam_size=1,
            vad_filter=True,
        )

        # Coletar resultados
        text_parts = []
        segment_list = []

        for segment in segments:
            text_parts.append(segment.text)
            segment_list.append({
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
            })

        processing_time = time.time() - start_time

        return TranscriptionResult(
            text=" ".join(text_parts).strip(),
            language=info.language if info else language,
            duration=duration or info.duration if info else 0,
            processing_time=processing_time,
            model=f"faster-whisper-{self.model_name}",
            segments=segment_list,
        )


class WhisperAPIClient:
    """
    Cliente completo para WhisperAPI (servidor externo de transcrição).

    Endpoints suportados:
    - POST /transcribe: enviar áudio para transcrição
    - GET /status/:jobId: verificar status do job
    - GET /health: verificar saúde do servidor
    - GET /formats: formatos de áudio suportados
    - GET /queue-estimate: estatísticas da fila
    - GET /estimate: estimativa de tempo
    - GET /completed-jobs: jobs concluídos
    - GET /all-status: status de todos os jobs
    - GET /system-report: relatório do sistema
    - GET /model-info: informações do modelo

    Integração com JobManager:
    - Tracking persistente de jobs
    - Health-aware Round Robin
    - Backoff adaptativo
    - Recovery automático de jobs pendentes
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:3001",
        base_urls: Optional[List[str]] = None,
        language: str = "pt",
        timeout: int = 300,
        word_timestamps: bool = False,
        translate: bool = False,
        cleanup: bool = True,
        use_job_manager: bool = True,
    ):
        """
        Inicializa o cliente WhisperAPI com suporte a Round Robin inteligente.

        Args:
            base_url: URL base primária (fallback)
            base_urls: Lista de URLs para balanceamento de carga
            language: Idioma padrão
            timeout: Timeout máximo
            word_timestamps: Incluir timestamps por palavra
            translate: Traduzir para inglês
            cleanup: Limpar arquivos temporários no servidor
            use_job_manager: Usar JobManager para tracking inteligente
        """
        # Configurar URLs
        self.urls = base_urls or [base_url]
        self.urls = [u.rstrip("/") for u in self.urls if u and u.strip()]
        if not self.urls:
            self.urls = ["http://127.0.0.1:3001"]

        self.base_url = self.urls[0]  # Compatibilidade

        self.language = language
        self.timeout = timeout
        self.word_timestamps = word_timestamps
        self.translate = translate
        self.cleanup = cleanup
        self.use_job_manager = use_job_manager

        # Gerenciamento de clientes (Round Robin)
        self._clients = {}  # Cache: url -> httpx.Client
        self._current_index = 0
        self._lock = threading.Lock()

        self._http_client = None  # Legado

        # JobManager para tracking inteligente
        self._job_manager = None
        if use_job_manager:
            try:
                from .job_manager import get_job_manager
                self._job_manager = get_job_manager()
                self._job_manager.register_servers(self.urls)
                logger.info(f"🧠 JobManager integrado com {len(self.urls)} servidores")
            except Exception as e:
                logger.warning(f"JobManager não disponível: {e}")
                self._job_manager = None

        logger.info(f"🌐 WhisperAPI inicializado com {len(self.urls)} servidores: {self.urls}")
    
    def _get_client_for_url(self, url: str):
        """Retorna ou cria client para uma URL específica."""
        with self._lock:
            if url not in self._clients:
                import httpx
                self._clients[url] = httpx.Client(
                    base_url=url,
                    timeout=60.0,
                )
            return self._clients[url]
            
    def _get_next_client(self):
        """
        Retorna (client, url) usando Round Robin inteligente.

        Se JobManager está disponível, usa seleção baseada em:
        - Saúde do servidor
        - Tamanho da fila
        - Workers disponíveis
        """
        # Se JobManager disponível, usar seleção inteligente
        if self._job_manager:
            url = self._job_manager.get_next_server()
            if url:
                client = self._get_client_for_url(url)
                return client, url

            # Fallback: tentar qualquer servidor se nenhum "saudável"
            logger.warning("Nenhum servidor saudável, tentando fallback...")

        # Round Robin simples (fallback)
        with self._lock:
            url = self.urls[self._current_index]
            self._current_index = (self._current_index + 1) % len(self.urls)

        client = self._get_client_for_url(url)
        return client, url

    def _get_client(self):
        """Retorna cliente padrão (compatibilidade)."""
        client, _ = self._get_next_client()
        return client
    
    # ==========================================================================
    # Health & Info Endpoints
    # ==========================================================================
    
    def health_check(self) -> dict:
        """
        Verifica saúde do servidor.
        
        Returns:
            Dict com status do servidor e endpoints disponíveis
        """
        try:
            client = self._get_client()
            response = client.get("/health")
            response.raise_for_status()
            data = response.json()
            
            # Validar se é realmente um WhisperAPI
            # WhisperAPI deve retornar availableEndpoints ou campos específicos
            if "availableEndpoints" in data or "whisper" in str(data).lower():
                logger.info(f"✅ WhisperAPI online: {data.get('status', 'ok')}")
                return data
            elif "whatsapp" in str(data).lower():
                # Usuário apontou para um servidor de WhatsApp, não WhisperAPI
                return {
                    "status": "invalid",
                    "error": "Este servidor é um bot de WhatsApp, não um WhisperAPI. Verifique a URL."
                }
            else:
                # Servidor respondeu mas não parece ser WhisperAPI
                logger.warning(f"Servidor respondeu mas não parece ser WhisperAPI: {data}")
                return {
                    "status": "unknown",
                    "message": "Servidor respondeu, mas pode não ser WhisperAPI",
                    "raw_response": data
                }
                
        except Exception as e:
            logger.error(f"❌ WhisperAPI não responde: {e}")
            return {"status": "offline", "error": str(e)}
    
    def is_available(self) -> bool:
        """Verifica se WhisperAPI está disponível."""
        try:
            result = self.health_check()
            return result.get("status") != "offline"
        except Exception:
            return False
    
    def get_supported_formats(self) -> list:
        """
        Obtém formatos de áudio suportados pelo servidor.
        
        Returns:
            Lista de extensões suportadas (ex: ['.wav', '.mp3', '.m4a'])
        """
        try:
            client = self._get_client()
            response = client.get("/formats")
            response.raise_for_status()
            data = response.json()
            formats = data.get("supportedFormats", [])
            logger.info(f"📋 Formatos suportados: {', '.join(formats)}")
            return formats
        except Exception as e:
            logger.error(f"❌ Erro ao obter formatos: {e}")
            return [".wav", ".mp3", ".m4a", ".ogg", ".flac"]  # Fallback padrão
    
    def get_queue_stats(self) -> dict:
        """
        Obtém estatísticas da fila de processamento.
        
        Returns:
            Dict com queueLength, activeJobs, availableWorkers, 
            totalWorkers, averageProcessingTime, estimatedWaitTime
        """
        try:
            client = self._get_client()
            response = client.get("/queue-estimate")
            response.raise_for_status()
            stats = response.json()
            logger.info(
                f"📊 Fila: {stats.get('queueLength', 0)} pendentes, "
                f"{stats.get('activeJobs', 0)} ativos, "
                f"espera: {stats.get('estimatedWaitTime', 0)}s"
            )
            return stats
        except Exception as e:
            logger.error(f"❌ Erro ao obter estatísticas: {e}")
            return {}
    
    def get_model_info(self) -> dict:
        """
        Obtém informações do modelo Whisper em uso no servidor.
        
        Returns:
            Dict com nome do modelo, tamanho, etc.
        """
        try:
            client = self._get_client()
            response = client.get("/model-info")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(f"Erro ao obter info do modelo: {e}")
            return {}
    
    def get_system_report(self) -> dict:
        """
        Obtém relatório completo do sistema (CPU, memória, etc).
        
        Returns:
            Dict com métricas do sistema servidor
        """
        try:
            client = self._get_client()
            response = client.get("/system-report")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(f"Erro ao obter relatório do sistema: {e}")
            return {}
    
    # ==========================================================================
    # Job Management
    # ==========================================================================
    
    def get_job_status(self, job_id: str, server_url: Optional[str] = None) -> dict:
        """
        Verifica status de um job específico.

        Args:
            job_id: ID do job retornado por transcribe()
            server_url: URL do servidor (necessário se usar Round Robin)

        Returns:
            Dict com status ('pending', 'processing', 'completed', 'failed'),
            result (se completed), error (se failed)

        Raises:
            ValueError: Job não encontrado (pode ser race condition)
            RuntimeError: Job falhou com erro (não tentar novamente)
        """
        try:
            if server_url:
                client = self._get_client_for_url(server_url)
            else:
                client = self._get_client()

            response = client.get(f"/status/{job_id}", timeout=10.0)

            # Verificar resposta mesmo em caso de 404
            if response.status_code == 404:
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", "")
                    error_code = error_data.get("code", "")

                    # Se há mensagem de erro real, o job falhou durante processamento
                    # Não é um "job não encontrado", é um "job falhou"
                    if error_msg and "transcription failed" in error_msg.lower():
                        logger.error(f"❌ Job {job_id[:8]} falhou durante processamento: {error_msg}")
                        return {
                            "status": "failed",
                            "error": error_msg,
                            "code": error_code,
                        }

                    # Se é JOB_NOT_FOUND sem erro real, pode ser race condition
                    if error_code == "JOB_NOT_FOUND" and not error_msg:
                        raise ValueError(f"Job não encontrado: {job_id}")

                    # Outro erro com mensagem
                    if error_msg:
                        return {
                            "status": "failed",
                            "error": error_msg,
                        }

                except json.JSONDecodeError:
                    pass

                # 404 sem corpo interpretável
                raise ValueError(f"Job não encontrado: {job_id}")

            response.raise_for_status()
            return response.json()
        except ValueError:
            raise
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Erro ao verificar status: {e}")
    
    def get_all_jobs_status(self) -> list:
        """
        Obtém status de todos os jobs.
        
        Returns:
            Lista de dicts com status de cada job
        """
        try:
            client = self._get_client()
            response = client.get("/all-status")
            response.raise_for_status()
            return response.json().get("jobs", [])
        except Exception as e:
            logger.warning(f"Erro ao obter status de todos os jobs: {e}")
            return []
    
    def get_completed_jobs(self) -> list:
        """
        Obtém lista de jobs concluídos.

        Returns:
            Lista de jobs completados
        """
        try:
            client = self._get_client()
            response = client.get("/completed-jobs")
            response.raise_for_status()
            return response.json().get("jobs", [])
        except Exception as e:
            logger.warning(f"Erro ao obter jobs concluídos: {e}")
            return []

    def _try_recover_from_completed_jobs(
        self, job_id: str, server_url: Optional[str] = None
    ) -> Optional[dict]:
        """
        Tenta recuperar resultado de um job que pode ter completado mas não está
        mais acessível via /status/:id.

        O servidor pode ter removido o job do endpoint /status/ após conclusão,
        mas mantém registro em /completed-jobs.

        Args:
            job_id: ID do job a recuperar
            server_url: URL do servidor

        Returns:
            Dict com resultado se encontrado, None caso contrário
        """
        try:
            if server_url:
                client = self._get_client_for_url(server_url)
            else:
                client = self._get_client()

            response = client.get("/completed-jobs", timeout=10.0)
            if response.status_code != 200:
                return None

            data = response.json()
            # Handle both formats: {"jobs": [...]} and {"completedJobs": [...]}
            jobs = data.get("jobs", []) or data.get("completedJobs", [])

            # Procurar job pelo ID (pode ser parcial ou em campos diferentes)
            for job in jobs:
                # Diferentes campos possíveis para o ID
                remote_id = (
                    job.get("jobId", "")
                    or job.get("id", "")
                    or job.get("job_id", "")
                )

                # Match exato ou parcial (primeiro 8 caracteres)
                if (job_id == remote_id
                    or job_id in remote_id
                    or remote_id in job_id
                    or job_id[:8] == remote_id[:8] if len(remote_id) >= 8 else False):

                    logger.info(f"🔍 Job {job_id[:8]} encontrado em /completed-jobs")

                    # O job pode ter resultado aninhado ou direto
                    result_data = job.get("result", job)

                    # Extrair texto (pode estar em diferentes lugares)
                    text = (
                        result_data.get("text", "")
                        or job.get("text", "")
                        or (result_data.get("result", {}).get("text", "") if isinstance(result_data.get("result"), dict) else "")
                    )

                    # Extrair metadata
                    metadata = result_data.get("metadata", {}) or job.get("metadata", {})

                    # Formatar como resultado do /status
                    return {
                        "status": job.get("status", "completed"),
                        "result": {
                            "text": text,
                            "metadata": metadata,
                            "segments": result_data.get("segments") or job.get("segments"),
                            "processingTime": (
                                result_data.get("processingTime", 0)
                                or job.get("processingTime", 0)
                            ),
                        },
                    }

            return None

        except Exception as e:
            logger.debug(f"Erro ao recuperar de /completed-jobs: {e}")
            return None

    # ==========================================================================
    # Transcription
    # ==========================================================================
    
    def upload_audio(
        self,
        audio_path: str,
        language: Optional[str] = None,
        translate: Optional[bool] = None,
        word_timestamps: Optional[bool] = None,
        cleanup: Optional[bool] = None,
    ) -> dict:
        """
        Envia arquivo de áudio para transcrição (não bloqueia).
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {audio_path}")
        
        # Usar padrões da instância se não especificado
        language = language or self.language
        translate = translate if translate is not None else self.translate
        word_timestamps = word_timestamps if word_timestamps is not None else self.word_timestamps
        cleanup = cleanup if cleanup is not None else self.cleanup
        
        try:
            # Round Robin: Escolher próximo servidor
            client, server_url = self._get_next_client()
            
            with open(audio_path, 'rb') as f:
                files = {'audio': (Path(audio_path).name, f, 'audio/wav')}
                data = {
                    'language': language,
                    'translate': str(translate).lower(),
                    'wordTimestamps': str(word_timestamps).lower(),
                    'cleanup': str(cleanup).lower(),
                }
                
                logger.info(f"📤 Enviando áudio para {server_url}: {Path(audio_path).name}")
                
                response = client.post(
                    "/transcribe",
                    files=files,
                    data=data,
                    timeout=30.0,
                )
                response.raise_for_status()
                result = response.json()
            
            job_id = result.get('jobId')
            estimated_wait = result.get('estimatedWaitTime', 0)
            
            logger.info(f"✅ Upload OK! Job ID: {job_id} em {server_url}")
            
            # Adicionar URL do servidor ao resultado para referência futura
            result['server_url'] = server_url
            
            return result
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Erro no upload: {error_msg}")
            raise RuntimeError(f"Upload falhou: {error_msg}")
    
    def wait_for_completion(
        self,
        job_id: str,
        poll_interval: float = 3.0,
        max_wait_time: Optional[float] = None,
        server_url: Optional[str] = None,
        local_job_id: Optional[str] = None,
    ) -> dict:
        """
        Aguarda conclusão de um job de transcrição com polling adaptativo.

        Args:
            job_id: ID do job no servidor remoto
            poll_interval: Intervalo inicial entre verificações (segundos)
            max_wait_time: Tempo máximo de espera (padrão: 30 minutos)
            server_url: URL do servidor (necessário para Round Robin)
            local_job_id: ID do job local no JobManager

        Returns:
            Dict com resultado completo da transcrição
        """
        max_wait = max_wait_time or 1800.0  # 30 minutos de timeout padrão
        start_time = time.time()
        last_status = ""
        not_found_retries = 0
        max_not_found_retries = 15  # Aumentado para dar mais tempo ao servidor

        # Calcular intervalo adaptativo baseado na carga do servidor
        if self._job_manager and server_url:
            poll_interval = self._job_manager.calculate_poll_interval(server_url)
            logger.debug(f"Polling adaptativo: {poll_interval:.1f}s para {server_url}")

        logger.info(
            f"⏳ Aguardando job {job_id[:8]}... em {server_url or 'default'} "
            f"(poll: {poll_interval:.1f}s, timeout: {max_wait}s)"
        )

        while (time.time() - start_time) < max_wait:
            try:
                status_data = self.get_job_status(job_id, server_url=server_url)
                status = status_data.get('status', '')
                not_found_retries = 0  # Reset contador se encontrou o job

                # Atualizar estado no JobManager
                if self._job_manager and local_job_id:
                    if status == 'processing':
                        self._job_manager.mark_job_processing(local_job_id)

                if status != last_status:
                    elapsed = time.time() - start_time
                    logger.info(f"📊 Job status: {status} ({elapsed:.1f}s)")
                    last_status = status

                    # Quando o job está processando, usar polling mais rápido
                    # para não perder a janela de conclusão
                    if status == 'processing':
                        poll_interval = 1.5  # Polling agressivo durante processamento

                if status == 'completed':
                    result = status_data.get('result', {})
                    text = result.get('text', '')[:100]
                    processing_time = time.time() - start_time

                    # Marcar sucesso no JobManager
                    if self._job_manager:
                        if server_url:
                            self._job_manager.mark_server_success(server_url)
                        if local_job_id:
                            metadata = result.get('metadata', {})
                            self._job_manager.mark_job_completed(
                                local_job_id,
                                text=result.get('text', ''),
                                language=metadata.get('language', self.language),
                                duration=metadata.get('duration', 0),
                                processing_time=processing_time,
                            )

                    logger.info(f"✅ Transcrição concluída! Texto: {text}...")
                    return status_data

                if status == 'failed':
                    error = status_data.get('error', 'Erro desconhecido')

                    # Marcar falha no JobManager
                    if self._job_manager and local_job_id:
                        self._job_manager.mark_job_failed(local_job_id, error)

                    raise RuntimeError(f"Transcrição falhou: {error}")

                # Esperar antes de próxima verificação
                time.sleep(poll_interval)

                # Aumentar intervalo progressivamente (até 10s)
                # Mas recalcular baseado na carga se JobManager disponível
                if self._job_manager and server_url:
                    poll_interval = self._job_manager.calculate_poll_interval(server_url)
                else:
                    poll_interval = min(poll_interval * 1.2, 10.0)

            except ValueError as e:
                # Job não encontrado - tentar recuperar de /completed-jobs
                not_found_retries += 1
                server_msg = f" em {server_url}" if server_url else ""

                # SEMPRE tentar recuperar de /completed-jobs (o job pode ter completado
                # e sido removido do /status muito rapidamente)
                try:
                    recovered_result = self._try_recover_from_completed_jobs(
                        job_id, server_url
                    )
                    if recovered_result:
                        # Verificar se foi realmente completado ou falhou
                        rec_status = recovered_result.get('status', 'completed')

                        if rec_status == 'failed':
                            error = recovered_result.get('error', 'Erro desconhecido')
                            if self._job_manager and local_job_id:
                                self._job_manager.mark_job_failed(local_job_id, error)
                            raise RuntimeError(f"Transcrição falhou: {error}")

                        # Marcar sucesso no JobManager
                        if self._job_manager:
                            if server_url:
                                self._job_manager.mark_server_success(server_url)
                            if local_job_id:
                                result_data = recovered_result.get('result', {})
                                metadata = result_data.get('metadata', {})
                                processing_time = time.time() - start_time
                                self._job_manager.mark_job_completed(
                                    local_job_id,
                                    text=result_data.get('text', ''),
                                    language=metadata.get('language', self.language),
                                    duration=metadata.get('duration', 0),
                                    processing_time=processing_time,
                                )

                        logger.info(f"✅ Job recuperado de /completed-jobs!")
                        return recovered_result
                except RuntimeError:
                    raise
                except Exception as recovery_error:
                    logger.debug(f"Recuperação falhou: {recovery_error}")

                if not_found_retries <= max_not_found_retries:
                    # Aumentar delay exponencialmente: 2s, 4s, 6s, 8s...
                    wait_time = min(2.0 * not_found_retries, 10.0)
                    logger.warning(
                        f"⚠️ Job não encontrado{server_msg} "
                        f"(tentativa {not_found_retries}/{max_not_found_retries}), "
                        f"aguardando {wait_time:.1f}s..."
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"❌ Job {job_id} perdido{server_msg} "
                        f"após {max_not_found_retries} tentativas."
                    )
                    # Marcar falha no JobManager
                    if self._job_manager and local_job_id:
                        self._job_manager.mark_job_failed(
                            local_job_id,
                            f"Job perdido após {max_not_found_retries} tentativas",
                            can_retry=True,
                        )
                    raise

            except RuntimeError as e:
                raise e
            except Exception as e:
                logger.warning(f"⚠️ Erro no polling: {e}")
                time.sleep(poll_interval)

        elapsed = time.time() - start_time

        # Marcar timeout no JobManager
        if self._job_manager and local_job_id:
            self._job_manager.mark_job_failed(
                local_job_id,
                f"Timeout após {elapsed:.1f}s",
                can_retry=True,
            )

        raise TimeoutError(f"Timeout após {elapsed:.1f}s aguardando conclusão do job {job_id}")
    
    def transcribe(
        self,
        audio: "AudioBuffer | np.ndarray | str",
        language: Optional[str] = None,
        translate: Optional[bool] = None,
        word_timestamps: Optional[bool] = None,
    ) -> TranscriptionResult:
        """
        Transcreve áudio usando WhisperAPI com failover inteligente.

        Características:
        - Tenta automaticamente em outro servidor se um falhar
        - Marca servidores problemáticos temporariamente
        - Só falha completamente após tentar todos os servidores disponíveis
        - Tracking persistente do job via JobManager

        Args:
            audio: AudioBuffer, numpy array, ou caminho do arquivo
            language: Idioma ('pt', 'en', 'auto', etc.)
            translate: Se True, traduz para inglês
            word_timestamps: Se True, inclui timestamps por palavra

        Returns:
            TranscriptionResult com texto, idioma, duração, etc.
        """
        start_time = time.time()
        language = language or self.language
        local_job_id = None

        # Preparar arquivo de áudio
        if isinstance(audio, str):
            audio_path = audio
            cleanup_file = False
        elif isinstance(audio, AudioBuffer):
            audio_path = tempfile.mktemp(suffix=".wav")
            self._save_audio(audio.data, audio_path)
            cleanup_file = True
        elif isinstance(audio, np.ndarray):
            audio_path = tempfile.mktemp(suffix=".wav")
            self._save_audio(audio, audio_path)
            cleanup_file = True
        else:
            raise TypeError(f"Tipo de áudio não suportado: {type(audio)}")

        try:
            # 0. Criar job local no JobManager (para tracking)
            if self._job_manager:
                local_job = self._job_manager.create_job(
                    audio_path=audio_path,
                    language=language,
                )
                local_job_id = local_job.id
                logger.debug(f"Job local criado: {local_job_id[:8]}")

            # Tentar transcrição com failover automático
            result, successful_server = self._transcribe_with_failover(
                audio_path=audio_path,
                language=language,
                translate=translate,
                word_timestamps=word_timestamps,
                local_job_id=local_job_id,
            )

            # Extrair resultado
            result_data = result.get('result', {})
            text = result_data.get('text', '')
            metadata = result_data.get('metadata', {})

            processing_time = time.time() - start_time
            server_processing_time = result_data.get('processingTime', processing_time)

            # Log resultado com servidor
            server_name = successful_server.split('/')[-1].replace(':3001', '') if successful_server else 'unknown'
            logger.info(
                f"📝 Transcrição: {len(text)} chars, "
                f"idioma: {metadata.get('language', language)}, "
                f"tempo: {server_processing_time:.1f}s, "
                f"servidor: {server_name}"
            )

            return TranscriptionResult(
                text=text.strip(),
                language=metadata.get('language', language),
                duration=metadata.get('duration', 0),
                processing_time=processing_time,
                model="whisperapi",
                segments=result_data.get('segments'),
                server_url=successful_server,
            )

        finally:
            if cleanup_file and os.path.exists(audio_path):
                try:
                    os.unlink(audio_path)
                except OSError:
                    pass

    def _transcribe_with_failover(
        self,
        audio_path: str,
        language: str,
        translate: Optional[bool],
        word_timestamps: Optional[bool],
        local_job_id: Optional[str],
    ) -> tuple:
        """
        Tenta transcrição com failover automático entre servidores.

        Se um servidor falhar, marca-o como problemático e tenta outro.
        Só falha completamente após tentar todos os servidores disponíveis.

        Args:
            audio_path: Caminho do arquivo de áudio
            language: Idioma para transcrição
            translate: Traduzir para inglês
            word_timestamps: Incluir timestamps por palavra
            local_job_id: ID do job local no JobManager

        Returns:
            Tuple (result_dict, server_url) com resultado da transcrição e servidor usado

        Raises:
            RuntimeError: Se todos os servidores falharem
        """
        tried_servers: set = set()
        last_error = None
        max_attempts = len(self.urls) * 2  # Permitir retry em cada servidor uma vez

        for attempt in range(max_attempts):
            # Selecionar servidor (evitando os que já falharam recentemente)
            server_url = self._select_server_for_job(exclude_servers=tried_servers)

            if not server_url:
                # Todos os servidores foram tentados, verificar se podemos tentar novamente
                if tried_servers:
                    # Limpar lista e tentar novamente (segunda rodada)
                    if attempt < len(self.urls):
                        tried_servers.clear()
                        server_url = self._select_server_for_job(exclude_servers=tried_servers)

                if not server_url:
                    break

            try:
                logger.info(
                    f"🔄 Tentativa {attempt + 1}/{max_attempts} em {server_url} "
                    f"(excluídos: {len(tried_servers)} servidores)"
                )

                # Upload para o servidor específico
                upload_result = self._upload_to_server(
                    audio_path=audio_path,
                    server_url=server_url,
                    language=language,
                    translate=translate,
                    word_timestamps=word_timestamps,
                )

                remote_job_id = upload_result.get('jobId')
                if not remote_job_id:
                    raise RuntimeError("WhisperAPI não retornou jobId")

                # Registrar job no JobManager
                if self._job_manager and local_job_id:
                    self._job_manager.mark_job_submitted(
                        local_job_id,
                        server_url=server_url,
                        remote_job_id=remote_job_id,
                    )

                # Pequeno delay para evitar race condition
                time.sleep(1.5)

                # Aguardar conclusão
                result = self.wait_for_completion(
                    remote_job_id,
                    server_url=server_url,
                    local_job_id=local_job_id,
                )

                # Sucesso! Marcar servidor como saudável
                if self._job_manager:
                    self._job_manager.mark_server_success(server_url)

                logger.info(f"✅ Transcrição bem-sucedida em {server_url}")
                return result, server_url

            except Exception as e:
                error_msg = str(e)
                last_error = e
                tried_servers.add(server_url)

                # Marcar servidor como problemático
                if self._job_manager:
                    self._job_manager.mark_server_failure(server_url, error_msg)

                # Log do erro
                remaining_servers = len(self.urls) - len(tried_servers)
                logger.warning(
                    f"⚠️ Servidor {server_url} falhou: {error_msg[:100]}... "
                    f"({remaining_servers} servidores restantes)"
                )

                # Se ainda há servidores para tentar, continua
                if remaining_servers > 0 or attempt < max_attempts - 1:
                    continue

        # Todos os servidores falharam
        if self._job_manager and local_job_id:
            self._job_manager.mark_job_failed(
                local_job_id,
                f"Todos os {len(self.urls)} servidores falharam",
                can_retry=False,
            )

        raise RuntimeError(
            f"Transcrição falhou em todos os {len(self.urls)} servidores. "
            f"Último erro: {last_error}"
        )

    def _select_server_for_job(self, exclude_servers: set = None) -> Optional[str]:
        """
        Seleciona o melhor servidor disponível, excluindo os problemáticos.

        Args:
            exclude_servers: Conjunto de URLs de servidores a evitar

        Returns:
            URL do servidor selecionado ou None se nenhum disponível
        """
        exclude_servers = exclude_servers or set()

        # Se JobManager disponível, usar seleção inteligente
        if self._job_manager:
            # Obter servidores saudáveis
            healthy_servers = self._job_manager.get_healthy_servers()

            # Filtrar os excluídos
            available = [s for s in healthy_servers if s not in exclude_servers]

            if available:
                # Usar o melhor servidor disponível
                return self._job_manager.get_next_server()

            # Se não há servidores saudáveis, tentar qualquer um não excluído
            all_available = [s for s in self.urls if s not in exclude_servers]
            if all_available:
                return all_available[0]

            return None

        # Fallback: Round Robin simples
        available = [s for s in self.urls if s not in exclude_servers]
        if available:
            with self._lock:
                server = available[self._current_index % len(available)]
                self._current_index += 1
                return server

        return None

    def _upload_to_server(
        self,
        audio_path: str,
        server_url: str,
        language: str,
        translate: Optional[bool],
        word_timestamps: Optional[bool],
    ) -> dict:
        """
        Envia áudio para um servidor específico.

        Args:
            audio_path: Caminho do arquivo de áudio
            server_url: URL do servidor de destino
            language: Idioma para transcrição
            translate: Traduzir para inglês
            word_timestamps: Incluir timestamps por palavra

        Returns:
            Dict com jobId e outras informações
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {audio_path}")

        translate = translate if translate is not None else self.translate
        word_timestamps = word_timestamps if word_timestamps is not None else self.word_timestamps

        try:
            client = self._get_client_for_url(server_url)

            with open(audio_path, 'rb') as f:
                files = {'audio': (Path(audio_path).name, f, 'audio/wav')}
                data = {
                    'language': language,
                    'translate': str(translate).lower(),
                    'wordTimestamps': str(word_timestamps).lower(),
                    'cleanup': str(self.cleanup).lower(),
                }

                logger.info(f"📤 Enviando áudio para {server_url}: {Path(audio_path).name}")

                response = client.post(
                    "/transcribe",
                    files=files,
                    data=data,
                    timeout=30.0,
                )
                response.raise_for_status()
                result = response.json()

            job_id = result.get('jobId')
            logger.info(f"✅ Upload OK! Job ID: {job_id} em {server_url}")

            result['server_url'] = server_url
            return result

        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Erro no upload para {server_url}: {error_msg}")
            raise RuntimeError(f"Upload falhou em {server_url}: {error_msg}")
    
    def _save_audio(self, audio: np.ndarray, path: str) -> None:
        """Salva array numpy como WAV (16kHz, mono, 16-bit)."""
        import wave

        if audio.dtype != np.int16:
            if audio.dtype in (np.float32, np.float64):
                audio = (audio * 32767).astype(np.int16)
            else:
                audio = audio.astype(np.int16)

        with wave.open(path, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(audio.tobytes())

    # =========================================================================
    # JobManager API - Métodos para gerenciamento inteligente de jobs
    # =========================================================================

    def get_job_manager_stats(self) -> dict:
        """
        Retorna estatísticas do JobManager.

        Returns:
            Dict com estatísticas de jobs e servidores
        """
        if not self._job_manager:
            return {"error": "JobManager não disponível"}

        return self._job_manager.stats

    def get_server_status(self) -> List[dict]:
        """
        Retorna status de todos os servidores registrados.

        Returns:
            Lista de dicts com status de cada servidor
        """
        if not self._job_manager:
            return []

        return self._job_manager.server_status

    def get_pending_jobs(self) -> List[dict]:
        """
        Retorna lista de jobs pendentes de processamento.

        Returns:
            Lista de jobs pendentes ou aguardando retry
        """
        if not self._job_manager:
            return []

        jobs = self._job_manager.get_pending_jobs()
        return [job.to_dict() for job in jobs]

    def get_in_progress_jobs(self) -> List[dict]:
        """
        Retorna lista de jobs em andamento.

        Returns:
            Lista de jobs sendo processados
        """
        if not self._job_manager:
            return []

        jobs = self._job_manager.get_in_progress_jobs()
        return [job.to_dict() for job in jobs]

    def retry_failed_jobs(self) -> int:
        """
        Processa jobs pendentes de retry.

        Returns:
            Número de jobs reprocessados
        """
        if not self._job_manager:
            return 0

        pending = self._job_manager.get_pending_jobs()
        retried = 0

        for job in pending:
            if job.state == "retrying" and os.path.exists(job.audio_path):
                try:
                    logger.info(f"🔄 Retrying job {job.id[:8]}...")
                    self.transcribe(job.audio_path, language=job.language)
                    retried += 1
                except Exception as e:
                    logger.error(f"Retry falhou para {job.id[:8]}: {e}")

        return retried

    def cleanup_old_jobs(self, max_age_hours: int = 24):
        """
        Remove jobs antigos completados ou falhos.

        Args:
            max_age_hours: Idade máxima em horas
        """
        if self._job_manager:
            self._job_manager.cleanup_old_jobs(max_age_hours)

    def close(self):
        """Fecha conexões HTTP."""
        if self._http_client:
            self._http_client.close()
            self._http_client = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


def get_transcriber(config: dict) -> "WhisperTranscriber | WhisperAPIClient":
    """
    Factory function para criar transcritor baseado na configuração.
    
    Args:
        config: Dicionário com configurações do Whisper
        
    Returns:
        Instância do transcritor apropriado
    """
    provider = config.get('provider', 'local')
    
    if provider == 'whisperapi':
        return WhisperAPIClient(
            base_url=config.get('whisperapi_url', 'http://127.0.0.1:3001'),
            base_urls=config.get('whisperapi_urls', []),
            language=config.get('language', 'pt'),
            timeout=config.get('whisperapi_timeout', 300),
        )
    
    elif provider == 'openai':
        # OpenAI Whisper API (futuro)
        logger.warning("OpenAI Whisper API não implementado, usando local")
        # Fallthrough para local
    
    # Default: local whisper.cpp
    return WhisperTranscriber(
        model=config.get('model', 'tiny'),
        language=config.get('language', 'pt'),
        use_cpp=config.get('use_cpp', True),
        threads=config.get('threads', 2),
        beam_size=config.get('beam_size', 1),
        stream_mode=config.get('stream_mode', False),
    )
