"""
Limitador de CPU para evitar congelamento do Raspberry Pi.

Monitora uso de CPU e pausa processamento quando excede limite configurado.
Usa nice/ionice para reduzir prioridade de processos pesados.
"""

import logging
import os
import signal
import subprocess
import threading
import time
from typing import Optional, Callable

logger = logging.getLogger(__name__)

# Tentar importar psutil
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil não disponível. Limitador de CPU desabilitado.")


class CPULimiter:
    """
    Limitador de uso de CPU.
    
    Pausa a execução quando CPU excede o limite configurado,
    permitindo que o sistema use swap sem congelar.
    """
    
    def __init__(
        self,
        enabled: bool = True,
        max_percent: int = 85,
        check_interval: float = 1.0,
    ):
        self.enabled = enabled and PSUTIL_AVAILABLE
        self.max_percent = max(50, min(95, max_percent))  # Entre 50% e 95%
        self.check_interval = check_interval
        
        self._paused = False
        self._pause_event = threading.Event()
        self._pause_event.set()  # Começa não pausado
        
        if self.enabled:
            logger.info(f"⚡ Limitador de CPU ativo: máx {self.max_percent}%")
    
    def get_cpu_percent(self) -> float:
        """Retorna uso atual de CPU."""
        if not PSUTIL_AVAILABLE:
            return 0.0
        try:
            return psutil.cpu_percent(interval=0.1)
        except Exception:
            return 0.0
    
    def get_memory_percent(self) -> float:
        """Retorna uso atual de memória."""
        if not PSUTIL_AVAILABLE:
            return 0.0
        try:
            return psutil.virtual_memory().percent
        except Exception:
            return 0.0
    
    def is_overloaded(self) -> bool:
        """Verifica se sistema está sobrecarregado."""
        if not self.enabled:
            return False
        
        cpu = self.get_cpu_percent()
        return cpu > self.max_percent
    
    def wait_if_overloaded(self, timeout: float = 60.0) -> bool:
        """
        Espera se CPU estiver sobrecarregada.
        
        Args:
            timeout: Tempo máximo de espera em segundos
            
        Returns:
            True se esperou, False se não foi necessário
        """
        if not self.enabled:
            return False
        
        waited = False
        start_time = time.time()
        
        while self.is_overloaded():
            if not waited:
                cpu = self.get_cpu_percent()
                mem = self.get_memory_percent()
                logger.warning(
                    f"⏸️ CPU alta ({cpu:.1f}%), pausando... "
                    f"(limite: {self.max_percent}%, mem: {mem:.1f}%)"
                )
                waited = True
            
            # Verificar timeout
            if time.time() - start_time > timeout:
                logger.warning(f"⚠️ Timeout de {timeout}s atingido, continuando...")
                break
            
            # Esperar um pouco
            time.sleep(self.check_interval)
        
        if waited:
            cpu = self.get_cpu_percent()
            logger.info(f"▶️ CPU normalizada ({cpu:.1f}%), continuando...")
        
        return waited
    
    def run_with_limit(
        self,
        func: Callable,
        *args,
        nice: int = 10,
        **kwargs,
    ):
        """
        Executa função com limitação de CPU.
        
        Args:
            func: Função a executar
            nice: Valor de nice (0-19, maior = menor prioridade)
            
        Returns:
            Resultado da função
        """
        # Esperar se CPU estiver alta antes de começar
        self.wait_if_overloaded()
        
        # Tentar reduzir prioridade do processo atual
        if self.enabled:
            try:
                os.nice(nice)
            except (OSError, AttributeError):
                pass  # Pode falhar se já foi chamado nice
        
        return func(*args, **kwargs)
    
    def run_subprocess_with_limit(
        self,
        cmd: list,
        timeout: Optional[int] = None,
        **kwargs,
    ) -> subprocess.CompletedProcess:
        """
        Executa subprocess com limitação de CPU usando nice/ionice.
        
        Args:
            cmd: Comando a executar
            timeout: Timeout em segundos
            
        Returns:
            CompletedProcess
        """
        # Esperar se CPU estiver alta
        self.wait_if_overloaded()
        
        # Adicionar nice e ionice para reduzir prioridade
        if self.enabled:
            # nice -n 15: baixa prioridade de CPU
            # ionice -c 3: classe idle para I/O
            prefix = ["nice", "-n", "15", "ionice", "-c", "3"]
            cmd = prefix + cmd
        
        return subprocess.run(cmd, timeout=timeout, **kwargs)


# Instância global (singleton)
_cpu_limiter: Optional[CPULimiter] = None


def get_cpu_limiter(
    enabled: bool = True,
    max_percent: int = 85,
    check_interval: float = 1.0,
) -> CPULimiter:
    """Retorna o limitador de CPU (singleton)."""
    global _cpu_limiter
    if _cpu_limiter is None:
        _cpu_limiter = CPULimiter(
            enabled=enabled,
            max_percent=max_percent,
            check_interval=check_interval,
        )
    return _cpu_limiter


def reset_cpu_limiter():
    """Reseta o limitador de CPU."""
    global _cpu_limiter
    _cpu_limiter = None
