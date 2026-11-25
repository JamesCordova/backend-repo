import pytest

from application.errors import InvalidCredentialsError
from application.use_cases.login_user import LoginUser, LoginUserInput
from application.use_cases.register_user import RegisterUser, RegisterUserInput


async def test_login_exitoso_devuelve_token(
    user_repository, password_hasher, token_service, id_generator
):
    await RegisterUser(user_repository, password_hasher, id_generator).execute(
        RegisterUserInput(name="Ana", email="ana@example.com", plain_password="secret123")
    )
    use_case = LoginUser(user_repository, password_hasher, token_service)

    result = await use_case.execute(
        LoginUserInput(email="ana@example.com", plain_password="secret123")
    )

    assert result.access_token


async def test_rechaza_password_incorrecto(
    user_repository, password_hasher, token_service, id_generator
):
    await RegisterUser(user_repository, password_hasher, id_generator).execute(
        RegisterUserInput(name="Ana", email="ana@example.com", plain_password="secret123")
    )
    use_case = LoginUser(user_repository, password_hasher, token_service)

    with pytest.raises(InvalidCredentialsError):
        await use_case.execute(
            LoginUserInput(email="ana@example.com", plain_password="incorrecta")
        )


async def test_rechaza_email_inexistente(user_repository, password_hasher, token_service):
    use_case = LoginUser(user_repository, password_hasher, token_service)

    with pytest.raises(InvalidCredentialsError):
        await use_case.execute(
            LoginUserInput(email="nadie@example.com", plain_password="lo-que-sea")
        )
