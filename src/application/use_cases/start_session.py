from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from application.errors import StudyNotFoundError
from application.ports.id_generator import IdGenerator
from application.ports.session_repository import SessionRepository
from application.ports.study_repository import StudyRepository
from domain.entities import Session


@dataclass(frozen=True, slots=True)
class StartSessionInput:
    study_id: UUID
    requesting_user_id: UUID


class StartSession:
    """Abre una sesion de visualizacion -- no exige que el estudio ya este
    'ready' a proposito: la pantalla de carga (mientras status=processing)
    tambien genera interacciones atribuibles (ej. 'usuario_espero',
    'usuario_cancelo'), seccion 9 del documento de arquitectura. Cualquier
    usuario autenticado puede abrir sesion en cualquier estudio -- Axial es
    una biblioteca compartida (seccion 9/21), y con la lista de estudios
    visible para todos, el caso normal es abrir sesion en un estudio que no
    subio uno mismo. requesting_user_id no autoriza nada aca, solo identifica
    de quien es la sesion."""

    def __init__(
        self, studies: StudyRepository, sessions: SessionRepository, ids: IdGenerator
    ) -> None:
        self._studies = studies
        self._sessions = sessions
        self._ids = ids

    async def execute(self, data: StartSessionInput) -> Session:
        study = await self._studies.get_by_id(data.study_id)
        if study is None:
            raise StudyNotFoundError(data.study_id)

        session = Session(
            id=self._ids.generate(),
            user_id=data.requesting_user_id,
            study_id=data.study_id,
            started_at=datetime.now(UTC),
        )
        await self._sessions.save(session)
        return session
