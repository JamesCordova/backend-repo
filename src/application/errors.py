class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class StudyNotFoundError(Exception):
    pass


class StudyAccessDeniedError(Exception):
    pass


class MissingUploadedFileError(Exception):
    """Se intento confirmar la subida de un estudio pero al menos uno de los
    archivos declarados no existe realmente en el storage -- nunca se confia
    en 'ya subi todo' del cliente sin verificarlo (seccion 6.2 del documento
    de clean architecture)."""


class VolumeNotReadyError(Exception):
    """El estudio existe pero todavia no tiene un volumen procesado
    disponible (status distinto de 'ready', o el worker aun no registro la
    fila en volumes)."""


class SessionNotFoundError(Exception):
    pass


class SessionAccessDeniedError(Exception):
    pass


class SusQuestionnaireNotFoundError(Exception):
    pass


class SusQuestionnaireAccessDeniedError(Exception):
    pass


class InvalidRangeError(Exception):
    """El header HTTP Range que mando el cliente esta mal formado o no es
    satisfacible contra el tamano real del recurso (RFC 7233). Lleva
    total_size para que la capa HTTP arme el header Content-Range de la
    respuesta 416 sin tener que volver a consultar el volumen."""

    def __init__(self, range_header: str, total_size: int) -> None:
        super().__init__(range_header)
        self.total_size = total_size
