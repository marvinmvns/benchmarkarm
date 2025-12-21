"""Testes para módulo de configuração."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from src.utils.config import (
    Config,
    load_config,
    expand_env_vars,
    AudioConfig,
    WhisperConfig,
)


def test_expand_env_vars():
    """Testa expansão de variáveis de ambiente."""
    os.environ["TEST_VAR"] = "test_value"

    result = expand_env_vars("${TEST_VAR}")
    assert result == "test_value"

    result = expand_env_vars("prefix_${TEST_VAR}_suffix")
    assert result == "prefix_test_value_suffix"

    result = expand_env_vars("no_vars_here")
    assert result == "no_vars_here"


def test_default_config():
    """Testa configuração padrão."""
    config = Config()

    assert config.mode == "hybrid"
    assert config.audio.sample_rate == 16000
    assert config.whisper.model == "tiny"
    assert config.llm.provider == "local"


def test_config_from_dict():
    """Testa criação de config a partir de dicionário."""
    data = {
        "mode": "local",
        "audio": {
            "sample_rate": 8000,
            "channels": 2,
        },
        "whisper": {
            "model": "base",
            "language": "en",
        },
    }

    config = Config.from_dict(data)

    assert config.mode == "local"
    assert config.audio.sample_rate == 8000
    assert config.audio.channels == 2
    assert config.whisper.model == "base"
    assert config.whisper.language == "en"


def test_load_config_file():
    """Testa carregamento de arquivo de configuração."""
    config_data = {
        "mode": "api",
        "whisper": {
            "model": "small",
        },
    }

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        delete=False,
    ) as f:
        yaml.dump(config_data, f)
        config_path = f.name

    try:
        config = load_config(config_path)
        assert config.mode == "api"
        assert config.whisper.model == "small"
    finally:
        os.unlink(config_path)


def test_audio_config_defaults():
    """Testa valores padrão de AudioConfig."""
    audio = AudioConfig()

    assert audio.sample_rate == 16000
    assert audio.channels == 1
    assert audio.chunk_size == 1024
    assert audio.vad_enabled is True


def test_whisper_config_defaults():
    """Testa valores padrão de WhisperConfig."""
    whisper = WhisperConfig()

    assert whisper.model == "tiny"
    assert whisper.language == "pt"
    assert whisper.use_cpp is True
    assert whisper.threads == 4
