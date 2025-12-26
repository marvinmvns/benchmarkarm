"""
Armazenamento persistente de transcrições.

Utiliza SQLite para metadados e permite consolidação diária em JSON.
"""

import json
import sqlite3
import uuid
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
import threading
import logging

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionRecord:
    """Registro de uma transcrição."""
    id: str
    timestamp: datetime
    duration_seconds: float
    text: str
    summary: Optional[str] = None
    audio_file: Optional[str] = None
    language: str = "pt"
    processed_by: str = "local"  # 'local', 'whisperapi', 'openai'
    llm_result: Optional[str] = None
    created_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário serializável."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "duration_seconds": self.duration_seconds,
            "text": self.text,
            "summary": self.summary,
            "audio_file": self.audio_file,
            "language": self.language,
            "processed_by": self.processed_by,
            "llm_result": self.llm_result,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TranscriptionStore:
    """
    Gerenciador de armazenamento de transcrições.
    
    Funcionalidades:
    - Salvar transcrições em SQLite
    - Listar com paginação e filtros
    - Buscar por texto
    - Consolidação diária em JSON
    - Processar com LLM
    """
    
    def __init__(self, db_path: Optional[str] = None, consolidation_dir: Optional[str] = None):
        """
        Inicializa o store.
        
        Args:
            db_path: Caminho do banco SQLite (padrão: ~/.cache/voice-processor/transcriptions.db)
            consolidation_dir: Diretório para arquivos consolidados diários
        """
        if db_path is None:
            cache_dir = Path.home() / ".cache" / "voice-processor"
            cache_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(cache_dir / "transcriptions.db")
        
        if consolidation_dir is None:
            consolidation_dir = str(Path.home() / "audio-recordings" / "daily")
        
        self.db_path = db_path
        self.consolidation_dir = Path(consolidation_dir)
        self.consolidation_dir.mkdir(parents=True, exist_ok=True)
        
        self._lock = threading.Lock()
        self._init_db()
        
        logger.info(f"TranscriptionStore inicializado: {db_path}")
    
    def _init_db(self):
        """Inicializa o banco de dados."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transcriptions (
                    id TEXT PRIMARY KEY,
                    timestamp DATETIME NOT NULL,
                    duration_seconds REAL,
                    text TEXT,
                    summary TEXT,
                    audio_file TEXT,
                    language TEXT DEFAULT 'pt',
                    processed_by TEXT DEFAULT 'local',
                    llm_result TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON transcriptions(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON transcriptions(date(timestamp))")
            conn.commit()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Obtém conexão com o banco."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def save(self, record: TranscriptionRecord) -> str:
        """
        Salva uma transcrição.

        Args:
            record: Registro de transcrição

        Returns:
            ID da transcrição salva
        """
        with self._lock:
            with self._get_connection() as conn:
                if not record.id:
                    record.id = str(uuid.uuid4())
                if not record.created_at:
                    record.created_at = datetime.now()

                conn.execute("""
                    INSERT OR REPLACE INTO transcriptions
                    (id, timestamp, duration_seconds, text, summary, audio_file,
                     language, processed_by, llm_result, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record.id,
                    record.timestamp.isoformat() if record.timestamp else None,
                    record.duration_seconds,
                    record.text,
                    record.summary,
                    record.audio_file,
                    record.language,
                    record.processed_by,
                    record.llm_result,
                    record.created_at.isoformat() if record.created_at else None,
                ))
                conn.commit()

                logger.debug(f"Transcrição salva: {record.id}")

        # Adicionar ao arquivo TXT diário (fora do lock do SQLite)
        try:
            self.append_to_daily_txt(record)
        except Exception as e:
            logger.warning(f"Erro ao adicionar ao TXT diário: {e}")

        return record.id

    def append_to_daily_txt(self, record: TranscriptionRecord) -> str:
        """
        Adiciona transcrição ao arquivo TXT diário, mantendo ordem cronológica.

        Arquivo: DDMMYYYY.txt (ex: 25122025.txt)
        Local: ~/audio-recordings/daily/

        As transcrições são ordenadas pelo timestamp do áudio original,
        não pela hora de processamento. Isso garante que reprocessamentos
        fiquem na posição temporal correta.

        Args:
            record: Registro de transcrição

        Returns:
            Caminho do arquivo TXT
        """
        import re

        # Determinar a data (usa timestamp do record ou data atual)
        if record.timestamp:
            target_date = record.timestamp.date()
            record_ts = record.timestamp
        else:
            target_date = date.today()
            record_ts = datetime.now()

        # Nome do arquivo no formato DDMMYYYY.txt
        filename = target_date.strftime("%d%m%Y") + ".txt"
        filepath = self.consolidation_dir / filename

        # Criar nova entrada
        new_entry = self._format_daily_entry(record, record_ts)

        # Ler entradas existentes
        existing_entries = []
        if filepath.exists():
            existing_entries = self._parse_daily_entries(filepath)

        # Verificar se já existe entrada com mesmo ID (evitar duplicatas)
        existing_entries = [e for e in existing_entries if e.get("id") != record.id]

        # Adicionar nova entrada
        existing_entries.append({
            "id": record.id,
            "timestamp": record_ts,
            "content": new_entry,
        })

        # Ordenar por timestamp (mais antigo primeiro)
        existing_entries.sort(key=lambda x: x["timestamp"])

        # Reescrever arquivo ordenado
        with open(filepath, "w", encoding="utf-8") as f:
            for entry in existing_entries:
                f.write(entry["content"])

        logger.debug(f"Transcrição adicionada ao TXT diário (ordenado): {filepath}")
        return str(filepath)

    def _format_daily_entry(self, record: TranscriptionRecord, timestamp: datetime) -> str:
        """Formata uma entrada para o arquivo TXT diário."""
        time_str = timestamp.strftime("%H:%M:%S")
        iso_str = timestamp.isoformat()
        duration_str = f"{record.duration_seconds:.1f}s" if record.duration_seconds else "N/A"

        entry_lines = [
            "=" * 80,
            f"[{time_str}] @{iso_str} | Duração: {duration_str} | {record.processed_by}",
            f"# ID: {record.id}",
            "-" * 80,
            record.text.strip() if record.text else "(sem texto)",
        ]

        if record.summary:
            entry_lines.extend([
                "",
                ">>> Resumo:",
                record.summary.strip(),
            ])

        entry_lines.append("")
        return "\n".join(entry_lines) + "\n"

    def _parse_daily_entries(self, filepath: Path) -> List[Dict[str, Any]]:
        """Parseia entradas existentes de um arquivo TXT diário."""
        import re

        entries = []
        content = filepath.read_text(encoding="utf-8")

        # Dividir por separador de entrada
        raw_entries = content.split("=" * 80)

        for raw in raw_entries:
            raw = raw.strip()
            if not raw:
                continue

            # Extrair timestamp ISO do formato: [HH:MM:SS] @2025-12-25T14:30:00 | ...
            ts_match = re.search(r"@(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", raw)
            id_match = re.search(r"# ID: ([a-f0-9-]+)", raw)

            if ts_match:
                try:
                    ts = datetime.fromisoformat(ts_match.group(1))
                    entry_id = id_match.group(1) if id_match else str(uuid.uuid4())
                    entries.append({
                        "id": entry_id,
                        "timestamp": ts,
                        "content": "=" * 80 + "\n" + raw + "\n",
                    })
                except ValueError:
                    # Timestamp inválido, manter entrada com timestamp antigo
                    entries.append({
                        "id": str(uuid.uuid4()),
                        "timestamp": datetime.min,
                        "content": "=" * 80 + "\n" + raw + "\n",
                    })
            else:
                # Entrada antiga sem timestamp ISO, tentar extrair hora
                time_match = re.search(r"\[(\d{2}:\d{2}:\d{2})\]", raw)
                if time_match:
                    try:
                        # Usar data do arquivo + hora extraída
                        date_match = re.search(r"(\d{2})(\d{2})(\d{4})", filepath.stem)
                        if date_match:
                            d, m, y = date_match.groups()
                            h, mi, s = time_match.group(1).split(":")
                            ts = datetime(int(y), int(m), int(d), int(h), int(mi), int(s))
                        else:
                            ts = datetime.now().replace(
                                hour=int(time_match.group(1).split(":")[0]),
                                minute=int(time_match.group(1).split(":")[1]),
                                second=int(time_match.group(1).split(":")[2])
                            )
                        entries.append({
                            "id": str(uuid.uuid4()),
                            "timestamp": ts,
                            "content": "=" * 80 + "\n" + raw + "\n",
                        })
                    except (ValueError, IndexError):
                        entries.append({
                            "id": str(uuid.uuid4()),
                            "timestamp": datetime.min,
                            "content": "=" * 80 + "\n" + raw + "\n",
                        })

        return entries
    
    def get(self, id: str) -> Optional[TranscriptionRecord]:
        """Obtém transcrição por ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM transcriptions WHERE id = ?", (id,)
            ).fetchone()
            
            if row:
                return self._row_to_record(row)
            return None
    
    def list(
        self,
        limit: int = 50,
        offset: int = 0,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        order: str = "DESC",
    ) -> List[TranscriptionRecord]:
        """
        Lista transcrições com paginação.
        
        Args:
            limit: Número máximo de resultados
            offset: Offset para paginação
            date_from: Data inicial (inclusive)
            date_to: Data final (inclusive)
            order: 'ASC' ou 'DESC'
            
        Returns:
            Lista de transcrições
        """
        query = "SELECT * FROM transcriptions WHERE 1=1"
        params = []
        
        if date_from:
            query += " AND date(timestamp) >= ?"
            params.append(date_from.isoformat())
        
        if date_to:
            query += " AND date(timestamp) <= ?"
            params.append(date_to.isoformat())
        
        query += f" ORDER BY timestamp {order} LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_record(row) for row in rows]
    
    def search(self, query: str, limit: int = 50) -> List[TranscriptionRecord]:
        """
        Busca transcrições por texto.
        
        Args:
            query: Texto a buscar
            limit: Número máximo de resultados
            
        Returns:
            Lista de transcrições que contêm o texto
        """
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM transcriptions 
                WHERE text LIKE ? OR summary LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (f"%{query}%", f"%{query}%", limit)).fetchall()
            
            return [self._row_to_record(row) for row in rows]
    
    def get_by_date(self, target_date: date) -> List[TranscriptionRecord]:
        """
        Obtém todas transcrições de um dia específico.
        
        Args:
            target_date: Data alvo
            
        Returns:
            Lista ordenada por timestamp
        """
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM transcriptions 
                WHERE date(timestamp) = ?
                ORDER BY timestamp ASC
            """, (target_date.isoformat(),)).fetchall()
            
            return [self._row_to_record(row) for row in rows]
    
    def count(self, date_from: Optional[date] = None, date_to: Optional[date] = None) -> int:
        """Conta total de transcrições."""
        query = "SELECT COUNT(*) FROM transcriptions WHERE 1=1"
        params = []
        
        if date_from:
            query += " AND date(timestamp) >= ?"
            params.append(date_from.isoformat())
        
        if date_to:
            query += " AND date(timestamp) <= ?"
            params.append(date_to.isoformat())
        
        with self._get_connection() as conn:
            return conn.execute(query, params).fetchone()[0]
    
    def delete(self, id: str) -> bool:
        """Remove transcrição por ID."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute("DELETE FROM transcriptions WHERE id = ?", (id,))
                conn.commit()
                deleted = cursor.rowcount > 0
                if deleted:
                    logger.info(f"Transcrição removida: {id}")
                return deleted
    
    def update_llm_result(self, id: str, llm_result: str) -> bool:
        """Atualiza resultado do processamento LLM."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "UPDATE transcriptions SET llm_result = ? WHERE id = ?",
                    (llm_result, id)
                )
                conn.commit()
                return cursor.rowcount > 0
    
    def consolidate_daily(self, target_date: Optional[date] = None) -> Optional[str]:
        """
        Consolida transcrições de um dia em arquivo JSON.
        
        Args:
            target_date: Data a consolidar (padrão: ontem)
            
        Returns:
            Caminho do arquivo gerado ou None se não houver transcrições
        """
        if target_date is None:
            target_date = date.today() - timedelta(days=1)
        
        records = self.get_by_date(target_date)
        
        if not records:
            logger.info(f"Nenhuma transcrição para consolidar em {target_date}")
            return None
        
        # Preparar dados consolidados
        consolidated = {
            "date": target_date.isoformat(),
            "total_transcriptions": len(records),
            "total_duration_seconds": sum(r.duration_seconds or 0 for r in records),
            "transcriptions": [r.to_dict() for r in records],
            "consolidated_at": datetime.now().isoformat(),
        }
        
        # Gerar texto completo do dia (timeline)
        timeline_text = []
        for r in records:
            time_str = r.timestamp.strftime("%H:%M:%S") if r.timestamp else "??:??:??"
            timeline_text.append(f"[{time_str}] {r.text}")
        
        consolidated["full_text"] = "\n\n".join(timeline_text)
        
        # Salvar arquivo
        filename = f"transcriptions_{target_date.isoformat()}.json"
        filepath = self.consolidation_dir / filename
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(consolidated, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ Consolidação concluída: {filepath} ({len(records)} transcrições)")
        return str(filepath)
    
    def get_daily_consolidated(self, target_date: date) -> Optional[Dict[str, Any]]:
        """
        Obtém arquivo consolidado de um dia.
        
        Args:
            target_date: Data alvo
            
        Returns:
            Dados consolidados ou None se não existir
        """
        filename = f"transcriptions_{target_date.isoformat()}.json"
        filepath = self.consolidation_dir / filename
        
        if not filepath.exists():
            # Tentar consolidar agora
            self.consolidate_daily(target_date)
        
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        
        return None
    
    def _row_to_record(self, row: sqlite3.Row) -> TranscriptionRecord:
        """Converte row do SQLite para TranscriptionRecord."""
        return TranscriptionRecord(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else None,
            duration_seconds=row["duration_seconds"],
            text=row["text"],
            summary=row["summary"],
            audio_file=row["audio_file"],
            language=row["language"] or "pt",
            processed_by=row["processed_by"] or "local",
            llm_result=row["llm_result"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        )


# Instância global (singleton)
_store_instance: Optional[TranscriptionStore] = None


def get_transcription_store() -> TranscriptionStore:
    """Obtém instância global do TranscriptionStore."""
    global _store_instance
    if _store_instance is None:
        _store_instance = TranscriptionStore()
    return _store_instance
