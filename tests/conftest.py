"""Fixtures compartidos. Los fakes de aqui implementan los Protocol de
application/ports/ en memoria -- ningun test unitario ni de API toca Docker,
Postgres real, ni siquiera sqlite en disco.
"""

import os
import sys
from pathlib import Path
from uuid import UUID

import pytest

# Debe fijarse ANTES de importar infrastructure.config (Settings se instancia al
# importar el modulo) para que main.py no dispare create_all_tables contra un
# sqlite real durante las pruebas -- ver interfaces/api/main.py.
os.environ.setdefault("ENVIRONMENT", "test")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

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
from domain.entities import (
    ConsentRecord,
    Interaction,
    ProcessingTask,
    Role,
    Session,
    Study,
    SusQuestionnaire,
    User,
    Volume,
)


class FakeUserRepository(UserRepository):
    def __init__(self) -> None:
        self._by_email: dict[str, User] = {}

    async def get_by_email(self, email: str) -> User | None:
        return self._by_email.get(email)

    async def get_by_id(self, user_id: UUID) -> User | None:
        return next((u for u in self._by_email.values() if u.id == user_id), None)

    async def save(self, user: User) -> None:
        self._by_email[user.email] = user


class FakePasswordHasher(PasswordHasher):
    """No usa bcrypt real -- las pruebas de dominio no necesitan que sea criptograficamente
    fuerte, solo que hash/verify sean consistentes entre si. El adaptador real
    (BcryptPasswordHasher) se prueba aparte, ver tests/unit/test_bcrypt_password_hasher.py.
    """

    def hash(self, plain_password: str) -> str:
        return f"hashed:{plain_password}"

    def verify(self, plain_password: str, password_hash: str) -> bool:
        return password_hash == f"hashed:{plain_password}"


class FakeTokenService(TokenService):
    def __init__(self) -> None:
        self._issued: dict[str, UUID] = {}

    def issue(self, user_id: UUID, role: Role) -> str:
        token = f"token-for-{user_id}"
        self._issued[token] = user_id
        return token

    def verify(self, token: str) -> UUID:
        if token not in self._issued:
            raise InvalidTokenError(token)
        return self._issued[token]


class FakeIdGenerator(IdGenerator):
    """Ids secuenciales y deterministicos (0000...0001, 0000...0002, ...) --
    permite a un test afirmar exactamente que id se genero, algo imposible con
    uuid4()/uuid7() real, que son nuevos en cada corrida."""

    def __init__(self) -> None:
        self._next = 1

    def generate(self) -> UUID:
        value = UUID(int=self._next)
        self._next += 1
        return value


class FakeStudyRepository(StudyRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, Study] = {}

    async def get_by_id(self, study_id: UUID) -> Study | None:
        return self._by_id.get(study_id)

    async def save(self, study: Study) -> None:
        self._by_id[study.id] = study

    async def list_all(self) -> list[Study]:
        return sorted(self._by_id.values(), key=lambda s: s.created_at, reverse=True)


class FakeTaskQueue(TaskQueue):
    """No manda nada a Redis -- solo registra con que se la llamo, para que un
    test pueda afirmar que se encolo lo correcto."""

    def __init__(self) -> None:
        self.enqueued: list[tuple[UUID, list[str]]] = []
        self.enqueued_raw: list[tuple] = []

    def enqueue_processing(self, study_id: UUID, dicom_object_keys: list[str]) -> None:
        self.enqueued.append((study_id, dicom_object_keys))

    def enqueue_raw_processing(
        self,
        study_id: UUID,
        raw_object_key: str,
        dims: list[int],
        dtype: str,
        spacing: list[float],
        value_range: tuple[float, float] | None = None,
    ) -> None:
        self.enqueued_raw.append((study_id, raw_object_key, dims, dtype, spacing, value_range))


class FakeObjectStorage(ObjectStorage):
    """No sube nada a MinIO -- guarda los bytes en memoria, indexados por key,
    para que exists()/put()/get_stream() sean consistentes entre si dentro de
    un test."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    async def put(self, key: str, stream, length: int) -> None:
        self._objects[key] = stream.read()

    async def exists(self, key: str) -> bool:
        return key in self._objects

    async def get_stream(self, key: str, offset: int = 0, length: int = 0):
        data = self._objects[key]
        if offset or length:
            end = offset + length if length else len(data)
            yield data[offset:end]
        else:
            yield data


class FakeVolumeRepository(VolumeRepository):
    def __init__(self) -> None:
        self._by_key: dict[tuple[UUID, str], Volume] = {}

    def seed(self, volume: Volume) -> None:
        """Los tests insertan el volumen directo -- en produccion esta fila
        la crea worker-repo (PostgresVolumeRepository), no esta API."""
        self._by_key[(volume.study_id, volume.detail_level)] = volume

    async def get_latest_by_study_id(self, study_id: UUID, detail_level: str) -> Volume | None:
        return self._by_key.get((study_id, detail_level))


class FakeProcessingTaskRepository(ProcessingTaskRepository):
    def __init__(self) -> None:
        self._by_study_id: dict[UUID, ProcessingTask] = {}

    def seed(self, processing_task: ProcessingTask) -> None:
        """Los tests insertan la fila directo -- en produccion la crea y
        actualiza worker-repo, no esta API."""
        self._by_study_id[processing_task.study_id] = processing_task

    async def get_latest_by_study_id(self, study_id: UUID) -> ProcessingTask | None:
        return self._by_study_id.get(study_id)


class FakeSessionRepository(SessionRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, Session] = {}

    async def get_by_id(self, session_id: UUID) -> Session | None:
        return self._by_id.get(session_id)

    async def save(self, session: Session) -> None:
        self._by_id[session.id] = session


class FakeInteractionRepository(InteractionRepository):
    def __init__(self) -> None:
        self.saved: list[Interaction] = []

    async def save(self, interaction: Interaction) -> None:
        self.saved.append(interaction)


class FakeConsentRepository(ConsentRepository):
    def __init__(self) -> None:
        self._by_user_id: dict[UUID, ConsentRecord] = {}

    async def get_by_user_id(self, user_id: UUID) -> ConsentRecord | None:
        return self._by_user_id.get(user_id)

    async def save(self, consent: ConsentRecord) -> None:
        self._by_user_id[consent.user_id] = consent


class FakeSusRepository(SusRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, SusQuestionnaire] = {}

    async def save_with_responses(self, questionnaire: SusQuestionnaire) -> None:
        self._by_id[questionnaire.id] = questionnaire

    async def get_by_id(self, questionnaire_id: UUID) -> SusQuestionnaire | None:
        return self._by_id.get(questionnaire_id)


@pytest.fixture
def sus_repository() -> FakeSusRepository:
    return FakeSusRepository()


@pytest.fixture
def consent_repository() -> FakeConsentRepository:
    return FakeConsentRepository()


@pytest.fixture
def session_repository() -> FakeSessionRepository:
    return FakeSessionRepository()


@pytest.fixture
def interaction_repository() -> FakeInteractionRepository:
    return FakeInteractionRepository()


@pytest.fixture
def id_generator() -> FakeIdGenerator:
    return FakeIdGenerator()


@pytest.fixture
def processing_task_repository() -> FakeProcessingTaskRepository:
    return FakeProcessingTaskRepository()


@pytest.fixture
def object_storage() -> FakeObjectStorage:
    return FakeObjectStorage()


@pytest.fixture
def volume_repository() -> FakeVolumeRepository:
    return FakeVolumeRepository()


@pytest.fixture
def study_repository() -> FakeStudyRepository:
    return FakeStudyRepository()


@pytest.fixture
def task_queue() -> FakeTaskQueue:
    return FakeTaskQueue()


@pytest.fixture
def user_repository() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def password_hasher() -> FakePasswordHasher:
    return FakePasswordHasher()


@pytest.fixture
def token_service() -> FakeTokenService:
    return FakeTokenService()
