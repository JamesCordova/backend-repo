from datetime import UTC, datetime, timedelta
from uuid import UUID

from application.use_cases.list_studies import ListStudies
from domain.entities import Study, StudyStatus


def _study(study_id: UUID, created_by: UUID, created_at: datetime) -> Study:
    return Study(
        id=study_id, name="Torax", status=StudyStatus.PENDING, created_by=created_by,
        created_at=created_at,
    )


async def test_devuelve_todos_los_estudios_sin_importar_quien_los_subio(study_repository):
    # Axial es una biblioteca compartida (datasets abiertos/sinteticos, no
    # datos reales de pacientes) -- no hay filtro por dueno ni por rol.
    owner_id = UUID(int=1)
    other_id = UUID(int=2)
    now = datetime.now(UTC)
    own_study = _study(UUID(int=10), owner_id, now)
    other_study = _study(UUID(int=11), other_id, now)
    await study_repository.save(own_study)
    await study_repository.save(other_study)
    use_case = ListStudies(study_repository)

    result = await use_case.execute()

    assert set(result) == {own_study, other_study}


async def test_devuelve_ordenado_del_mas_reciente_al_mas_antiguo(study_repository):
    owner_id = UUID(int=1)
    now = datetime.now(UTC)
    older = _study(UUID(int=10), owner_id, now - timedelta(days=1))
    newer = _study(UUID(int=11), owner_id, now)
    await study_repository.save(older)
    await study_repository.save(newer)
    use_case = ListStudies(study_repository)

    result = await use_case.execute()

    assert result == [newer, older]


async def test_sin_estudios_devuelve_lista_vacia(study_repository):
    use_case = ListStudies(study_repository)

    result = await use_case.execute()

    assert result == []
