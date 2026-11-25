from uuid import UUID, uuid4

import psycopg

from processing.application.ports.study_status_repository import StudyStatusRepository


class PostgresStudyStatusRepository(StudyStatusRepository):
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def start_processing(self, study_id: UUID) -> UUID:
        processing_task_id = uuid4()
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COALESCE(MAX(attempt_number), 0) + 1
                    FROM processing_tasks WHERE study_id = %s
                    """,
                    (study_id,),
                )
                attempt_number = cur.fetchone()[0]

                cur.execute(
                    """
                    INSERT INTO processing_tasks
                        (id, study_id, attempt_number, status, stage, progress_percent, started_at)
                    VALUES (%s, %s, %s, 'running', 'queued', 0, now())
                    """,
                    (processing_task_id, study_id, attempt_number),
                )
                cur.execute(
                    "UPDATE studies SET status = 'processing' WHERE id = %s", (study_id,)
                )
            conn.commit()
        return processing_task_id

    def update_progress(self, processing_task_id: UUID, stage: str, progress_percent: int) -> None:
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE processing_tasks SET stage = %s, progress_percent = %s WHERE id = %s",
                    (stage, progress_percent, processing_task_id),
                )
            conn.commit()

    def mark_succeeded(self, study_id: UUID, processing_task_id: UUID) -> None:
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE processing_tasks
                    SET status = 'succeeded', stage = 'done', progress_percent = 100,
                        finished_at = now()
                    WHERE id = %s
                    """,
                    (processing_task_id,),
                )
                cur.execute("UPDATE studies SET status = 'ready' WHERE id = %s", (study_id,))
            conn.commit()

    def mark_failed(self, study_id: UUID, processing_task_id: UUID, error_message: str) -> None:
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE processing_tasks
                    SET status = 'failed', error_message = %s, finished_at = now()
                    WHERE id = %s
                    """,
                    (error_message, processing_task_id),
                )
                cur.execute("UPDATE studies SET status = 'failed' WHERE id = %s", (study_id,))
            conn.commit()
