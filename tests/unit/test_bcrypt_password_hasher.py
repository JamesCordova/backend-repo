from infrastructure.security.bcrypt_password_hasher import BcryptPasswordHasher


def test_hash_no_es_el_texto_plano():
    hasher = BcryptPasswordHasher()
    assert hasher.hash("secret123") != "secret123"


def test_verify_acepta_password_correcto_y_rechaza_incorrecto():
    hasher = BcryptPasswordHasher()
    password_hash = hasher.hash("secret123")

    assert hasher.verify("secret123", password_hash) is True
    assert hasher.verify("otra-cosa", password_hash) is False
