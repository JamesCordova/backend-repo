"""Contra Postgres real (testcontainers) -- verifica que las consultas SQL
crudas (psycopg) de verdad actualizan studies.status/processing_tasks como se
espera, no solo que el codigo compila."""

import psycopg

from processing.infrastructure.db.postgres_study_status_repository import (
    PostgresStudyStatusRepository,
)


def _fetch_study_status(database_url: str, study_id) -> str:
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT status FROM studies WHERE id = %s", (study_id,))
        return cur.fetchone()[0]


def _fetch_task(database_url: str, task_id):
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT status, attempt_number, error_message, finished_at, stage, progress_percent "
            "FROM processing_tasks WHERE id = %s",
            (task_id,),
        )
        return cur.fetchone()


def test_start_processing_marca_processing_y_crea_processing_task(database_url, seeded_study_id):
    repo = PostgresStudyStatusRepository(database_url)

    task_id = repo.start_processing(seeded_study_id)

    assert _fetch_study_status(database_url, seeded_study_id) == "processing"
    status, attempt_number, error_message, finished_at, stage, progress_percent = _fetch_task(
        database_url, task_id
    )
    assert status == "running"
    assert attempt_number == 1
    assert error_message is None
    assert finished_at is None
    assert stage == "queued"
    assert progress_percent == 0


def test_update_progress_actualiza_stage_y_porcentaje(database_url, seeded_study_id):
    repo = PostgresStudyStatusRepository(database_url)
    task_id = repo.start_processing(seeded_study_id)

    repo.update_progress(task_id, "resampling", 70)

    *_, stage, progress_percent = _fetch_task(database_url, task_id)
    assert stage == "resampling"
    assert progress_percent == 70


def test_mark_succeeded_deja_el_progreso_en_100(database_url, seeded_study_id):
    repo = PostgresStudyStatusRepository(database_url)
    task_id = repo.start_processing(seeded_study_id)
    repo.update_progress(task_id, "uploading_result", 90)

    repo.mark_succeeded(seeded_study_id, task_id)

    *_, stage, progress_percent = _fetch_task(database_url, task_id)
    assert stage == "done"
    assert progress_percent == 100


def test_intentos_sucesivos_incrementan_attempt_number(database_url, seeded_study_id):
    repo = PostgresStudyStatusRepository(database_url)

    repo.start_processing(seeded_study_id)
    second_task_id = repo.start_processing(seeded_study_id)

    _, attempt_number, *_ = _fetch_task(database_url, second_task_id)
    assert attempt_number == 2


def test_mark_succeeded_marca_ready_y_succeeded(database_url, seeded_study_id):
    repo = PostgresStudyStatusRepository(database_url)
    task_id = repo.start_processing(seeded_study_id)

    repo.mark_succeeded(seeded_study_id, task_id)

    assert _fetch_study_status(database_url, seeded_study_id) == "ready"
    status, _, _, finished_at, _, _ = _fetch_task(database_url, task_id)
    assert status == "succeeded"
    assert finished_at is not None


def test_mark_failed_marca_failed_con_el_mensaje_real(database_url, seeded_study_id):
    repo = PostgresStudyStatusRepository(database_url)
    task_id = repo.start_processing(seeded_study_id)

    repo.mark_failed(seeded_study_id, task_id, "DICOM corrupto: slice_003.dcm")

    assert _fetch_study_status(database_url, seeded_study_id) == "failed"
    status, _, error_message, finished_at, _, _ = _fetch_task(database_url, task_id)
    assert status == "failed"
    assert error_message == "DICOM corrupto: slice_003.dcm"
    assert finished_at is not None
