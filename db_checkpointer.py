import json
from typing import Any, Dict, Optional, Tuple, AsyncIterator, Tuple, List, Sequence
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointTuple, CheckpointMetadata, SerializerProtocol
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
import oracledb
from contextlib import contextmanager

class DBCheckpointSaver(BaseCheckpointSaver):
    """
    A persistent checkpointer that saves LangGraph states in the database.
    Uses the AI_SESSAO_CHAT table.
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
                    WHERE SESSION_ID = :session_id AND CHECKPOINT_ID = :checkpoint_id
                """
                cursor.execute(query, session_id=thread_id, checkpoint_id=checkpoint_id)
            else:
                query = """
                    SELECT CHECKPOINT_DATA, METADATA, CHECKPOINT_ID
                    FROM AI_SESSAO_CHAT
                    WHERE SESSION_ID = :session_id
                    ORDER BY CREATED_AT DESC
                    FETCH FIRST 1 ROWS ONLY
                """
                cursor.execute(query, session_id=thread_id)

            row = cursor.fetchone()
            if not row:
                return None

            checkpoint_data = row[0].read() if hasattr(row[0], 'read') else row[0]
            metadata_data = row[1].read() if row[1] and hasattr(row[1], 'read') else (row[1] or "{}")

            import json
            import base64
            try:
                cp_list = json.loads(checkpoint_data)
                cp_tuple = (cp_list[0], base64.b64decode(cp_list[1]))
            except:
                cp_tuple = ("json", checkpoint_data.encode("utf-8"))
            checkpoint = self.serde.loads_typed(cp_tuple)

            try:
                md_list = json.loads(metadata_data)
                md_tuple = (md_list[0], base64.b64decode(md_list[1]))
            except:
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
        """Save a checkpoint to the database."""
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = checkpoint["id"]

        import json
        import base64
        cp_type, cp_bytes = self.serde.dumps_typed(checkpoint)
        checkpoint_data_str = json.dumps([cp_type, base64.b64encode(cp_bytes).decode('ascii')])

        md_type, md_bytes = self.serde.dumps_typed(metadata)
        metadata_str = json.dumps([md_type, base64.b64encode(md_bytes).decode('ascii')])

        with self._get_cursor() as (cursor, conn):
            query = """
                MERGE INTO AI_SESSAO_CHAT tgt
                USING (SELECT :1 as SESSION_ID, :2 as CHECKPOINT_ID, :3 as CHECKPOINT_DATA, :4 as METADATA FROM DUAL) src
                ON (tgt.SESSION_ID = src.SESSION_ID AND tgt.CHECKPOINT_ID = src.CHECKPOINT_ID)
                WHEN MATCHED THEN
                    UPDATE SET CHECKPOINT_DATA = src.CHECKPOINT_DATA, METADATA = src.METADATA
                WHEN NOT MATCHED THEN
                    INSERT (SESSION_ID, CHECKPOINT_ID, CHECKPOINT_DATA, METADATA)
                    VALUES (src.SESSION_ID, src.CHECKPOINT_ID, src.CHECKPOINT_DATA, src.METADATA)
            """
            # Parâmetros 3 e 4 precisam ser declarados como CLOB para evitar ORA-01461
            cursor.setinputsizes(None, None, oracledb.DB_TYPE_CLOB, oracledb.DB_TYPE_CLOB)
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
