from pathlib import Path

import numpy as np

from processing.application.use_cases.process_dicom_series import (
    ProcessDicomSeries,
    ProcessDicomSeriesInput,
)
from processing.domain.entities import Volume


class FakeVolumeProcessor:
    """No usa SimpleITK -- verifica solo la orquestacion del caso de uso
    (cargar -> normalizar -> resamplear), no el procesamiento de imagen real."""

    def __init__(self) -> None:
        self.load_calls = 0
        self.resample_calls: list[tuple[Volume, float]] = []

    def load_series(self, dicom_paths: list[Path]) -> Volume:
        self.load_calls += 1
        return Volume(pixel_array=np.array([[[-1000.0, 1000.0]]]), spacing=(2.0, 1.0, 1.0))

    def resample_to_isotropic(self, volume: Volume, target_spacing_mm: float) -> Volume:
        self.resample_calls.append((volume, target_spacing_mm))
        return Volume(pixel_array=volume.pixel_array, spacing=(target_spacing_mm,) * 3)


def test_orquesta_carga_normalizacion_y_resampling_por_nivel():
    processor = FakeVolumeProcessor()
    use_case = ProcessDicomSeries(processor)

    result = use_case.execute(
        ProcessDicomSeriesInput(
            dicom_paths=[Path("a.dcm")],
            min_hu=-1000.0,
            max_hu=1000.0,
            detail_levels={"preview": 4.0, "full": 1.0},
        )
    )

    assert set(result.keys()) == {"preview", "full"}
    assert result["preview"].spacing == (4.0, 4.0, 4.0)
    assert result["full"].spacing == (1.0, 1.0, 1.0)

    # la carga y normalizacion se hacen UNA sola vez, no una por nivel
    assert processor.load_calls == 1
    assert len(processor.resample_calls) == 2
    # ambos resamples reciben el volumen YA normalizado (0..1), no el crudo (-1000..1000)
    for normalized_input, _ in processor.resample_calls:
        np.testing.assert_allclose(normalized_input.pixel_array.flatten(), [0.0, 1.0])


def test_default_detail_levels_son_preview_y_full():
    processor = FakeVolumeProcessor()
    use_case = ProcessDicomSeries(processor)

    result = use_case.execute(ProcessDicomSeriesInput(dicom_paths=[Path("a.dcm")]))

    assert set(result.keys()) == {"preview", "full"}
