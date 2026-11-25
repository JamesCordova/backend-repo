from application.ports.study_repository import StudyRepository
from domain.entities import Study


class ListStudies:
    """Necesario para que un cliente (el frontend) pueda mostrar la
    biblioteca de estudios sin ya saber ningun study_id de antemano --
    GET /estudios/{id} exige conocerlo. Sin input: cualquier usuario
    autenticado ve todos los estudios (ver StudyRepository.list_all), no hay
    nada que decidir en base a quien pregunta -- la autenticacion en si la
    exige el router (get_current_user), no este caso de uso."""

    def __init__(self, studies: StudyRepository) -> None:
        self._studies = studies

    async def execute(self) -> list[Study]:
        return await self._studies.list_all()
