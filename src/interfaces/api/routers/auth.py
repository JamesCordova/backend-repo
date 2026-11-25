from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from application.errors import EmailAlreadyRegisteredError, InvalidCredentialsError
from application.use_cases.login_user import LoginUser, LoginUserInput
from application.use_cases.register_user import RegisterUser, RegisterUserInput
from domain.entities import User
from interfaces.api.deps import get_current_user, get_login_use_case, get_register_use_case
from interfaces.api.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/registro", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def registrar(
    body: RegisterRequest,
    use_case: Annotated[RegisterUser, Depends(get_register_use_case)],
) -> UserResponse:
    try:
        user = await use_case.execute(
            RegisterUserInput(name=body.name, email=body.email, plain_password=body.password)
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "El email ya esta registrado") from exc
    return UserResponse(id=user.id, name=user.name, email=user.email, role=user.role)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    use_case: Annotated[LoginUser, Depends(get_login_use_case)],
) -> TokenResponse:
    try:
        result = await use_case.execute(
            LoginUserInput(email=body.email, plain_password=body.password)
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales invalidas") from exc
    return TokenResponse(access_token=result.access_token)


@router.get("/me", response_model=UserResponse)
async def me(current_user: Annotated[User, Depends(get_current_user)]) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        name=current_user.name,
        email=current_user.email,
        role=current_user.role,
    )
