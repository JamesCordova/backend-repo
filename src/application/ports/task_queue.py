from typing import Protocol
from uuid import UUID


class TaskQueue(Protocol):
    def enqueue_processing(self, study_id: UUID, dicom_object_keys: list[str]) -> None:
        """Encola la tarea `procesar_dicom` de worker-repo. `dicom_object_keys`
        son rutas dentro del bucket de MinIO (ver
        application/use_cases/upload_study_file.py:object_key_for), no rutas
        de disco -- el worker las descarga el mismo antes de procesar.
        Fire-and-forget: la API no espera el resultado, eso lo refleja
        processing_tasks/studies.status, actualizado por el propio worker."""
        ...

    def enqueue_raw_processing(
        self,
        study_id: UUID,
        raw_object_key: str,
        dims: list[int],
        dtype: str,
        spacing: list[float],
        value_range: tuple[float, float] | None = None,
    ) -> None:
        """Encola la tarea `procesar_volumen_raw` de worker-repo -- camino
        alternativo para un volumen .raw sin cabecera (sin metadata propia,
        a diferencia de un DICOM real): dims/dtype/spacing los declara el
        cliente (ver ConfirmRawVolumeUpload), no se leen de ningun tag.
        `value_range` es opcional -- sin el, el worker usa min-max automatico
        sobre los propios datos en vez de una ventana fisica declarada."""
        ...
