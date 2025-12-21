"""Testes para módulo de cache."""

import tempfile
import time
from pathlib import Path

import pytest

from src.utils.cache import Cache


@pytest.fixture
def cache():
    """Fixture de cache para testes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Cache(
            cache_dir=tmpdir,
            ttl=10,
            max_memory_entries=5,
            enabled=True,
        )


def test_cache_set_get(cache):
    """Testa set e get básico."""
    cache.set("key1", "value1")
    result = cache.get("key1")
    assert result == "value1"


def test_cache_miss(cache):
    """Testa cache miss."""
    result = cache.get("nonexistent")
    assert result is None


def test_cache_dict_value(cache):
    """Testa armazenamento de dicionário."""
    data = {"text": "hello", "count": 42}
    cache.set("dict_key", data)

    result = cache.get("dict_key")
    assert result == data


def test_cache_delete(cache):
    """Testa remoção de entrada."""
    cache.set("to_delete", "value")
    assert cache.get("to_delete") == "value"

    removed = cache.delete("to_delete")
    assert removed is True
    assert cache.get("to_delete") is None


def test_cache_clear(cache):
    """Testa limpeza do cache."""
    cache.set("key1", "value1")
    cache.set("key2", "value2")

    cache.clear()

    assert cache.get("key1") is None
    assert cache.get("key2") is None


def test_cache_disabled():
    """Testa cache desabilitado."""
    cache = Cache(enabled=False)

    cache.set("key", "value")
    result = cache.get("key")

    assert result is None


def test_cache_stats(cache):
    """Testa estatísticas do cache."""
    cache.set("key1", "value1")
    cache.set("key2", "value2")

    stats = cache.get_stats()

    assert stats["enabled"] is True
    assert stats["memory_entries"] == 2
    assert stats["ttl"] == 10


def test_cache_eviction(cache):
    """Testa eviction quando cache está cheio."""
    # Preencher cache além do limite
    for i in range(10):
        cache.set(f"key{i}", f"value{i}")

    # Algumas entradas devem ter sido removidas
    stats = cache.get_stats()
    assert stats["memory_entries"] <= 5
