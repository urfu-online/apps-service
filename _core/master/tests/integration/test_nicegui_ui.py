"""Тесты для NiceGUI UI компонентов."""
import pytest
from playwright.async_api import Page

import sys
from pathlib import Path

# Настройка пути к папке app для импорта модулей проекта
APP_DIR = Path(__file__).resolve().parents[3] / "app"
sys.path.insert(0, str(APP_DIR))


@pytest.mark.asyncio
async def test_main_page_components(page: Page):
    """Тест основных компонентов главной страницы."""
    # Переход на главную страницу
    await page.goto('http://localhost:8000/')
    
    # Проверка наличия основных элементов UI
    await page.wait_for_selector('text=Platform Manager', timeout=5000)
    
    # Проверяем наличие панели навигации
    await page.wait_for_selector('.nice-menu', timeout=5000)
    
    # Проверка кнопок/ссылок на главной странице
    services_nav_item = page.locator('text=Services')
    await services_nav_item.wait_for(state='visible')
    
    logs_nav_item = page.locator('text=Logs')
    await logs_nav_item.wait_for(state='visible')
    
    backups_nav_item = page.locator('text=Backups')
    await backups_nav_item.wait_for(state='visible')


@pytest.mark.asyncio
async def test_services_page_components(page: Page):
    """Тест компонентов страницы сервисов."""
    # Переход на страницу сервисов
    await page.goto('http://localhost:8000/services')
    
    # Проверка заголовка страницы
    await page.wait_for_selector('text=Services Overview', timeout=5000)
    
    # Проверка наличия таблицы сервисов
    services_table = page.locator('#services-table')
    await services_table.wait_for(state='visible')
    
    # Проверка столбцов таблицы
    name_col = page.locator('text=Name')
    await name_col.wait_for(state='visible')
    
    status_col = page.locator('text=Status')
    await status_col.wait_for(state='visible')
    
    version_col = page.locator('text=Version')
    await version_col.wait_for(state='visible')
    
    actions_col = page.locator('text=Actions')
    await actions_col.wait_for(state='visible')


@pytest.mark.asyncio
async def test_logs_page_components(page: Page):
    """Тест компонентов страницы логов."""
    # Переход на страницу логов
    await page.goto('http://localhost:8000/logs')
    
    # Проверка заголовка страницы
    await page.wait_for_selector('text=Service Logs', timeout=5000)
    
    # Проверка наличия списка сервисов для выбора
    service_select = page.locator('[data-testid="service-select"]')
    await service_select.wait_for(state='visible')
    
    # Проверка наличия поля поиска
    search_input = page.locator('[data-testid="log-search-input"]')
    await search_input.wait_for(state='visible')
    
    # Проверка наличия компонента отображения логов
    logs_viewer = page.locator('#logs-viewer')
    await logs_viewer.wait_for(state='visible')


@pytest.mark.asyncio
async def test_backups_page_components(page: Page):
    """Тест компонентов страницы бэкапов."""
    # Переход на страницу бэкапов
    await page.goto('http://localhost:8000/backups')
    
    # Проверка заголовка страницы
    await page.wait_for_selector('text=Service Backups', timeout=5000)
    
    # Проверка наличия таблицы бэкапов
    backups_table = page.locator('#backups-table')
    await backups_table.wait_for(state='visible')
    
    # Проверка столбцов таблицы
    backup_name_col = page.locator('text=Backup Name')
    await backup_name_col.wait_for(state='visible')
    
    service_col = page.locator('text=Service')
    await service_col.wait_for(state='visible')
    
    status_col = page.locator('text=Status')
    await status_col.wait_for(state='visible')
    
    created_col = page.locator('text=Created')
    await created_col.wait_for(state='visible')

    # Проверка наличия кнопки создания бэкапа
    create_backup_btn = page.locator('text=Create Backup')
    await create_backup_btn.wait_for(state='visible')


@pytest.mark.asyncio
async def test_theme_consistency(page: Page):
    """Тест согласованности темы."""
    # Проверка темы на главной странице
    await page.goto('http://localhost:8000/')
    
    # Убедиться, что компоненты отображаются с светлой темой (настройка из main.py)
    body = page.locator('body')
    body_classes = await body.get_attribute('class')
    assert body_classes and 'light-theme' in body_classes or 'dark-theme' not in body_classes
    
    # Проверка согласованности шрифтов и оформления на других страницах
    await page.goto('http://localhost:8000/services')
    
    # Проверить те же элементы на странице сервисов
    services_body = page.locator('body')
    services_body_classes = await services_body.get_attribute('class')
    assert services_body_classes and 'light-theme' in services_body_classes or 'dark-theme' not in services_body_classes