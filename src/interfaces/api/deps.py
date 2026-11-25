"""Composition root: aqui, y solo aqui, se cablean adaptadores reales a casos de
uso. Los tests de tests/api/ reemplazan estas funciones via
app.dependency_overrides para inyectar fakes en su lugar, sin tocar el resto
del codigo de produccion.
"""

from concurrent.futures import ProcessPoolExecutor
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from application.ports.consent_repository import ConsentRepository
from application.ports.id_generator import IdGenerator
from application.ports.interaction_repository import InteractionRepository
from application.ports.object_storage import ObjectStorage
from application.ports.password_hasher import PasswordHasher
from application.ports.processing_task_repository import ProcessingTaskRepository
from application.ports.session_repository import SessionRepository
from application.ports.study_repository import StudyRepository
from application.ports.sus_repository import SusRepository
from application.ports.task_queue import TaskQueue
from application.ports.token_service import InvalidTokenError, TokenService
from application.ports.user_repository import UserRepository
from application.ports.volume_repository import VolumeRepository
from application.use_cases.confirm_raw_volume_upload import ConfirmRawVolumeUpload
from application.use_cases.confirm_study_upload import ConfirmStudyUpload
from application.use_cases.end_session import EndSession
from application.use_cases.get_consent_status import GetConsentStatus
from application.use_cases.get_study import GetStudy
from application.use_cases.get_study_volume import GetStudyVolume
from application.use_cases.get_sus_questionnaire import GetSusQuestionnaire
from application.use_cases.list_studies import ListStudies
from application.use_cases.login_user import LoginUser
from application.use_cases.record_consent import RecordConsent
from application.use_cases.record_interaction import RecordInteraction
from application.use_cases.register_user import RegisterUser
from application.use_cases.start_session import StartSession
from application.use_cases.submit_sus_questionnaire import SubmitSusQuestionnaire
from application.use_cases.upload_study import UploadStudy
from application.use_cases.upload_study_file import UploadStudyFile
from domain.entities import User
from infrastructure.config import settings
from infrastructure.db.session import get_session
from infrastructure.db.sqlalchemy_consent_repository import SqlAlchemyConsentRepository
from infrastructure.db.sqlalchemy_interaction_repository import SqlAlchemyInteractionRepository
from infrastructure.db.sqlalchemy_processing_task_repository import (
    SqlAlchemyProcessingTaskRepository,
)
from infrastructure.db.sqlalchemy_session_repository import SqlAlchemySessionRepository
from infrastructure.db.sqlalchemy_study_repository import SqlAlchemyStudyRepository
from infrastructure.db.sqlalchemy_sus_repository import SqlAlchemySusRepository
from infrastructure.db.sqlalchemy_user_repository import SqlAlchemyUserRepository
from infrastructure.db.sqlalchemy_volume_repository import SqlAlchemyVolumeRepository
from infrastructure.ids.uuid7_id_generator import Uuid7IdGenerator
from infrastructure.queue.in_process_task_queue import InProcessTaskQueue
from infrastructure.security.bcrypt_password_hasher import BcryptPasswordHasher
from infrastructure.security.jose_token_service import JoseTokenService
from infrastructure.storage.local_filesystem_object_storage import LocalFilesystemObjectStorage
from infrastructure.storage.minio_object_storage import MinioObjectStorage

_bearer_scheme = HTTPBearer(auto_error=False)


def _build_object_storage() -> ObjectStorage:
    """settings.storage_backend elige el adaptador -- "local" (default, sin
    servicios externos, ver README) o "minio" (para cuando si hay un
    MinIO/S3 real). Mismo Protocol de los dos lados, ningun caso de uso sabe
    cual esta activo."""
    if settings.storage_backend == "minio":
        return MinioObjectStorage(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            bucket=settings.minio_bucket,
            secure=settings.minio_secure,
        )
    return LocalFilesystemObjectStorage(settings.local_storage_dir)


# Singleton de proceso: el cliente de MinIO (o el path base, para el
# adaptador local) no tiene sentido recrearlo por request (a diferencia de
# la sesion de SQLAlchemy, que si es por-request). main.py llama a
# ensure_bucket() una vez al arrancar.
object_storage = _build_object_storage()

# Singleton de proceso, igual que object_storage arriba -- el pool en si NO
# lanza procesos hijo todavia al construirse (concurrent.futures los arranca
# de forma perezosa, recien en el primer submit()/run_in_executor real), asi
# que crearlo aca (a nivel de modulo) es seguro y no le cuesta nada a un
# request que nunca sube un estudio. main.py lo cierra (shutdown) al apagar
# la app -- ver lifespan(). Reemplaza al proceso `celery worker` separado que
# tenia worker-repo: aqui el "worker" es este pool, dentro del mismo proceso
# que sirve HTTP (ver infrastructure/queue/in_process_task_queue.py).
process_pool = ProcessPoolExecutor(max_workers=settings.processing_workers)


async def get_user_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserRepository:
    return SqlAlchemyUserRepository(session)


def get_password_hasher() -> PasswordHasher:
    return BcryptPasswordHasher()


def get_token_service() -> TokenService:
    return JoseTokenService(settings.jwt_secret, settings.jwt_expire_minutes)


def get_id_generator() -> IdGenerator:
    return Uuid7IdGenerator()


async def get_study_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StudyRepository:
    return SqlAlchemyStudyRepository(session)


def get_task_queue() -> TaskQueue:
    return InProcessTaskQueue(process_pool)


def get_object_storage() -> ObjectStorage:
    return object_storage


def get_upload_study_use_case(
    studies: Annotated[StudyRepository, Depends(get_study_repository)],
    ids: Annotated[IdGenerator, Depends(get_id_generator)],
) -> UploadStudy:
    return UploadStudy(studies, ids)


def get_upload_study_file_use_case(
    studies: Annotated[StudyRepository, Depends(get_study_repository)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> UploadStudyFile:
    return UploadStudyFile(studies, storage)


def get_confirm_study_upload_use_case(
    studies: Annotated[StudyRepository, Depends(get_study_repository)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    tasks: Annotated[TaskQueue, Depends(get_task_queue)],
) -> ConfirmStudyUpload:
    return ConfirmStudyUpload(studies, storage, tasks)


def get_confirm_raw_volume_upload_use_case(
    studies: Annotated[StudyRepository, Depends(get_study_repository)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    tasks: Annotated[TaskQueue, Depends(get_task_queue)],
) -> ConfirmRawVolumeUpload:
    return ConfirmRawVolumeUpload(studies, storage, tasks)


async def get_processing_task_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProcessingTaskRepository:
    return SqlAlchemyProcessingTaskRepository(session)


def get_get_study_use_case(
    studies: Annotated[StudyRepository, Depends(get_study_repository)],
    processing_tasks: Annotated[ProcessingTaskRepository, Depends(get_processing_task_repository)],
) -> GetStudy:
    return GetStudy(studies, processing_tasks)


def get_list_studies_use_case(
    studies: Annotated[StudyRepository, Depends(get_study_repository)],
) -> ListStudies:
    return ListStudies(studies)


async def get_volume_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> VolumeRepository:
    return SqlAlchemyVolumeRepository(session)


def get_get_study_volume_use_case(
    studies: Annotated[StudyRepository, Depends(get_study_repository)],
    volumes: Annotated[VolumeRepository, Depends(get_volume_repository)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> GetStudyVolume:
    return GetStudyVolume(studies, volumes, storage)


async def get_session_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SessionRepository:
    return SqlAlchemySessionRepository(session)


async def get_interaction_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InteractionRepository:
    return SqlAlchemyInteractionRepository(session)


def get_start_session_use_case(
    studies: Annotated[StudyRepository, Depends(get_study_repository)],
    sessions: Annotated[SessionRepository, Depends(get_session_repository)],
    ids: Annotated[IdGenerator, Depends(get_id_generator)],
) -> StartSession:
    return StartSession(studies, sessions, ids)


def get_end_session_use_case(
    sessions: Annotated[SessionRepository, Depends(get_session_repository)],
) -> EndSession:
    return EndSession(sessions)


def get_record_interaction_use_case(
    sessions: Annotated[SessionRepository, Depends(get_session_repository)],
    interactions: Annotated[InteractionRepository, Depends(get_interaction_repository)],
    ids: Annotated[IdGenerator, Depends(get_id_generator)],
) -> RecordInteraction:
    return RecordInteraction(sessions, interactions, ids)


async def get_sus_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SusRepository:
    return SqlAlchemySusRepository(session)


def get_submit_sus_use_case(
    sus: Annotated[SusRepository, Depends(get_sus_repository)],
    ids: Annotated[IdGenerator, Depends(get_id_generator)],
) -> SubmitSusQuestionnaire:
    return SubmitSusQuestionnaire(sus, ids)


def get_get_sus_use_case(
    sus: Annotated[SusRepository, Depends(get_sus_repository)],
) -> GetSusQuestionnaire:
    return GetSusQuestionnaire(sus)


async def get_consent_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ConsentRepository:
    return SqlAlchemyConsentRepository(session)


def get_record_consent_use_case(
    consents: Annotated[ConsentRepository, Depends(get_consent_repository)],
    ids: Annotated[IdGenerator, Depends(get_id_generator)],
) -> RecordConsent:
    return RecordConsent(consents, ids)


def get_get_consent_status_use_case(
    consents: Annotated[ConsentRepository, Depends(get_consent_repository)],
) -> GetConsentStatus:
    return GetConsentStatus(consents)


def get_register_use_case(
    users: Annotated[UserRepository, Depends(get_user_repository)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    ids: Annotated[IdGenerator, Depends(get_id_generator)],
) -> RegisterUser:
    return RegisterUser(users, hasher, ids)


def get_login_use_case(
    users: Annotated[UserRepository, Depends(get_user_repository)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
) -> LoginUser:
    return LoginUser(users, hasher, tokens)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falta el token")
    try:
        user_id: UUID = tokens.verify(credentials.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token invalido") from exc

    user = await users.get_by_id(user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario no encontrado")
    return user
