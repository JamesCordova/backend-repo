"""Contra Postgres real (testcontainers). volumes tiene FK a studies y a
processing_tasks -- en produccion ambas filas las crea worker-repo antes de
llamar VolumeRepository.create(); aca se insertan directo por SQLAlchemy
porque api-repo no tiene (ni necesita) un puerto propio para escribirlas,
solo para leerlas.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from domain.entities import Role, Study, StudyStatus, User
from infrastructure.db.models import ProcessingTaskModel, VolumeModel
from infrastructure.db.sqlalchemy_study_repository import SqlAlchemyStudyRepository
from infrastructure.db.sqlalchemy_user_repository import SqlAlchemyUserRepository
from infrastructure.db.sqlalchemy_volume_repository import SqlAlchemyVolumeRepository


async def _seed_study_with_processing_task(db_session) -> tuple[Study, UUID]:
    owner = User(
        id=uuid4(),
        name="Ana",
        email=f"ana-{uuid4()}@example.com",
        password_hash="hashed:x",
        role=Role.STUDENT,
        created_at=datetime.now(UTC),
    )
    await SqlAlchemyUserRepository(db_session).save(owner)

    study = Study(
        id=uuid4(),
        name="Torax",
        status=StudyStatus.READY,
        created_by=owner.id,
        created_at=datetime.now(UTC),
    )
    await SqlAlchemyStudyRepository(db_session).save(study)

    processing_task_id = uuid4()
    db_session.add(
        ProcessingTaskModel(
            id=processing_task_id,
            study_id=study.id,
            attempt_number=1,
            status="succeeded",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )
    )
    await db_session.commit()
    return study, processing_task_id


async def _seed_volume(db_session, study_id, processing_task_id, detail_level: str) -> VolumeModel:
    model = VolumeModel(
        id=uuid4(),
        study_id=study_id,
        processing_task_id=processing_task_id,
        detail_level=detail_level,
        format="npz",
        storage_path=f"results/{study_id}/{detail_level}.npz",
        size_bytes=1234,
        created_at=datetime.now(UTC),
    )
    db_session.add(model)
    await db_session.commit()
    return model


async def test_devuelve_el_volumen_del_nivel_de_detalle_pedido(db_session):
    study, processing_task_id = await _seed_study_with_processing_task(db_session)
    await _seed_volume(db_session, study.id, processing_task_id, "preview")
    await _seed_volume(db_session, study.id, processing_task_id, "full")
    repo = SqlAlchemyVolumeRepository(db_session)

    preview = await repo.get_latest_by_study_id(study.id, "preview")
    full = await repo.get_latest_by_study_id(study.id, "full")

    assert preview is not None and preview.detail_level == "preview"
    assert full is not None and full.detail_level == "full"
    assert preview.storage_path != full.storage_path


async def test_sin_volumen_de_ese_nivel_devuelve_none(db_session):
    study, processing_task_id = await _seed_study_with_processing_task(db_session)
    await _seed_volume(db_session, study.id, processing_task_id, "full")
    repo = SqlAlchemyVolumeRepository(db_session)

    assert await repo.get_latest_by_study_id(study.id, "preview") is None
