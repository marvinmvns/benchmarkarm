"""
Voice Activity Detection (VAD) otimizado para Raspberry Pi.
Usa WebRTC VAD para detecção eficiente de fala.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VADResult:
    """Resultado da detecção de voz."""
    is_speech: bool
    confidence: float
    energy: float


class VoiceActivityDetector:
    """
    Detector de Atividade de Voz usando WebRTC VAD.

    Características:
    - Baixo uso de CPU (ideal para Raspberry Pi)
    - Níveis de agressividade configuráveis
    - Suporte a diferentes taxas de amostragem
    - Cache de resultados para reduzir processamento
    """

    # Frame sizes suportados pelo WebRTC VAD (em ms)
    VALID_FRAME_DURATIONS = [10, 20, 30]

    def __init__(
        self,
        sample_rate: int = 16000,
        aggressiveness: int = 2,
        min_speech_duration: float = 0.5,
        frame_duration_ms: int = 30,
    ):
        """
        Inicializa o detector de voz.

        Args:
            sample_rate: Taxa de amostragem (8000, 16000, 32000 ou 48000)
            aggressiveness: Nível de agressividade (0-3)
                           0 = menos agressivo, mais falsos positivos
                           3 = mais agressivo, pode perder fala suave
            min_speech_duration: Duração mínima de fala em segundos
            frame_duration_ms: Duração do frame em ms (10, 20 ou 30)
        """
        self.sample_rate = sample_rate
        self.aggressiveness = max(0, min(3, aggressiveness))
        self.min_speech_duration = min_speech_duration
        self.frame_duration_ms = frame_duration_ms

        # Validar parâmetros
        if sample_rate not in [8000, 16000, 32000, 48000]:
            raise ValueError(f"Sample rate {sample_rate} não suportado. Use 8000, 16000, 32000 ou 48000")

        if frame_duration_ms not in self.VALID_FRAME_DURATIONS:
            raise ValueError(f"Frame duration {frame_duration_ms}ms não suportado. Use 10, 20 ou 30")

        # Calcular tamanho do frame
        self.frame_size = int(sample_rate * frame_duration_ms / 1000)

        # Inicializar VAD
        self._vad = None
        self._init_vad()

        # Estado para tracking de fala
        self._speech_frames = 0
        self._silence_frames = 0
        self._min_speech_frames = int(min_speech_duration * 1000 / frame_duration_ms)

        logger.info(
            f"VAD inicializado: sample_rate={sample_rate}, "
            f"aggressiveness={aggressiveness}, frame_size={self.frame_size}"
        )

    def _init_vad(self) -> None:
        """Inicializa o WebRTC VAD."""
        try:
            import webrtcvad
            self._vad = webrtcvad.Vad(self.aggressiveness)
        except ImportError:
            logger.warning(
                "webrtcvad não instalado. Usando detector de energia simples. "
                "Para melhor detecção, execute: pip install webrtcvad"
            )
            self._vad = None

    def is_speech(
        self,
        audio: np.ndarray,
        return_details: bool = False,
    ) -> bool | VADResult:
        """
        Verifica se o áudio contém fala.

        Args:
            audio: Array numpy com áudio (int16)
            return_details: Se True, retorna VADResult com detalhes

        Returns:
            True se contém fala, ou VADResult se return_details=True
        """
        # Converter para int16 se necessário
        if audio.dtype != np.int16:
            if audio.dtype == np.float32 or audio.dtype == np.float64:
                audio = (audio * 32767).astype(np.int16)
            else:
                audio = audio.astype(np.int16)

        # Calcular energia do sinal
        energy = np.sqrt(np.mean(audio.astype(np.float64) ** 2))

        # Usar WebRTC VAD se disponível
        if self._vad is not None:
            is_speech = self._check_vad(audio)
        else:
            # Fallback: detector de energia simples
            is_speech = self._check_energy(audio, energy)

        # Calcular confiança baseada em energia
        max_energy = 10000  # Normalização aproximada
        confidence = min(1.0, energy / max_energy) if is_speech else 0.0

        if return_details:
            return VADResult(
                is_speech=is_speech,
                confidence=confidence,
                energy=energy,
            )

        return is_speech

    def _check_vad(self, audio: np.ndarray) -> bool:
        """Verifica VAD usando WebRTC."""
        # Processar em frames do tamanho correto
        speech_count = 0
        total_frames = 0

        for i in range(0, len(audio) - self.frame_size + 1, self.frame_size):
            frame = audio[i:i + self.frame_size]
            frame_bytes = frame.tobytes()

            try:
                if self._vad.is_speech(frame_bytes, self.sample_rate):
                    speech_count += 1
                total_frames += 1
            except Exception:
                pass

        # Considerar fala se mais de 50% dos frames têm fala
        if total_frames == 0:
            return False

        return speech_count / total_frames > 0.5

    def _check_energy(self, audio: np.ndarray, energy: float) -> bool:
        """Detector de fala simples baseado em energia."""
        # Threshold dinâmico baseado no ruído de fundo
        # Valores típicos para fala: 500-5000
        threshold = 300  # Threshold base

        # Ajustar por agressividade
        threshold *= (1 + self.aggressiveness * 0.5)

        return energy > threshold

    def process_stream(
        self,
        audio: np.ndarray,
    ) -> tuple[bool, float]:
        """
        Processa stream de áudio e retorna estado de fala.

        Implementa lógica de debouncing para evitar falsos positivos.

        Args:
            audio: Chunk de áudio

        Returns:
            Tupla (is_speaking, duration_seconds)
        """
        result = self.is_speech(audio, return_details=True)

        if result.is_speech:
            self._speech_frames += 1
            self._silence_frames = 0
        else:
            self._silence_frames += 1

            # Reset após silêncio prolongado
            if self._silence_frames > self._min_speech_frames * 2:
                self._speech_frames = 0

        # Considerar fala válida apenas após duração mínima
        is_valid_speech = self._speech_frames >= self._min_speech_frames
        duration = self._speech_frames * self.frame_duration_ms / 1000

        return is_valid_speech, duration

    def reset(self) -> None:
        """Reseta estado do detector."""
        self._speech_frames = 0
        self._silence_frames = 0

    def get_speech_segments(
        self,
        audio: np.ndarray,
        min_silence_duration: float = 0.3,
    ) -> list[tuple[int, int]]:
        """
        Encontra segmentos de fala no áudio.

        Args:
            audio: Array completo de áudio
            min_silence_duration: Duração mínima de silêncio entre segmentos

        Returns:
            Lista de tuplas (start_sample, end_sample)
        """
        segments = []
        in_speech = False
        speech_start = 0
        silence_start = 0

        min_silence_frames = int(min_silence_duration * 1000 / self.frame_duration_ms)

        for i in range(0, len(audio) - self.frame_size + 1, self.frame_size):
            frame = audio[i:i + self.frame_size]
            is_speech = self.is_speech(frame)

            if is_speech and not in_speech:
                # Início de fala
                in_speech = True
                speech_start = i
            elif not is_speech and in_speech:
                # Possível fim de fala
                if silence_start == 0:
                    silence_start = i

                silence_frames = (i - silence_start) // self.frame_size
                if silence_frames >= min_silence_frames:
                    # Fim de fala confirmado
                    segments.append((speech_start, silence_start))
                    in_speech = False
                    silence_start = 0
            elif is_speech and in_speech:
                # Continua fala
                silence_start = 0

        # Adicionar segmento final se estiver em fala
        if in_speech:
            segments.append((speech_start, len(audio)))

        return segments

    def trim_silence(
        self,
        audio: np.ndarray,
        pad_ms: int = 100,
    ) -> np.ndarray:
        """
        Remove silêncio do início e fim do áudio.

        Args:
            audio: Array de áudio
            pad_ms: Padding em ms para manter nas bordas

        Returns:
            Áudio sem silêncio
        """
        segments = self.get_speech_segments(audio)

        if not segments:
            return audio

        # Encontrar início e fim da fala
        start = segments[0][0]
        end = segments[-1][1]

        # Adicionar padding
        pad_samples = int(pad_ms * self.sample_rate / 1000)
        start = max(0, start - pad_samples)
        end = min(len(audio), end + pad_samples)

        return audio[start:end]


class SileroVAD:
    """
    VAD usando modelo Silero (mais preciso, mas mais lento).
    Recomendado para Pi 4+ ou quando precisão é crítica.
    """

    def __init__(self, sample_rate: int = 16000):
        """
        Inicializa Silero VAD.

        Requer: pip install torch torchaudio
        """
        self.sample_rate = sample_rate
        self._model = None
        self._utils = None

    def _load_model(self):
        """Carrega modelo Silero sob demanda."""
        if self._model is not None:
            return

        try:
            import torch
            model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False
            )
            self._model = model
            self._utils = utils
            logger.info("Silero VAD carregado")
        except Exception as e:
            raise RuntimeError(f"Erro ao carregar Silero VAD: {e}")

    def is_speech(self, audio: np.ndarray, threshold: float = 0.5) -> bool:
        """
        Verifica se o áudio contém fala.

        Args:
            audio: Array numpy com áudio
            threshold: Limiar de probabilidade (0-1)

        Returns:
            True se contém fala
        """
        self._load_model()

        import torch

        # Converter para tensor
        if audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0

        audio_tensor = torch.from_numpy(audio)

        # Inferência
        speech_prob = self._model(audio_tensor, self.sample_rate).item()

        return speech_prob > threshold
