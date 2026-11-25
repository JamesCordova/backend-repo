from datetime import UTC, datetime
from uuid import UUID

import pytest

from application.errors import SessionAccessDeniedError, SessionNotFoundError
from application.use_cases.record_interaction import RecordInteraction, RecordInteractionInput
from domain.entities import Role, Session


def _session(session_id: UUID, user_id: UUID) -> Session:
    return Session(
        id=session_id, user_id=user_id, study_id=UUID(int=99), started_at=datetime.now(UTC)
    )


async def test_registra_la_interaccion_con_el_user_id_de_la_sesion(
    session_repository, interaction_repository, id_generator
):
    owner_id = UUID(int=1)
    session = _session(UUID(int=7), owner_id)
    await session_repository.save(session)
    use_case = RecordInteraction(session_repository, interaction_repository, id_generator)

    interaction = await use_case.execute(
        RecordInteractionInput(
            session_id=session.id,
            action_type="rotar_volumen",
            metadata={"eje": "z", "grados": 90},
            requesting_user_id=owner_id,
            requesting_user_role=Role.STUDENT,
        )
    )

    assert interaction.session_id == session.id
    assert interaction.action_type == "rotar_volumen"
    assert interaction.metadata == {"eje": "z", "grados": 90}
    assert interaction_repository.saved == [interaction]


async def test_no_permite_registrar_en_sesion_ajena(
    session_repository, interaction_repository, id_generator
):
    owner_id = UUID(int=1)
    other_id = UUID(int=2)
    session = _session(UUID(int=7), owner_id)
    await session_repository.save(session)
    use_case = RecordInteraction(session_repository, interaction_repository, id_generator)

    with pytest.raises(SessionAccessDeniedError):
        await use_case.execute(
            RecordInteractionInput(
                session_id=session.id,
                action_type="rotar_volumen",
                metadata={},
                requesting_user_id=other_id,
                requesting_user_role=Role.STUDENT,
            )
        )
    assert interaction_repository.saved == []


async def test_rechaza_sesion_inexistente(session_repository, interaction_repository, id_generator):
    use_case = RecordInteraction(session_repository, interaction_repository, id_generator)

    with pytest.raises(SessionNotFoundError):
        await use_case.execute(
            RecordInteractionInput(
                session_id=UUID(int=404),
                action_type="rotar_volumen",
                metadata={},
                requesting_user_id=UUID(int=1),
                requesting_user_role=Role.STUDENT,
            )
        )
