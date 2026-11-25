from datetime import UTC, datetime
from uuid import UUID

import pytest

from application.errors import StudyNotFoundError
from application.use_cases.start_session import StartSession, StartSessionInput
from domain.entities import Study, StudyStatus


def _study(study_id: UUID, owner_id: UUID) -> Study:
    return Study(
        id=study_id,
        name="Torax",
        status=StudyStatus.PENDING,
        created_by=owner_id,
        created_at=datetime.now(UTC),
    )


async def test_el_dueno_puede_iniciar_sesion(study_repository, session_repository, id_generator):
    owner_id = UUID(int=1)
    study = _study(UUID(int=7), owner_id)
    await study_repository.save(study)
    use_case = StartSession(study_repository, session_repository, id_generator)

    session = await use_case.execute(
        StartSessionInput(study_id=study.id, requesting_user_id=owner_id)
    )

    assert session.user_id == owner_id
    assert session.study_id == study.id
    assert session.is_active
    stored = await session_repository.get_by_id(session.id)
    assert stored == session


async def test_cualquier_usuario_puede_iniciar_sesion_en_un_estudio_ajeno(
    study_repository, session_repository, id_generator
):
    # Axial es una biblioteca compartida -- el caso normal es abrir sesion en
    # un estudio que no subio uno mismo.
    owner_id = UUID(int=1)
    other_id = UUID(int=2)
    study = _study(UUID(int=7), owner_id)
    await study_repository.save(study)
    use_case = StartSession(study_repository, session_repository, id_generator)

    session = await use_case.execute(
        StartSessionInput(study_id=study.id, requesting_user_id=other_id)
    )

    assert session.user_id == other_id
    assert session.study_id == study.id


async def test_rechaza_estudio_inexistente(study_repository, session_repository, id_generator):
    use_case = StartSession(study_repository, session_repository, id_generator)

    with pytest.raises(StudyNotFoundError):
        await use_case.execute(
            StartSessionInput(study_id=UUID(int=404), requesting_user_id=UUID(int=1))
        )
