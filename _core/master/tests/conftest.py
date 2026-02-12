"""Фикстуры pytest для тестирования приложения master."""
import pytest


@pytest.fixture
def client():
    """Фикстура для тестового клиента."""
    pass


@pytest.fixture
def event_loop():
    """Фикстура для event loop в асинхронных тестах."""
    pass