from pathlib import Path
from typing import Protocol


class ObjectStorage(Protocol):
    def download_to(self, key: str, local_path: Path) -> None:
        """Descarga el objeto (subido por api-repo, mismo bucket/keys -- ver
        application/use_cases/upload_study_file.py:object_key_for en api-repo)
        a un archivo local. Sincrono porque Celery ejecuta la tarea de forma
        sincrona por defecto."""
        ...

    def upload_from(self, local_path: Path, key: str) -> None:
        """Sube el volumen ya procesado -- api-repo lo sirve despues via
        streaming proxy (GET /estudios/{id}/volumen), nunca exponiendo MinIO
        directo (seccion 6.6 del documento de clean architecture)."""
        ...
