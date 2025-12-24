"""
Gerenciador Inteligente de Jobs para WhisperAPI.

Funcionalidades:
- Tracking persistente de jobs (sobrevive restarts)
- Health-aware Round Robin (só usa servidores saudáveis)
- Backoff adaptativo baseado no estado da fila
- Retry automático com backoff exponencial
- Recovery de jobs pendentes no startup
"""

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Callable, Any
import queue

logger = logging.getLogger(__name__)


class JobState(Enum):
    """Estados possíveis de um job."""
    PENDING = "pending"          # Aguardando envio
    SUBMITTED = "submitted"      # Enviado, aguardando processamento
    PROCESSING = "processing"    # Em processamento no servidor
    COMPLETED = "completed"      # Concluído com sucesso
    FAILED = "failed"            # Falhou permanentemente
    RETRYING = "retrying"        # Aguardando retry


@dataclass
class Job:
    """Representa um job de transcrição."""
    id: str                                  # UUID local
    audio_path: str                          # Caminho do arquivo de áudio
    server_url: Optional[str] = None         # URL do servidor que processou
    remote_job_id: Optional[str] = None      # ID do job no servidor remoto
    state: str = "pending"                   # Estado atual (string para serialização)

    # Timestamps
    created_at: str = ""                     # ISO format
    submitted_at: Optional[str] = None
    completed_at: Optional[str] = None

    # Resultado
    result_text: Optional[str] = None
    result_language: Optional[str] = None
    result_duration: Optional[float] = None
    processing_time: Optional[float] = None

    # Retry info
    retry_count: int = 0
    max_retries: int = 3
    last_error: Optional[str] = None
    next_retry_at: Optional[str] = None

    # Metadados
    language: str = "pt"
    priority: int = 0                        # Maior = mais prioritário

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    @property
    def state_enum(self) -> JobState:
        return JobState(self.state)

    @state_enum.setter
    def state_enum(self, value: JobState):
        self.state = value.value

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Job":
        return cls(**data)

    def can_retry(self) -> bool:
        """Verifica se pode tentar novamente."""
        return self.retry_count < self.max_retries and self.state in ("failed", "retrying")


@dataclass
class ServerHealth:
    """Saúde de um servidor WhisperAPI."""
    url: str
    is_healthy: bool = True
    last_check: Optional[str] = None
    last_success: Optional[str] = None
    last_failure: Optional[str] = None
    failure_count: int = 0
    consecutive_failures: int = 0
    queue_length: int = 0
    active_jobs: int = 0
    avg_processing_time: float = 0.0
    available_workers: int = 0
    total_workers: int = 0

    # Backoff
    backoff_until: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ServerHealth":
        return cls(**data)

    def is_available(self) -> bool:
        """Verifica se servidor está disponível (saudável e sem backoff)."""
        if not self.is_healthy:
            return False

        if self.backoff_until:
            backoff_time = datetime.fromisoformat(self.backoff_until)
            if datetime.now() < backoff_time:
                return False

        return True

    def mark_success(self):
        """Marca um sucesso."""
        now = datetime.now().isoformat()
        self.last_success = now
        self.last_check = now
        self.consecutive_failures = 0
        self.is_healthy = True
        self.backoff_until = None

    def mark_failure(self, error: str = ""):
        """Marca uma falha com backoff exponencial."""
        now = datetime.now()
        self.last_failure = now.isoformat()
        self.last_check = now.isoformat()
        self.failure_count += 1
        self.consecutive_failures += 1

        # Backoff exponencial: 30s, 60s, 120s, 240s, max 10min
        backoff_seconds = min(30 * (2 ** (self.consecutive_failures - 1)), 600)
        self.backoff_until = (
            datetime.fromtimestamp(now.timestamp() + backoff_seconds)
        ).isoformat()

        # Marcar como não saudável após 3 falhas consecutivas
        if self.consecutive_failures >= 3:
            self.is_healthy = False
            logger.warning(
                f"🔴 Servidor {self.url} marcado como não saudável "
                f"após {self.consecutive_failures} falhas consecutivas"
            )


class JobManager:
    """
    Gerenciador central de jobs de transcrição.

    Responsabilidades:
    - Manter estado de todos os jobs
    - Persistir estado em disco
    - Gerenciar saúde dos servidores
    - Implementar Round Robin inteligente
    - Recuperar jobs pendentes no restart
    """

    def __init__(
        self,
        state_file: Optional[str] = None,
        health_check_interval: float = 60.0,
        max_concurrent_jobs: int = 5,
    ):
        """
        Inicializa o JobManager.

        Args:
            state_file: Caminho para arquivo de estado (JSON)
            health_check_interval: Intervalo entre health checks (segundos)
            max_concurrent_jobs: Máximo de jobs simultâneos por servidor
        """
        # Configuração
        self._project_root = self._find_project_root()
        self.state_file = state_file or str(
            self._project_root / "data" / "job_state.json"
        )
        self.health_check_interval = health_check_interval
        self.max_concurrent_jobs = max_concurrent_jobs

        # Estado
        self._jobs: Dict[str, Job] = {}
        self._servers: Dict[str, ServerHealth] = {}
        self._lock = threading.RLock()

        # Round Robin
        self._current_server_index = 0

        # Background workers
        self._running = False
        self._health_thread: Optional[threading.Thread] = None
        self._poll_thread: Optional[threading.Thread] = None

        # Callbacks
        self._on_job_completed: Optional[Callable[[Job], None]] = None
        self._on_job_failed: Optional[Callable[[Job], None]] = None

        # Estatísticas
        self._stats = {
            "total_jobs": 0,
            "completed_jobs": 0,
            "failed_jobs": 0,
            "retried_jobs": 0,
            "total_processing_time": 0.0,
        }

        # Carregar estado persistido
        self._load_state()

        logger.info(
            f"JobManager inicializado: {len(self._jobs)} jobs carregados, "
            f"{len(self._servers)} servidores"
        )

    def _find_project_root(self) -> Path:
        """Encontra diretório raiz do projeto."""
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "config").is_dir() or (parent / "external").is_dir():
                return parent
        return current.parent.parent.parent

    # =========================================================================
    # Persistência
    # =========================================================================

    def _load_state(self):
        """Carrega estado do arquivo."""
        try:
            state_path = Path(self.state_file)
            if not state_path.exists():
                logger.info("Arquivo de estado não existe, iniciando vazio")
                return

            with open(state_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Carregar jobs
            for job_data in data.get("jobs", []):
                job = Job.from_dict(job_data)
                self._jobs[job.id] = job

            # Carregar servidores
            for server_data in data.get("servers", []):
                server = ServerHealth.from_dict(server_data)
                self._servers[server.url] = server

            # Carregar estatísticas
            self._stats.update(data.get("stats", {}))

            logger.info(
                f"Estado carregado: {len(self._jobs)} jobs, "
                f"{len(self._servers)} servidores"
            )

        except Exception as e:
            logger.warning(f"Erro ao carregar estado: {e}")

    def _save_state(self):
        """Salva estado no arquivo."""
        try:
            state_path = Path(self.state_file)
            state_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "jobs": [job.to_dict() for job in self._jobs.values()],
                "servers": [server.to_dict() for server in self._servers.values()],
                "stats": self._stats,
                "saved_at": datetime.now().isoformat(),
            }

            # Escrever atomicamente
            tmp_path = state_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            tmp_path.replace(state_path)

        except Exception as e:
            logger.error(f"Erro ao salvar estado: {e}")

    # =========================================================================
    # Gerenciamento de Servidores
    # =========================================================================

    def register_servers(self, urls: List[str]):
        """Registra servidores para uso."""
        with self._lock:
            for url in urls:
                url = url.rstrip("/")
                if url not in self._servers:
                    self._servers[url] = ServerHealth(url=url)
                    logger.info(f"Servidor registrado: {url}")

            self._save_state()

    def get_healthy_servers(self) -> List[str]:
        """Retorna lista de servidores saudáveis e disponíveis."""
        with self._lock:
            return [
                url for url, health in self._servers.items()
                if health.is_available()
            ]

    def get_next_server(self) -> Optional[str]:
        """
        Retorna próximo servidor disponível usando Round Robin inteligente.

        Prioriza servidores com:
        1. Menos jobs na fila
        2. Menor tempo médio de processamento
        3. Mais workers disponíveis
        """
        with self._lock:
            available = self.get_healthy_servers()

            if not available:
                logger.warning("Nenhum servidor disponível!")
                return None

            if len(available) == 1:
                return available[0]

            # Calcular score para cada servidor (menor = melhor)
            def server_score(url: str) -> float:
                health = self._servers[url]
                score = 0.0

                # Penalizar por jobs na fila
                score += health.queue_length * 10

                # Penalizar por jobs ativos
                score += health.active_jobs * 5

                # Penalizar por tempo de processamento alto
                score += health.avg_processing_time * 0.5

                # Bonificar por workers disponíveis
                if health.total_workers > 0:
                    availability = health.available_workers / health.total_workers
                    score -= availability * 20

                return score

            # Ordenar por score
            available.sort(key=server_score)

            # Usar o melhor servidor
            best_server = available[0]
            logger.debug(f"Servidor selecionado: {best_server} (score: {server_score(best_server):.1f})")

            return best_server

    def update_server_health(self, url: str, queue_stats: dict):
        """Atualiza estatísticas de saúde de um servidor."""
        with self._lock:
            if url not in self._servers:
                self._servers[url] = ServerHealth(url=url)

            health = self._servers[url]
            health.queue_length = queue_stats.get("queueLength", 0)
            health.active_jobs = queue_stats.get("activeJobs", 0)
            health.available_workers = queue_stats.get("availableWorkers", 0)
            health.total_workers = queue_stats.get("totalWorkers", 0)
            health.avg_processing_time = queue_stats.get("averageProcessingTime", 0)
            health.last_check = datetime.now().isoformat()
            health.mark_success()

            self._save_state()

    def mark_server_failure(self, url: str, error: str = ""):
        """Marca falha em um servidor."""
        with self._lock:
            if url in self._servers:
                self._servers[url].mark_failure(error)
                self._save_state()

    def mark_server_success(self, url: str):
        """Marca sucesso em um servidor."""
        with self._lock:
            if url in self._servers:
                self._servers[url].mark_success()
                self._save_state()

    # =========================================================================
    # Gerenciamento de Jobs
    # =========================================================================

    def create_job(
        self,
        audio_path: str,
        language: str = "pt",
        priority: int = 0,
    ) -> Job:
        """
        Cria um novo job de transcrição.

        Args:
            audio_path: Caminho do arquivo de áudio
            language: Idioma para transcrição
            priority: Prioridade (maior = mais prioritário)

        Returns:
            Job criado
        """
        import uuid

        job = Job(
            id=str(uuid.uuid4()),
            audio_path=audio_path,
            language=language,
            priority=priority,
        )

        with self._lock:
            self._jobs[job.id] = job
            self._stats["total_jobs"] += 1
            self._save_state()

        logger.info(f"📋 Job criado: {job.id} para {Path(audio_path).name}")
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        """Retorna um job pelo ID."""
        with self._lock:
            return self._jobs.get(job_id)

    def update_job(self, job: Job):
        """Atualiza um job e persiste."""
        with self._lock:
            self._jobs[job.id] = job
            self._save_state()

    def mark_job_submitted(
        self,
        job_id: str,
        server_url: str,
        remote_job_id: str,
    ):
        """Marca job como enviado ao servidor."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.state = JobState.SUBMITTED.value
                job.server_url = server_url
                job.remote_job_id = remote_job_id
                job.submitted_at = datetime.now().isoformat()
                self._save_state()

                logger.info(
                    f"📤 Job {job_id[:8]} enviado para {server_url}, "
                    f"remote_id: {remote_job_id}"
                )

    def mark_job_processing(self, job_id: str):
        """Marca job como em processamento."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.state = JobState.PROCESSING.value
                self._save_state()

    def mark_job_completed(
        self,
        job_id: str,
        text: str,
        language: str,
        duration: float,
        processing_time: float,
    ):
        """Marca job como concluído."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.state = JobState.COMPLETED.value
                job.completed_at = datetime.now().isoformat()
                job.result_text = text
                job.result_language = language
                job.result_duration = duration
                job.processing_time = processing_time

                # Atualizar estatísticas
                self._stats["completed_jobs"] += 1
                self._stats["total_processing_time"] += processing_time

                # Marcar sucesso no servidor
                if job.server_url:
                    self.mark_server_success(job.server_url)

                self._save_state()

                logger.info(
                    f"✅ Job {job_id[:8]} concluído: {len(text)} chars, "
                    f"{processing_time:.1f}s"
                )

                # Callback
                if self._on_job_completed:
                    try:
                        self._on_job_completed(job)
                    except Exception as e:
                        logger.error(f"Erro no callback on_job_completed: {e}")

    def mark_job_failed(self, job_id: str, error: str, can_retry: bool = True):
        """Marca job como falho."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.last_error = error
                job.retry_count += 1

                if can_retry and job.can_retry():
                    job.state = JobState.RETRYING.value
                    # Backoff exponencial: 10s, 20s, 40s
                    delay = 10 * (2 ** (job.retry_count - 1))
                    job.next_retry_at = datetime.fromtimestamp(
                        time.time() + delay
                    ).isoformat()

                    self._stats["retried_jobs"] += 1
                    logger.warning(
                        f"⚠️ Job {job_id[:8]} falhou (tentativa {job.retry_count}), "
                        f"retry em {delay}s: {error}"
                    )
                else:
                    job.state = JobState.FAILED.value
                    self._stats["failed_jobs"] += 1
                    logger.error(f"❌ Job {job_id[:8]} falhou permanentemente: {error}")

                    # Callback
                    if self._on_job_failed:
                        try:
                            self._on_job_failed(job)
                        except Exception as e:
                            logger.error(f"Erro no callback on_job_failed: {e}")

                # Marcar falha no servidor
                if job.server_url:
                    self.mark_server_failure(job.server_url, error)

                self._save_state()

    def get_pending_jobs(self) -> List[Job]:
        """Retorna jobs pendentes de envio ou retry."""
        now = datetime.now()

        with self._lock:
            pending = []

            for job in self._jobs.values():
                if job.state == JobState.PENDING.value:
                    pending.append(job)

                elif job.state == JobState.RETRYING.value:
                    if job.next_retry_at:
                        retry_time = datetime.fromisoformat(job.next_retry_at)
                        if now >= retry_time:
                            pending.append(job)

            # Ordenar por prioridade e data de criação
            pending.sort(
                key=lambda j: (-j.priority, j.created_at)
            )

            return pending

    def get_in_progress_jobs(self) -> List[Job]:
        """Retorna jobs em andamento (submitted ou processing)."""
        with self._lock:
            return [
                job for job in self._jobs.values()
                if job.state in (JobState.SUBMITTED.value, JobState.PROCESSING.value)
            ]

    def cleanup_old_jobs(self, max_age_hours: int = 24):
        """Remove jobs completados ou falhos antigos."""
        cutoff = datetime.fromtimestamp(
            time.time() - max_age_hours * 3600
        )

        with self._lock:
            to_remove = []

            for job_id, job in self._jobs.items():
                if job.state in (JobState.COMPLETED.value, JobState.FAILED.value):
                    completed_at = (
                        datetime.fromisoformat(job.completed_at)
                        if job.completed_at else None
                    )

                    if completed_at and completed_at < cutoff:
                        to_remove.append(job_id)

            for job_id in to_remove:
                del self._jobs[job_id]

            if to_remove:
                logger.info(f"🧹 Removidos {len(to_remove)} jobs antigos")
                self._save_state()

    # =========================================================================
    # Polling Adaptativo
    # =========================================================================

    def calculate_poll_interval(self, server_url: str) -> float:
        """
        Calcula intervalo de polling adaptativo baseado na carga do servidor.

        Retorna intervalo em segundos.
        """
        with self._lock:
            health = self._servers.get(server_url)

            if not health:
                return 3.0  # Padrão

            # Base: 2 segundos
            interval = 2.0

            # Se fila grande, aumentar intervalo
            if health.queue_length > 10:
                interval += 2.0
            elif health.queue_length > 5:
                interval += 1.0

            # Se muitos jobs ativos, aumentar
            if health.active_jobs >= health.total_workers:
                interval += 2.0

            # Se tempo de processamento alto, aumentar
            if health.avg_processing_time > 60:
                interval += 3.0
            elif health.avg_processing_time > 30:
                interval += 1.5

            # Limitar entre 2 e 15 segundos
            return max(2.0, min(interval, 15.0))

    # =========================================================================
    # Background Workers
    # =========================================================================

    def start(self):
        """Inicia workers de background."""
        if self._running:
            return

        self._running = True

        # Health check thread
        self._health_thread = threading.Thread(
            target=self._health_check_loop,
            daemon=True,
            name="JobManager-HealthCheck",
        )
        self._health_thread.start()

        logger.info("🚀 JobManager iniciado")

    def stop(self):
        """Para workers de background."""
        self._running = False

        if self._health_thread:
            self._health_thread.join(timeout=5)

        self._save_state()
        logger.info("⏹️ JobManager parado")

    def _health_check_loop(self):
        """Loop de verificação de saúde dos servidores."""
        import httpx

        while self._running:
            try:
                for url in list(self._servers.keys()):
                    if not self._running:
                        break

                    try:
                        with httpx.Client(timeout=10.0) as client:
                            # Verificar saúde
                            response = client.get(f"{url}/health")
                            if response.status_code != 200:
                                self.mark_server_failure(url, f"HTTP {response.status_code}")
                                continue

                            # Obter estatísticas da fila
                            try:
                                queue_response = client.get(f"{url}/queue-estimate")
                                if queue_response.status_code == 200:
                                    queue_stats = queue_response.json()
                                    self.update_server_health(url, queue_stats)
                            except Exception:
                                pass  # Queue stats são opcionais

                            self.mark_server_success(url)

                    except Exception as e:
                        self.mark_server_failure(url, str(e))

            except Exception as e:
                logger.error(f"Erro no health check: {e}")

            # Aguardar próximo check
            time.sleep(self.health_check_interval)

    # =========================================================================
    # Propriedades e Status
    # =========================================================================

    @property
    def stats(self) -> dict:
        """Retorna estatísticas do JobManager."""
        with self._lock:
            pending = len(self.get_pending_jobs())
            in_progress = len(self.get_in_progress_jobs())
            healthy_servers = len(self.get_healthy_servers())

            return {
                **self._stats,
                "pending_jobs": pending,
                "in_progress_jobs": in_progress,
                "total_servers": len(self._servers),
                "healthy_servers": healthy_servers,
                "avg_processing_time": (
                    self._stats["total_processing_time"] / self._stats["completed_jobs"]
                    if self._stats["completed_jobs"] > 0 else 0
                ),
            }

    @property
    def server_status(self) -> List[dict]:
        """Retorna status de todos os servidores."""
        with self._lock:
            return [
                {
                    "url": url,
                    "healthy": health.is_healthy,
                    "available": health.is_available(),
                    "queue_length": health.queue_length,
                    "active_jobs": health.active_jobs,
                    "available_workers": health.available_workers,
                    "total_workers": health.total_workers,
                    "avg_processing_time": health.avg_processing_time,
                    "consecutive_failures": health.consecutive_failures,
                    "last_check": health.last_check,
                }
                for url, health in self._servers.items()
            ]


# =========================================================================
# Instância Global
# =========================================================================

_global_job_manager: Optional[JobManager] = None
_global_lock = threading.Lock()


def get_job_manager() -> JobManager:
    """Obtém instância global do JobManager."""
    global _global_job_manager

    with _global_lock:
        if _global_job_manager is None:
            _global_job_manager = JobManager()
            _global_job_manager.start()

        return _global_job_manager


def shutdown_job_manager():
    """Desliga o JobManager global."""
    global _global_job_manager

    with _global_lock:
        if _global_job_manager:
            _global_job_manager.stop()
            _global_job_manager = None
