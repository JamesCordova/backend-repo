from dataclasses import dataclass
from pathlib import Path

from processing.application.ports.volume_processor import VolumeProcessor
from processing.domain.entities import Volume
from processing.domain.hounsfield import normalize_hounsfield

# Ventana de Hounsfield units para tejido blando -- ver seccion 2 del documento
# de arquitectura. Configurable por caso de uso si mas adelante se necesitan
# otras ventanas (ej. hueso: 400 a 1800 HU).
_DEFAULT_MIN_HU = -1000.0
_DEFAULT_MAX_HU = 1000.0

# LOD (niveles de detalle, seccion 2 del documento de arquitectura): "preview"
# a un espaciado mas grueso (menos voxeles, carga casi instantanea) y "full"
# a resolucion completa, on-demand. El nombre es el detail_level que se
# registra despues en la tabla volumes (seccion 21).
DEFAULT_DETAIL_LEVELS: dict[str, float] = {"preview": 4.0, "full": 1.0}


@dataclass(frozen=True, slots=True)
class ProcessDicomSeriesInput:
    dicom_paths: list[Path]
    min_hu: float = _DEFAULT_MIN_HU
    max_hu: float = _DEFAULT_MAX_HU
    # detail_level -> target_spacing_mm. Un solo elemento tambien es valido
    # (ej. {"full": 1.0}) si algun caso de uso no necesita preview.
    detail_levels: dict[str, float] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.detail_levels is None:
            object.__setattr__(self, "detail_levels", dict(DEFAULT_DETAIL_LEVELS))


class ProcessDicomSeries:
    """Orquesta el pipeline de la seccion 2 del documento de arquitectura:
    ingesta -> normalizacion HU -> resampling isotropico, una vez por cada
    nivel de detalle solicitado. La carga y normalizacion se hacen una sola
    vez (son el costo mayor); solo el resampling final se repite por nivel.
    """

    def __init__(self, processor: VolumeProcessor) -> None:
        self._processor = processor

    def execute(self, data: ProcessDicomSeriesInput) -> dict[str, Volume]:
        raw = self._processor.load_series(data.dicom_paths)
        normalized = normalize_hounsfield(raw, data.min_hu, data.max_hu)
        return {
            detail_level: self._processor.resample_to_isotropic(normalized, spacing_mm)
            for detail_level, spacing_mm in data.detail_levels.items()
        }
