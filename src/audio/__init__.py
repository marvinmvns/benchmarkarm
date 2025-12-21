"""Módulos de captura e processamento de áudio."""

from .capture import AudioCapture, AudioBuffer
from .vad import VoiceActivityDetector

__all__ = ["AudioCapture", "AudioBuffer", "VoiceActivityDetector"]
