from pathlib import Path
from typing import Protocol

from processing.domain.entities import Volume


class VolumeSerializer(Protocol):
    def save(self, volume: Volume, path: Path) -> None:
        """Serializa el volumen a disco en `path`. El formato concreto (y la
        extension esperada de `path`) lo define el adaptador -- ver
        infrastructure/dicom/simpleitk_volume_serializer.py."""
        ...
