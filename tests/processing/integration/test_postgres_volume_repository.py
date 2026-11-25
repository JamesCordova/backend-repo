import psycopg

from processing.infrastructure.db.postgres_study_status_repository import (
    PostgresStudyStatusRepository,
)
from processing.infrastructure.db.postgres_volume_repository import PostgresVolumeRepository


def test_create_inserta_la_fila_esperada(database_url, seeded_study_id):
    status_repo = PostgresStudyStatusRepository(database_url)
    task_id = status_repo.start_processing(seeded_study_id)
    volume_repo = PostgresVolumeRepository(database_url)
    storage_path = f"results/{seeded_study_id}/full.npz"

    volume_repo.create(
        study_id=seeded_study_id,
        processing_task_id=task_id,
        detail_level="full",
        format="npz",
        storage_path=storage_path,
        size_bytes=472,
    )

    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT detail_level, format, storage_path, size_bytes "
            "FROM volumes WHERE study_id = %s AND processing_task_id = %s",
            (seeded_study_id, task_id),
        )
        row = cur.fetchone()

    assert row == ("full", "npz", storage_path, 472)
