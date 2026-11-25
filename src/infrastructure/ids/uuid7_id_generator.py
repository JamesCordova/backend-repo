"""UUIDv7 (RFC 9562) en vez de v4: los primeros 48 bits son un timestamp en
milisegundos, el resto es aleatorio. Sigue siendo un UUID valido, generable sin
coordinacion entre servicios (api-repo y worker-repo pueden generar ids sin
hablarse), pero al ser mayormente creciente en el tiempo se comporta bien como
llave de indice -- un UUIDv4 aleatorio fragmenta el B-tree del indice primario
en Postgres a medida que la tabla crece, porque cada insercion cae en una
posicion al azar en vez de al final.
"""

from uuid import UUID

from uuid6 import uuid7

from application.ports.id_generator import IdGenerator


class Uuid7IdGenerator(IdGenerator):
    def generate(self) -> UUID:
        return uuid7()
