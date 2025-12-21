"""
Sistema de cache para Voice Processor.
Otimizado para reduzir processamento redundante no Raspberry Pi.
"""

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass
import threading


@dataclass
class CacheEntry:
    """Entrada de cache."""
    value: Any
    timestamp: float
    ttl: int


class Cache:
    """
    Cache em memória e disco para resultados de transcrição e LLM.

    Otimizações:
    - Cache em memória para acesso rápido
    - Persistência em disco para reinicializações
    - TTL configurável
    - Limpeza automática de entradas expiradas
    """

    def __init__(
        self,
        cache_dir: str = "~/.cache/voice-processor",
        ttl: int = 3600,
        max_memory_entries: int = 100,
        enabled: bool = True,
    ):
        """
        Inicializa o cache.

        Args:
            cache_dir: Diretório para cache em disco
            ttl: Tempo de vida em segundos
            max_memory_entries: Número máximo de entradas em memória
            enabled: Se o cache está habilitado
        """
        self.enabled = enabled
        self.ttl = ttl
        self.max_memory_entries = max_memory_entries
        self.cache_dir = Path(cache_dir).expanduser()

        # Cache em memória
        self._memory_cache: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()

        # Criar diretório se necessário
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _hash_key(self, key: str) -> str:
        """Gera hash MD5 da chave."""
        return hashlib.md5(key.encode()).hexdigest()

    def _get_disk_path(self, hashed_key: str) -> Path:
        """Retorna caminho do arquivo de cache."""
        return self.cache_dir / f"{hashed_key}.json"

    def _is_expired(self, entry: CacheEntry) -> bool:
        """Verifica se entrada expirou."""
        return time.time() - entry.timestamp > entry.ttl

    def get(self, key: str) -> Optional[Any]:
        """
        Obtém valor do cache.

        Args:
            key: Chave do cache

        Returns:
            Valor cacheado ou None se não encontrado/expirado
        """
        if not self.enabled:
            return None

        hashed_key = self._hash_key(key)

        # Tentar cache em memória primeiro
        with self._lock:
            if hashed_key in self._memory_cache:
                entry = self._memory_cache[hashed_key]
                if not self._is_expired(entry):
                    return entry.value
                else:
                    del self._memory_cache[hashed_key]

        # Tentar cache em disco
        disk_path = self._get_disk_path(hashed_key)
        if disk_path.exists():
            try:
                with open(disk_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    entry = CacheEntry(
                        value=data["value"],
                        timestamp=data["timestamp"],
                        ttl=data["ttl"],
                    )

                    if not self._is_expired(entry):
                        # Carregar em memória para acesso futuro
                        with self._lock:
                            self._memory_cache[hashed_key] = entry
                        return entry.value
                    else:
                        # Remover arquivo expirado
                        disk_path.unlink()
            except (json.JSONDecodeError, KeyError, IOError):
                pass

        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Armazena valor no cache.

        Args:
            key: Chave do cache
            value: Valor a armazenar
            ttl: Tempo de vida (usa padrão se None)
        """
        if not self.enabled:
            return

        hashed_key = self._hash_key(key)
        entry_ttl = ttl if ttl is not None else self.ttl

        entry = CacheEntry(
            value=value,
            timestamp=time.time(),
            ttl=entry_ttl,
        )

        # Salvar em memória
        with self._lock:
            # Limpar se atingiu limite
            if len(self._memory_cache) >= self.max_memory_entries:
                self._evict_oldest()

            self._memory_cache[hashed_key] = entry

        # Salvar em disco
        disk_path = self._get_disk_path(hashed_key)
        try:
            with open(disk_path, "w", encoding="utf-8") as f:
                json.dump({
                    "value": value,
                    "timestamp": entry.timestamp,
                    "ttl": entry_ttl,
                }, f)
        except IOError:
            pass  # Falha silenciosa em caso de erro de disco

    def _evict_oldest(self) -> None:
        """Remove entradas mais antigas do cache em memória."""
        if not self._memory_cache:
            return

        # Ordenar por timestamp e remover 20% mais antigas
        sorted_keys = sorted(
            self._memory_cache.keys(),
            key=lambda k: self._memory_cache[k].timestamp
        )

        to_remove = max(1, len(sorted_keys) // 5)
        for key in sorted_keys[:to_remove]:
            del self._memory_cache[key]

    def delete(self, key: str) -> bool:
        """
        Remove entrada do cache.

        Args:
            key: Chave do cache

        Returns:
            True se removido, False se não encontrado
        """
        if not self.enabled:
            return False

        hashed_key = self._hash_key(key)
        removed = False

        with self._lock:
            if hashed_key in self._memory_cache:
                del self._memory_cache[hashed_key]
                removed = True

        disk_path = self._get_disk_path(hashed_key)
        if disk_path.exists():
            disk_path.unlink()
            removed = True

        return removed

    def clear(self) -> None:
        """Limpa todo o cache."""
        with self._lock:
            self._memory_cache.clear()

        if self.cache_dir.exists():
            for f in self.cache_dir.glob("*.json"):
                try:
                    f.unlink()
                except IOError:
                    pass

    def cleanup_expired(self) -> int:
        """
        Remove entradas expiradas.

        Returns:
            Número de entradas removidas
        """
        removed = 0

        # Limpar memória
        with self._lock:
            expired_keys = [
                k for k, v in self._memory_cache.items()
                if self._is_expired(v)
            ]
            for key in expired_keys:
                del self._memory_cache[key]
                removed += 1

        # Limpar disco
        if self.cache_dir.exists():
            for f in self.cache_dir.glob("*.json"):
                try:
                    with open(f, "r", encoding="utf-8") as file:
                        data = json.load(file)
                        entry = CacheEntry(
                            value=data["value"],
                            timestamp=data["timestamp"],
                            ttl=data["ttl"],
                        )
                        if self._is_expired(entry):
                            f.unlink()
                            removed += 1
                except (json.JSONDecodeError, KeyError, IOError):
                    f.unlink()  # Remove arquivo corrompido
                    removed += 1

        return removed

    def get_stats(self) -> dict:
        """Retorna estatísticas do cache."""
        disk_count = 0
        disk_size = 0

        if self.cache_dir.exists():
            for f in self.cache_dir.glob("*.json"):
                disk_count += 1
                disk_size += f.stat().st_size

        return {
            "memory_entries": len(self._memory_cache),
            "disk_entries": disk_count,
            "disk_size_bytes": disk_size,
            "enabled": self.enabled,
            "ttl": self.ttl,
        }


# Instância global do cache
_global_cache: Optional[Cache] = None


def get_cache() -> Cache:
    """Retorna instância global do cache."""
    global _global_cache
    if _global_cache is None:
        _global_cache = Cache()
    return _global_cache


def init_cache(
    cache_dir: str = "~/.cache/voice-processor",
    ttl: int = 3600,
    enabled: bool = True,
) -> Cache:
    """Inicializa cache global com configurações específicas."""
    global _global_cache
    _global_cache = Cache(cache_dir=cache_dir, ttl=ttl, enabled=enabled)
    return _global_cache
