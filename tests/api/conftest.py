"""Fixture compartido entre todos los tests de tests/api/ -- un TestClient con
todos los adaptadores reales reemplazados por los fakes de tests/conftest.py."""

import pytest
from fastapi.testclient import TestClient

from interfaces.api.deps import (
    get_consent_repository,
    get_id_generator,
    get_interaction_repository,
    get_object_storage,
    get_password_hasher,
    get_processing_task_repository,
    get_session_repository,
    get_study_repository,
    get_sus_repository,
    get_task_queue,
    get_token_service,
    get_user_repository,
    get_volume_repository,
)
from interfaces.api.main import create_app


@pytest.fixture
def client(
    user_repository,
    password_hasher,
    token_service,
    id_generator,
    study_repository,
    task_queue,
    object_storage,
    volume_repository,
    processing_task_repository,
    session_repository,
    interaction_repository,
    sus_repository,
    consent_repository,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_user_repository] = lambda: user_repository
    app.dependency_overrides[get_password_hasher] = lambda: password_hasher
    app.dependency_overrides[get_token_service] = lambda: token_service
    app.dependency_overrides[get_id_generator] = lambda: id_generator
    app.dependency_overrides[get_study_repository] = lambda: study_repository
    app.dependency_overrides[get_task_queue] = lambda: task_queue
    app.dependency_overrides[get_processing_task_repository] = lambda: processing_task_repository
    app.dependency_overrides[get_object_storage] = lambda: object_storage
    app.dependency_overrides[get_volume_repository] = lambda: volume_repository
    app.dependency_overrides[get_session_repository] = lambda: session_repository
    app.dependency_overrides[get_interaction_repository] = lambda: interaction_repository
    app.dependency_overrides[get_sus_repository] = lambda: sus_repository
    app.dependency_overrides[get_consent_repository] = lambda: consent_repository
    return TestClient(app)
