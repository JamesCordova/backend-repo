from datetime import UTC, datetime
from uuid import UUID

import pytest

from application.errors import SessionAccessDeniedError, SessionNotFoundError
from application.use_cases.end_session import EndSession, EndSessionInput
from domain.entities import Role, Session


def _session(session_id: UUID, user_id: UUID) -> Session:
    return Session(
        id=session_id, user_id=user_id, study_id=UUID(int=99), started_at=datetime.now(UTC)
    )


async def test_el_dueno_puede_terminar_su_sesion(session_repository):
    owner_id = UUID(int=1)
    session = _session(UUID(int=7), owner_id)
    await session_repository.save(session)
    use_case = EndSession(session_repository)

    await use_case.execute(
        EndSessionInput(
            session_id=session.id, requesting_user_id=owner_id, requesting_user_role=Role.STUDENT
        )
    )

    updated = await session_repository.get_by_id(session.id)
    assert not updated.is_active
    assert updated.ended_at is not None


async def test_terminar_dos_veces_no_falla(session_repository):
    owner_id = UUID(int=1)
    session = _session(UUID(int=7), owner_id)
    await session_repository.save(session)
    use_case = EndSession(session_repository)
    data = EndSessionInput(
        session_id=session.id, requesting_user_id=owner_id, requesting_user_role=Role.STUDENT
    )

    await use_case.execute(data)
    first_ended_at = (await session_repository.get_by_id(session.id)).ended_at
    await use_case.execute(data)  # idempotente, no revienta ni pisa el valor

    assert (await session_repository.get_by_id(session.id)).ended_at == first_ended_at


async def test_no_permite_terminar_sesion_ajena(session_repository):
    owner_id = UUID(int=1)
    other_id = UUID(int=2)
    session = _session(UUID(int=7), owner_id)
    await session_repository.save(session)
    use_case = EndSession(session_repository)

    with pytest.raises(SessionAccessDeniedError):
        await use_case.execute(
            EndSessionInput(
                session_id=session.id, requesting_user_id=other_id, requesting_user_role=Role.STUDENT
            )
        )


async def test_rechaza_sesion_inexistente(session_repository):
    use_case = EndSession(session_repository)

    with pytest.raises(SessionNotFoundError):
        await use_case.execute(
            EndSessionInput(
                session_id=UUID(int=404),
                requesting_user_id=UUID(int=1),
                requesting_user_role=Role.STUDENT,
            )
        )
