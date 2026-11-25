import bcrypt

from application.ports.password_hasher import PasswordHasher

# bcrypt trunca en 72 bytes por diseño del algoritmo -- se valida largo maximo
# de password en el schema de entrada (RegisterRequest), esto es un limite
# duro adicional para nunca pasarle a la libreria mas de lo que soporta.
_MAX_PASSWORD_BYTES = 72


class BcryptPasswordHasher(PasswordHasher):
    def hash(self, plain_password: str) -> str:
        raw = plain_password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
        return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("ascii")

    def verify(self, plain_password: str, password_hash: str) -> bool:
        raw = plain_password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
        return bcrypt.checkpw(raw, password_hash.encode("ascii"))
