"""Prueba el adaptador que reemplazo a CeleryTaskQueue -- ver
infrastructure/queue/in_process_task_queue.py. Dos cosas distintas, dos
tests distintos:

1. Que enqueue_processing/enqueue_raw_processing llaman a
   run_dicom_processing/run_raw_volume_processing con los argumentos
   correctos (UUID -> str, tupla -> lista para value_range) -- usando un
   ThreadPoolExecutor (mismo proceso/interprete, asi que monkeypatch SI
   afecta lo que corre) para que sea rapido y no dependa de spawnear un
   proceso real.
2. Que el mecanismo de fondo -- someter trabajo a un Executor real y no
   bloquear el caller -- de verdad cruza a otro proceso, con un
   ProcessPoolExecutor real y una funcion de verdad separada (no un mock:
   un mock no sobrevive el pickling hacia el proceso hijo). Esto es lo que
   antes garantizaba Celery+Redis (un mensaje viaja fuera del proceso que
   sirve HTTP); aca lo garantiza la libreria estandar.

La orquestacion real del pipeline (processing/jobs.py, la logica que hered
worker-repo) tiene su propia cobertura aparte -- ver
tests/processing/unit/test_jobs.py (fakes) y
tests/processing/integration/test_jobs_real_pipeline.py (Postgres/MinIO
reales) -- este archivo solo cubre el "transporte".
"""

import asyncio
import threading
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from uuid import UUID

import infrastructure.queue.in_process_task_queue as queue_module
from infrastructure.queue.in_process_task_queue import InProcessTaskQueue


def _write_marker(path: str) -> None:
    """Top-level (picklable) a proposito -- tiene que sobrevivir el viaje
    real a un proceso hijo de ProcessPoolExecutor, algo que un objeto local
    (lambda, closure, Mock) no puede hacer."""
    Path(path).write_text("done")


async def _wait_until(predicate, timeout_seconds: float = 5.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while not predicate():
        assert loop.time() < deadline, "timeout esperando el resultado del pool"
        await asyncio.sleep(0.05)


async def test_submit_corre_la_funcion_en_un_proceso_real_sin_bloquear_el_caller(tmp_path):
    marker = tmp_path / "marker.txt"
    pool = ProcessPoolExecutor(max_workers=1)
    try:
        InProcessTaskQueue(pool)._submit(_write_marker, str(marker))
        # _submit() ya volvio aca -- si fuera bloqueante, el archivo ya
        # existiria; en cambio se espera a que el proceso hijo lo escriba.
        await _wait_until(marker.exists)
        assert marker.read_text() == "done"
    finally:
        pool.shutdown(wait=True)


async def test_enqueue_processing_llama_run_dicom_processing_con_los_argumentos_correctos(
    monkeypatch,
):
    calls: list[tuple] = []
    done = threading.Event()

    def fake_run_dicom_processing(study_id: str, dicom_object_keys: list[str]) -> dict:
        calls.append((study_id, dicom_object_keys))
        done.set()
        return {}

    monkeypatch.setattr(queue_module, "run_dicom_processing", fake_run_dicom_processing)

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        study_id = UUID(int=7)
        InProcessTaskQueue(pool).enqueue_processing(
            study_id, ["studies/x/a.dcm", "studies/x/b.dcm"]
        )
        await asyncio.get_running_loop().run_in_executor(None, done.wait, 5)
        assert calls == [(str(study_id), ["studies/x/a.dcm", "studies/x/b.dcm"])]
    finally:
        pool.shutdown(wait=True)


async def test_enqueue_raw_processing_llama_run_raw_volume_processing_con_los_argumentos_correctos(
    monkeypatch,
):
    calls: list[tuple] = []
    done = threading.Event()

    def fake_run_raw_volume_processing(
        study_id, raw_object_key, dims, dtype, spacing, value_range=None
    ) -> dict:
        calls.append((study_id, raw_object_key, dims, dtype, spacing, value_range))
        done.set()
        return {}

    monkeypatch.setattr(queue_module, "run_raw_volume_processing", fake_run_raw_volume_processing)

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        study_id = UUID(int=9)
        InProcessTaskQueue(pool).enqueue_raw_processing(
            study_id, "raws/x/v.raw", [4, 8, 8], "uint8", [1.0, 1.0, 1.0], (0.0, 255.0)
        )
        await asyncio.get_running_loop().run_in_executor(None, done.wait, 5)
        # value_range llega como tupla -- el adaptador la convierte a lista
        # (mismo criterio que CeleryTaskQueue, que la serializaba a JSON).
        assert calls == [
            (str(study_id), "raws/x/v.raw", [4, 8, 8], "uint8", [1.0, 1.0, 1.0], [0.0, 255.0])
        ]
    finally:
        pool.shutdown(wait=True)


async def test_enqueue_raw_processing_sin_value_range_pasa_none(monkeypatch):
    calls: list[tuple] = []
    done = threading.Event()

    def fake_run_raw_volume_processing(
        study_id, raw_object_key, dims, dtype, spacing, value_range=None
    ) -> dict:
        calls.append(value_range)
        done.set()
        return {}

    monkeypatch.setattr(queue_module, "run_raw_volume_processing", fake_run_raw_volume_processing)

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        InProcessTaskQueue(pool).enqueue_raw_processing(
            UUID(int=1), "raws/x/v.raw", [4, 8, 8], "uint8", [1.0, 1.0, 1.0]
        )
        await asyncio.get_running_loop().run_in_executor(None, done.wait, 5)
        assert calls == [None]
    finally:
        pool.shutdown(wait=True)
