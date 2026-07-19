import json
import base64
from typing import Any, Dict, Optional, AsyncIterator
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointTuple, CheckpointMetadata, SerializerProtocol
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from contextlib import contextmanager

class DBCheckpointSaver(BaseCheckpointSaver):
    """
    A persistent checkpointer that saves LangGraph states in the database.
    Uses the AI_SESSAO_CHAT table (PostgreSQL).
    """

    def __init__(
        self,
        get_connection_func,
        serde: Optional[SerializerProtocol] = None,
    ) -> None:
        super().__init__(serde=serde or JsonPlusSerializer())
        self.get_connection = get_connection_func

    @contextmanager
    def _get_cursor(self):
        conn = self.get_connection()
        if not conn:
            raise Exception("Failed to get database connection.")
        try:
            cursor = conn.cursor()
            yield cursor, conn
        finally:
            cursor.close()
            conn.close()

    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        """Fetch a checkpoint tuple from the database."""
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = config["configurable"].get("checkpoint_id")

        with self._get_cursor() as (cursor, conn):
            if checkpoint_id:
                query = """
                    SELECT CHECKPOINT_DATA, METADATA
                    FROM AI_SESSAO_CHAT
                    WHERE SESSION_ID = %(session_id)s AND CHECKPOINT_ID = %(checkpoint_id)s
                """
                cursor.execute(query, {"session_id": thread_id, "checkpoint_id": checkpoint_id})
            else:
                query = """
                    SELECT CHECKPOINT_DATA, METADATA, CHECKPOINT_ID
                    FROM AI_SESSAO_CHAT
                    WHERE SESSION_ID = %(session_id)s
                    ORDER BY CREATED_AT DESC
                    LIMIT 1
                """
                cursor.execute(query, {"session_id": thread_id})

            row = cursor.fetchone()
            if not row:
                return None

            checkpoint_data = row[0]
            metadata_data = row[1] or "{}"

            try:
                cp_list = json.loads(checkpoint_data)
                cp_tuple = (cp_list[0], base64.b64decode(cp_list[1]))
            except Exception:
                cp_tuple = ("json", checkpoint_data.encode("utf-8"))
            checkpoint = self.serde.loads_typed(cp_tuple)

            try:
                md_list = json.loads(metadata_data)
                md_tuple = (md_list[0], base64.b64decode(md_list[1]))
            except Exception:
                md_tuple = ("json", metadata_data.encode("utf-8"))
            metadata = self.serde.loads_typed(md_tuple)

            # Extract checkpoint_id if fetching latest
            if not checkpoint_id:
                checkpoint_id = row[2]

            return CheckpointTuple(
                config={"configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id}},
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=None,
            )

    def list(self, config: Optional[RunnableConfig], *, filter: Optional[Dict[str, Any]] = None, before: Optional[RunnableConfig] = None, limit: Optional[int] = None) -> AsyncIterator[CheckpointTuple]:
        """List checkpoints (sync wrapper implementation to satisfy interface, since we use sync db)."""
        raise NotImplementedError("List not implemented yet for DBCheckpointer")

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, str | float | int]
    ) -> RunnableConfig:
        """Save a checkpoint to the database (upsert via ON CONFLICT)."""
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = checkpoint["id"]

        cp_type, cp_bytes = self.serde.dumps_typed(checkpoint)
        checkpoint_data_str = json.dumps([cp_type, base64.b64encode(cp_bytes).decode('ascii')])

        md_type, md_bytes = self.serde.dumps_typed(metadata)
        metadata_str = json.dumps([md_type, base64.b64encode(md_bytes).decode('ascii')])

        with self._get_cursor() as (cursor, conn):
            query = """
                INSERT INTO AI_SESSAO_CHAT (SESSION_ID, CHECKPOINT_ID, CHECKPOINT_DATA, METADATA)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (SESSION_ID, CHECKPOINT_ID)
                DO UPDATE SET CHECKPOINT_DATA = EXCLUDED.CHECKPOINT_DATA,
                              METADATA        = EXCLUDED.METADATA
            """
            cursor.execute(query, (thread_id, checkpoint_id, checkpoint_data_str, metadata_str))
            conn.commit()

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_namespace": config["configurable"].get("checkpoint_namespace", ""),
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(self, config, writes, task_id, task_path=""):
        """
        Stub implementando o método obrigatório no LangGraph 0.2+.
        Usado para salvar writes pendentes em casos de interrupt/resume (human-in-the-loop).
        """
        pass
