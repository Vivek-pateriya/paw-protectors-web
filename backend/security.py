"""Salted scrypt passwords and expiring HMAC-signed bearer sessions."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return f'scrypt${salt.hex()}${digest.hex()}'


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, expected = stored.split('$')
        if scheme != 'scrypt':
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


def secret() -> bytes:
    value = os.environ.get('TOKEN_SECRET', '')
    if len(value) < 32 or value.startswith('REPLACE_'):
        raise RuntimeError('Configure TOKEN_SECRET with at least 32 random characters')
    return value.encode()


def issue_token(user_id: int) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({
        'sub': user_id, 'exp': int(time.time()) + int(os.getenv('TOKEN_TTL_SECONDS', '28800')),
        'nonce': secrets.token_hex(8),
    }, separators=(',', ':')).encode()).rstrip(b'=').decode()
    signature = hmac.new(secret(), payload.encode(), hashlib.sha256).hexdigest()
    return payload + '.' + signature


def decode_token(token: str) -> int:
    try:
        payload, signature = token.split('.')
        expected = hmac.new(secret(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError('Invalid session')
        data = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        if data['exp'] <= time.time():
            raise ValueError('Expired session')
        return int(data['sub'])
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid session') from exc
