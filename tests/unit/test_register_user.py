from uuid import UUID

import pytest

from application.errors import EmailAlreadyRegisteredError
from application.use_cases.register_user import RegisterUser, RegisterUserInput
from domain.entities import Role


async def test_registra_un_usuario_nuevo(user_repository, password_hasher, id_generator):
    use_case = RegisterUser(user_repository, password_hasher, id_generator)

    user = await use_case.execute(
        RegisterUserInput(name="Ana", email="ANA@example.com", plain_password="secret123")
    )

    assert user.id == UUID(int=1)  # el id_generator fake es deterministico
    assert user.email == "ana@example.com"  # normalizado a minusculas
    assert user.role == Role.STUDENT
    assert user.password_hash != "secret123"  # nunca se guarda en texto plano
    stored = await user_repository.get_by_email("ana@example.com")
    assert stored == user


async def test_rechaza_email_duplicado(user_repository, password_hasher, id_generator):
    use_case = RegisterUser(user_repository, password_hasher, id_generator)
    await use_case.execute(
        RegisterUserInput(name="Ana", email="ana@example.com", plain_password="secret123")
    )

    with pytest.raises(EmailAlreadyRegisteredError):
        await use_case.execute(
            RegisterUserInput(name="Ana 2", email="ana@example.com", plain_password="otraClave")
        )
