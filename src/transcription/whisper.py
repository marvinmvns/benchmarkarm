"""
Transcrição de áudio usando Whisper.
Suporta whisper.cpp (otimizado para ARM) e Whisper Python.
"""

import logging
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Literal
import json

import numpy as np

from ..audio.capture import AudioBuffer

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

    @property
    def words_per_second(self) -> float:
        """Palavras por segundo de processamento."""
        words = len(self.text.split())
        return words / self.processing_time if self.processing_time > 0 else 0

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "text": self.text,
            "language": self.language,
            "duration": self.duration,
            "processing_time": self.processing_time,
            "model": self.model,
            "segments": self.segments,
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

        # Converter para arquivo WAV temporário se necessário
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            if isinstance(audio, AudioBuffer):
                audio.save(tmp_path)
                duration = audio.duration
            elif isinstance(audio, np.ndarray):
                self._save_audio(audio, tmp_path)
                duration = len(audio) / 16000  # Assume 16kHz
            elif isinstance(audio, str):
                if Path(audio).exists():
                    tmp_path = audio
                    # Obter duração do arquivo
                    import wave
                    with wave.open(audio, 'rb') as wav:
                        duration = wav.getnframes() / wav.getframerate()
                else:
                    raise FileNotFoundError(f"Arquivo não encontrado: {audio}")
            else:
                raise TypeError(f"Tipo de áudio não suportado: {type(audio)}")

            # Transcrever
            if self.use_cpp and self._cpp_available:
                try:
                    result = self._transcribe_cpp(tmp_path, language)
                except RuntimeError as e:
                    # Se falhar com OOM (-9) ou outro erro, tentar Python
                    error_msg = str(e)
                    if "código -9" in error_msg or "código -11" in error_msg:
                        logger.warning(
                            f"⚠️ whisper.cpp falhou com OOM. "
                            f"Tentando fallback para Whisper Python..."
                        )
                        result = self._transcribe_python(tmp_path, language)
                    else:
                        raise
            else:
                result = self._transcribe_python(tmp_path, language)

            processing_time = time.time() - start_time

            return TranscriptionResult(
                text=result["text"],
                language=result.get("language", language),
                duration=duration,
                processing_time=processing_time,
                model=self.model,
                segments=result.get("segments"),
            )

        finally:
            # Limpar arquivo temporário
            if isinstance(audio, (AudioBuffer, np.ndarray)):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

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

            result = subprocess.run(
                cmd,
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
