"""Тесты валидации Settings.SECRET_KEY (шаг 2 плана исправлений).

Строгая проверка SECRET_KEY (длина ≥ 32, непустой, не placeholder) применяется
только в ENV=production. В dev/staging допустимы слабые ключи, чтобы не
блокировать локальный запуск. Тесты ``test_secret_key_*_rejected`` явно
выставляют ``ENV=production`` через окружение.
"""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError


def _make_settings(**overrides):
    from app.config import Settings

    env = {
        "SECRET_KEY": "x" * 32,
        "ENV": "dev",
    }
    env.update(overrides)
    with patch.dict(os.environ, env, clear=False):
        return Settings()


def test_secret_key_empty_rejected_in_production():
    with pytest.raises(ValidationError):
        _make_settings(ENV="production", SECRET_KEY="")


def test_secret_key_default_placeholder_rejected_in_production():
    with pytest.raises(ValidationError):
        _make_settings(ENV="production", SECRET_KEY="change-me-in-production")


def test_secret_key_too_short_rejected_in_production():
    with pytest.raises(ValidationError):
        _make_settings(ENV="production", SECRET_KEY="short")


def test_secret_key_short_accepted_in_dev():
    # В dev слабый ключ допустим (позволяет быстро запустить локально).
    s = _make_settings(ENV="dev", SECRET_KEY="short")
    assert s.SECRET_KEY == "short"


def test_secret_key_strong_accepted_in_production():
    strong = "a" * 40
    s = _make_settings(ENV="production", SECRET_KEY=strong)
    assert s.SECRET_KEY == strong


def test_env_field_defaults_to_dev():
    s = _make_settings()
    assert s.ENV == "dev"
