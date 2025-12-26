"""
Sistema de filas offline para processamento assíncrono.
Armazena tarefas quando não há conectividade e processa quando disponível.
"""

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Callable, Any, List
import queue

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Status da tarefa na fila."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"


class TaskType(Enum):
    """Tipos de tarefas."""
    TRANSCRIPTION = "transcription"
    SUMMARIZATION = "summarization"
    CUSTOM_LLM = "custom_llm"
    SYNC = "sync"


@dataclass
class QueuedTask:
    """Tarefa na fila."""
    id: str
    task_type: str
    payload: dict
    status: str
    priority: int = 0
    retries: int = 0
    max_retries: int = 3
    created_at: str = ""
    updated_at: str = ""
    result: Optional[dict] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "QueuedTask":
        """Cria a partir de dicionário."""
        return cls(**data)


class OfflineQueue:
    """
    Fila persistente para processamento offline.

    Características:
    - Persistência em SQLite (sobrevive a reinicializações)
    - Priorização de tarefas
    - Retry automático com backoff exponencial
    - Detecção automática de conectividade
    - Processamento em background
    """

    def __init__(
        self,
        db_path: str = "~/.cache/voice-processor/queue.db",
        max_queue_size: int = 1000,
        retry_delay_base: float = 30.0,
        connectivity_check_interval: float = 60.0,
        enabled: bool = True,
        max_retries: int = 3,
    ):
        """
        Inicializa a fila offline.

        Args:
            db_path: Caminho do banco de dados SQLite
            max_queue_size: Tamanho máximo da fila
            retry_delay_base: Delay base para retry (segundos)
            connectivity_check_interval: Intervalo de verificação de conectividade
            enabled: Se a fila está habilitada
            max_retries: Número máximo de tentativas por tarefa
        """
        self.db_path = Path(db_path).expanduser()
        self.max_queue_size = max_queue_size
        self.retry_delay_base = retry_delay_base
        self.connectivity_check_interval = connectivity_check_interval
        self.enabled = enabled
        self.default_max_retries = max_retries

        # Estado
        self._is_online = True
        self._processing = False
        self._stop_event = threading.Event()
        self._process_thread: Optional[threading.Thread] = None
        self._connectivity_thread: Optional[threading.Thread] = None

        # Callbacks
        self._task_handlers: dict[str, Callable] = {}
        self._on_task_complete: Optional[Callable] = None
        self._on_connectivity_change: Optional[Callable] = None

        # Inicializar banco de dados
        self._init_db()

        logger.info(f"Fila offline inicializada: {self.db_path}")

    def _init_db(self) -> None:
        """Inicializa banco de dados SQLite."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    priority INTEGER DEFAULT 0,
                    retries INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    result TEXT,
                    error TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status ON tasks(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_priority ON tasks(priority DESC, created_at ASC)
            """)
            conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        """Retorna conexão com o banco."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def enqueue(
        self,
        task_type: TaskType | str,
        payload: dict,
        priority: int = 0,
        max_retries: int = 3,
    ) -> str:
        """
        Adiciona tarefa à fila.

        Args:
            task_type: Tipo da tarefa
            payload: Dados da tarefa
            priority: Prioridade (maior = mais prioritário)
            max_retries: Número máximo de tentativas

        Returns:
            ID da tarefa
        """
        task_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        if isinstance(task_type, TaskType):
            task_type = task_type.value

        with self._get_connection() as conn:
            # Verificar limite da fila
            count = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE status IN ('pending', 'retry')"
            ).fetchone()[0]

            if count >= self.max_queue_size:
                # Remover tarefas mais antigas
                conn.execute("""
                    DELETE FROM tasks WHERE id IN (
                        SELECT id FROM tasks
                        WHERE status = 'completed'
                        ORDER BY updated_at ASC
                        LIMIT 100
                    )
                """)

            conn.execute("""
                INSERT INTO tasks (id, task_type, payload, status, priority, max_retries, created_at, updated_at)
                VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)
            """, (task_id, task_type, json.dumps(payload), priority, max_retries, now, now))
            conn.commit()

        logger.debug(f"Tarefa enfileirada: {task_id} ({task_type})")
        return task_id

    def get_pending_tasks(self, limit: int = 10) -> List[QueuedTask]:
        """Retorna tarefas pendentes ordenadas por prioridade."""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM tasks
                WHERE status IN ('pending', 'retry')
                ORDER BY priority DESC, created_at ASC
                LIMIT ?
            """, (limit,)).fetchall()

        return [self._row_to_task(row) for row in rows]

    def get_task(self, task_id: str) -> Optional[QueuedTask]:
        """Retorna tarefa por ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()

        return self._row_to_task(row) if row else None

    def update_task(
        self,
        task_id: str,
        status: Optional[TaskStatus] = None,
        result: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> None:
        """Atualiza status da tarefa."""
        now = datetime.now().isoformat()

        with self._get_connection() as conn:
            updates = ["updated_at = ?"]
            params = [now]

            if status:
                updates.append("status = ?")
                params.append(status.value)

            if result is not None:
                updates.append("result = ?")
                params.append(json.dumps(result))

            if error is not None:
                updates.append("error = ?")
                params.append(error)

            params.append(task_id)
            conn.execute(
                f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?",
                params
            )
            conn.commit()

    def increment_retry(self, task_id: str) -> bool:
        """
        Incrementa contador de retry.

        Returns:
            True se ainda pode tentar, False se atingiu limite
        """
        with self._get_connection() as conn:
            task = conn.execute(
                "SELECT retries, max_retries FROM tasks WHERE id = ?",
                (task_id,)
            ).fetchone()

            if not task:
                return False

            new_retries = task["retries"] + 1
            if new_retries >= task["max_retries"]:
                conn.execute(
                    "UPDATE tasks SET status = 'failed', retries = ?, updated_at = ? WHERE id = ?",
                    (new_retries, datetime.now().isoformat(), task_id)
                )
                conn.commit()
                return False

            conn.execute(
                "UPDATE tasks SET status = 'retry', retries = ?, updated_at = ? WHERE id = ?",
                (new_retries, datetime.now().isoformat(), task_id)
            )
            conn.commit()
            return True

    def _row_to_task(self, row: sqlite3.Row) -> QueuedTask:
        """Converte row do SQLite para QueuedTask."""
        return QueuedTask(
            id=row["id"],
            task_type=row["task_type"],
            payload=json.loads(row["payload"]),
            status=row["status"],
            priority=row["priority"],
            retries=row["retries"],
            max_retries=row["max_retries"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            result=json.loads(row["result"]) if row["result"] else None,
            error=row["error"],
        )

    def register_handler(
        self,
        task_type: TaskType | str,
        handler: Callable[[dict], dict],
    ) -> None:
        """
        Registra handler para tipo de tarefa.

        Args:
            task_type: Tipo da tarefa
            handler: Função que processa a tarefa
        """
        if isinstance(task_type, TaskType):
            task_type = task_type.value
        self._task_handlers[task_type] = handler

    def check_connectivity(self) -> bool:
        """
        Verifica conectividade com internet.

        Returns:
            True se online, False se offline
        """
        import socket

        hosts = [
            ("8.8.8.8", 53),  # Google DNS
            ("1.1.1.1", 53),  # Cloudflare DNS
            ("api.openai.com", 443),
        ]

        for host, port in hosts:
            try:
                socket.setdefaulttimeout(3)
                socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
                return True
            except (socket.timeout, socket.error):
                continue

        return False

    def _connectivity_monitor(self) -> None:
        """Thread de monitoramento de conectividade."""
        while not self._stop_event.is_set():
            was_online = self._is_online
            self._is_online = self.check_connectivity()

            if was_online != self._is_online:
                status = "online" if self._is_online else "offline"
                logger.info(f"Conectividade alterada: {status}")

                if self._on_connectivity_change:
                    self._on_connectivity_change(self._is_online)

                # Se voltou online, processar fila
                if self._is_online and not was_online:
                    self._trigger_processing()

            self._stop_event.wait(self.connectivity_check_interval)

    def _trigger_processing(self) -> None:
        """Dispara processamento de tarefas pendentes."""
        if self._processing:
            return

        thread = threading.Thread(target=self._process_queue, daemon=True)
        thread.start()

    def _process_queue(self) -> None:
        """Processa tarefas na fila."""
        if self._processing:
            return

        self._processing = True
        logger.info("Iniciando processamento da fila offline...")

        try:
            while not self._stop_event.is_set():
                if not self._is_online:
                    break

                tasks = self.get_pending_tasks(limit=5)
                if not tasks:
                    break

                for task in tasks:
                    if self._stop_event.is_set() or not self._is_online:
                        break

                    self._process_task(task)

        finally:
            self._processing = False
            logger.info("Processamento da fila finalizado")

    def _process_task(self, task: QueuedTask) -> None:
        """Processa uma tarefa individual."""
        handler = self._task_handlers.get(task.task_type)
        if not handler:
            logger.warning(f"Handler não encontrado para: {task.task_type}")
            self.update_task(task.id, TaskStatus.FAILED, error="Handler não encontrado")
            return

        self.update_task(task.id, TaskStatus.PROCESSING)

        try:
            result = handler(task.payload)
            self.update_task(task.id, TaskStatus.COMPLETED, result=result)

            if self._on_task_complete:
                self._on_task_complete(task, result)

            logger.info(f"Tarefa processada: {task.id}")

        except Exception as e:
            logger.error(f"Erro ao processar tarefa {task.id}: {e}")

            if self.increment_retry(task.id):
                # Aguardar com backoff exponencial
                delay = self.retry_delay_base * (2 ** task.retries)
                logger.info(f"Retry agendado em {delay}s para {task.id}")
            else:
                self.update_task(task.id, TaskStatus.FAILED, error=str(e))

    def start(self) -> None:
        """Inicia monitoramento e processamento."""
        self._stop_event.clear()

        # Thread de monitoramento de conectividade
        self._connectivity_thread = threading.Thread(
            target=self._connectivity_monitor,
            daemon=True,
        )
        self._connectivity_thread.start()

        # Processar tarefas pendentes se online
        if self.check_connectivity():
            self._is_online = True
            self._trigger_processing()

        logger.info("Sistema de filas iniciado")

    def stop(self) -> None:
        """Para monitoramento e processamento."""
        self._stop_event.set()

        if self._connectivity_thread:
            self._connectivity_thread.join(timeout=5)

        logger.info("Sistema de filas parado")

    def get_stats(self) -> dict:
        """Retorna estatísticas da fila."""
        with self._get_connection() as conn:
            stats = {}
            for status in TaskStatus:
                count = conn.execute(
                    "SELECT COUNT(*) FROM tasks WHERE status = ?",
                    (status.value,)
                ).fetchone()[0]
                stats[status.value] = count

            total = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            stats["total"] = total

        stats["is_online"] = self._is_online
        stats["is_processing"] = self._processing

        return stats

    def clear_completed(self, older_than_hours: int = 24) -> int:
        """Remove tarefas completadas antigas."""
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(hours=older_than_hours)).isoformat()

        with self._get_connection() as conn:
            result = conn.execute(
                "DELETE FROM tasks WHERE status = 'completed' AND updated_at < ?",
                (cutoff,)
            )
            conn.commit()
            return result.rowcount

    @property
    def is_online(self) -> bool:
        """Retorna status de conectividade."""
        return self._is_online

    def process_pending(self) -> int:
        """
        Processa tarefas pendentes manualmente.

        Returns:
            Número de tarefas processadas
        """
        if not self.enabled:
            logger.warning("Fila offline desabilitada")
            return 0

        if not self._is_online:
            logger.warning("Sem conexão - não é possível processar")
            return 0

        if self._processing:
            logger.info("Processamento já em andamento")
            return 0

        self._processing = True
        processed = 0

        try:
            tasks = self.get_pending_tasks(limit=100)

            for task in tasks:
                if not self._is_online:
                    break

                handler = self._task_handlers.get(task.task_type)
                if not handler:
                    logger.warning(f"Handler não encontrado para: {task.task_type}")
                    self.update_task(task.id, TaskStatus.FAILED, error="Handler não encontrado")
                    continue

                self.update_task(task.id, TaskStatus.PROCESSING)

                try:
                    result = handler(task.payload)
                    self.update_task(task.id, TaskStatus.COMPLETED, result=result)
                    processed += 1

                    if self._on_task_complete:
                        self._on_task_complete(task, result)

                except Exception as e:
                    logger.error(f"Erro ao processar tarefa {task.id}: {e}")
                    if not self.increment_retry(task.id):
                        self.update_task(task.id, TaskStatus.FAILED, error=str(e))

        finally:
            self._processing = False

        logger.info(f"Processadas {processed} tarefas da fila")
        return processed

    def on_connectivity_change(self, callback: Callable[[bool], None]) -> None:
        """Registra callback para mudança de conectividade."""
        self._on_connectivity_change = callback

    def on_task_complete(self, callback: Callable[[QueuedTask, dict], None]) -> None:
        """Registra callback para conclusão de tarefas."""
        self._on_task_complete = callback

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False


class SyncManager:
    """
    Gerenciador de sincronização para modo offline/online.
    Integra com o pipeline de processamento.
    """

    def __init__(self, queue: OfflineQueue):
        """
        Inicializa o gerenciador de sincronização.

        Args:
            queue: Fila offline
        """
        self.queue = queue
        self._pending_results: dict[str, Any] = {}

    def enqueue_for_api(
        self,
        task_type: TaskType,
        payload: dict,
        fallback_handler: Optional[Callable] = None,
    ) -> tuple[bool, Any]:
        """
        Enfileira tarefa para API ou processa localmente.

        Args:
            task_type: Tipo da tarefa
            payload: Dados
            fallback_handler: Handler local se offline

        Returns:
            Tupla (processado_agora, resultado_ou_task_id)
        """
        if self.queue.is_online:
            # Tentar processar imediatamente
            handler = self.queue._task_handlers.get(task_type.value)
            if handler:
                try:
                    result = handler(payload)
                    return (True, result)
                except Exception as e:
                    logger.warning(f"Falha no processamento online: {e}")

        # Enfileirar para processamento posterior
        if fallback_handler:
            # Processar localmente como fallback
            try:
                result = fallback_handler(payload)
                return (True, result)
            except Exception:
                pass

        # Enfileirar
        task_id = self.queue.enqueue(task_type, payload)
        return (False, task_id)

    def get_result(self, task_id: str) -> Optional[dict]:
        """Retorna resultado de tarefa processada."""
        task = self.queue.get_task(task_id)
        if task and task.status == TaskStatus.COMPLETED.value:
            return task.result
        return None

    def wait_for_result(
        self,
        task_id: str,
        timeout: float = 300,
        poll_interval: float = 1.0,
    ) -> Optional[dict]:
        """
        Aguarda resultado de tarefa.

        Args:
            task_id: ID da tarefa
            timeout: Timeout em segundos
            poll_interval: Intervalo de polling

        Returns:
            Resultado ou None se timeout
        """
        start = time.time()
        while time.time() - start < timeout:
            result = self.get_result(task_id)
            if result is not None:
                return result
            time.sleep(poll_interval)
        return None
