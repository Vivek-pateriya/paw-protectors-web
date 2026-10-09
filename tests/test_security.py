import os
import time
import pytest
from backend.security import hash_password,verify_password,issue_token,decode_token


def test_password_salted_and_verified():
    a,b=hash_password('CorrectPassword123'),hash_password('CorrectPassword123')
    assert a!=b
    assert verify_password('CorrectPassword123',a)
    assert not verify_password('wrong',a)
    assert not verify_password('anything','malformed')


def test_token_integrity_and_expiry(monkeypatch):
    monkeypatch.setenv('TOKEN_SECRET','test-secret-'*4)
    token=issue_token(23)
    assert decode_token(token)==23
    with pytest.raises(ValueError):
        decode_token(token[:-1]+('a' if token[-1]!='a' else 'b'))
    monkeypatch.setenv('TOKEN_TTL_SECONDS','-1')
    with pytest.raises(ValueError):
        decode_token(issue_token(23))


def test_secret_required(monkeypatch):
    monkeypatch.delenv('TOKEN_SECRET',raising=False)
    with pytest.raises(RuntimeError):
        issue_token(1)
