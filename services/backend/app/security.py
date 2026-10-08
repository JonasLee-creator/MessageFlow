import base64
import hashlib
import hmac
import os
import secrets
from datetime import timedelta
from pathlib import Path

import jwt
from cryptography.fernet import Fernet
from fastapi import HTTPException
from .db import now


def secret():
    configured = os.getenv("SECRET_KEY")
    if configured:
        if len(configured) < 32:
            raise RuntimeError("SECRET_KEY must contain at least 32 characters")
        return configured
    # Persistent private development key, excluded from source control.
    path = Path(".local-secret")
    if not path.exists():
        try:
            with path.open("x") as f:
                f.write(secrets.token_urlsafe(48))
        except FileExistsError:
            pass
    return path.read_text().strip()


def password_hash(password):
    salt = secrets.token_hex(16)
    value = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600000).hex()
    return f"{salt}:{value}"


def password_matches(password, encoded):
    salt, expected = encoded.split(":")
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600000).hex()
    return hmac.compare_digest(actual, expected)


def token(user_id):
    return jwt.encode({"sub": user_id, "exp": now() + timedelta(days=30), "iat": now()}, secret(), algorithm="HS256")


def decode(value):
    try:
        return jwt.decode(value, secret(), algorithms=["HS256"])["sub"]
    except (jwt.PyJWTError, KeyError):
        raise HTTPException(401, "登录已过期，请重新登录")


def vault():
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret().encode()).digest()))
