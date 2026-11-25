"""Adaptador en proceso del puerto TaskQueue -- reemplaza a CeleryTaskQueue
(que enviaba un mensaje a Redis para que un proceso `worker` aparte lo
consumiera). No hay broker ni un segundo servicio de aplicacion: el
procesamiento pesado corre en el mismo proceso de la API, en un
`ProcessPoolExecutor` (creado una sola vez al arrancar -- ver
interfaces/api/main.py:lifespan) para no bloquear el event loop de uvicorn ni
competir por el GIL con los requests HTTP normales mientras SimpleITK/numpy
procesan un volumen.

Mismo contrato que CeleryTaskQueue: fire-and-forget -- `enqueue_processing`/
`enqueue_raw_processing` someten el trabajo real al pool y retornan de
inmediato, sin esperar el resultado. El progreso se refleja en Postgres
(processing_tasks/studies.status), actualizado por el propio proceso hijo
-- ver processing/jobs.py, que es literalmente el codigo que antes vivia en
worker-repo.
"""

import asyncio
import logging
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from typing import Any
from uuid import UUID

from application.ports.task_queue import TaskQueue
from processing.jobs import run_dicom_processing, run_raw_volume_processing

logger = logging.getLogger(__name__)


class InProcessTaskQueue(TaskQueue):
    def __init__(self, pool: ProcessPoolExecutor) -> None:
        self._pool = pool

    def _submit(self, func: Callable[..., Any], *args: Any) -> None:
        # Se llama siempre desde dentro de un endpoint async (ver
        # confirm_study_upload.py/confirm_raw_volume_upload.py), asi que
        # siempre hay un loop corriendo -- get_running_loop() nunca falla aca.
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(self._pool, func, *args)

        def _log_if_failed(f: "asyncio.Future[Any]") -> None:
            exc = f.exception()
            if exc is not None:
                # processing/jobs.py ya llamo a status_repo.mark_failed(...)
                # antes de relanzar la excepcion -- esto es solo para que no
                # quede completamente silenciosa (nadie mas espera este
                # future, a diferencia de un request HTTP normal).
                logger.error("tarea de procesamiento fallo: %s", exc)

        future.add_done_callback(_log_if_failed)

    def enqueue_processing(self, study_id: UUID, dicom_object_keys: list[str]) -> None:
        self._submit(run_dicom_processing, str(study_id), dicom_object_keys)

    def enqueue_raw_processing(
        self,
        study_id: UUID,
        raw_object_key: str,
        dims: list[int],
        dtype: str,
        spacing: list[float],
        value_range: tuple[float, float] | None = None,
    ) -> None:
        self._submit(
            run_raw_volume_processing,
            str(study_id),
            raw_object_key,
            dims,
            dtype,
            spacing,
            list(value_range) if value_range is not None else None,
        )
