from uuid import UUID, uuid4

import psycopg

from processing.application.ports.volume_repository import VolumeRepository


class PostgresVolumeRepository(VolumeRepository):
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def create(
        self,
        study_id: UUID,
        processing_task_id: UUID,
        detail_level: str,
        format: str,
        storage_path: str,
        size_bytes: int,
    ) -> None:
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO volumes
                        (id, study_id, processing_task_id, detail_level, format,
                         storage_path, size_bytes, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                    """,
                    (uuid4(), study_id, processing_task_id, detail_level, format,
                     storage_path, size_bytes),
                )
            conn.commit()
