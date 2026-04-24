"""Базовые UI компоненты для Platform Manager."""
from nicegui import ui
from typing import Callable, Optional


def create_header(title: str = "🚀 Platform Manager", show_refresh: bool = True,
                  on_refresh: Optional[Callable] = None, show_navigation: bool = True) -> None:
    """Создает стандартный заголовок страницы.
    
    Args:
        title: Заголовок страницы
        show_refresh: Показывать кнопку обновления
        on_refresh: Callback при нажатии на refresh
        show_navigation: Показывать навигационное меню
    """
    with ui.header().classes('w-full px-6 py-3'):
        with ui.column().classes('w-full'):
            # Верхняя строка: заголовок и кнопки
            with ui.row().classes('w-full items-center'):
                ui.label(title).classes('text-h5 font-medium')
                ui.space()
                with ui.row().classes('gap-2'):
                    if show_refresh:
                        refresh_action = on_refresh if on_refresh else lambda: ui.navigate.reload()
                        ui.button(icon='refresh', on_click=refresh_action) \
                            .props('flat dense round').tooltip('Обновить')
            
            # Навигационная панель
            if show_navigation:
                with ui.row().classes('w-full mt-2 gap-1'):
                    ui.button('Главная', icon='home', on_click=lambda: ui.navigate.to('/')) \
                        .props('flat dense').classes('text-capitalize')
                    ui.button('Сервисы', icon='apps', on_click=lambda: ui.navigate.to('/services')) \
                        .props('flat dense').classes('text-capitalize')
                    ui.button('Логи', icon='description', on_click=lambda: ui.navigate.to('/logs')) \
                        .props('flat dense').classes('text-capitalize')
                    ui.button('Бэкапы', icon='backup', on_click=lambda: ui.navigate.to('/backups')) \
                        .props('flat dense').classes('text-capitalize')


def create_page_title(title: str, subtitle: Optional[str] = None) -> None:
    """Создает заголовок страницы с подзаголовком."""
    with ui.column().classes('w-full mb-4'):
        ui.label(title).classes('text-h4 font-medium')
        if subtitle:
            ui.label(subtitle).classes('text-subtitle1 text-grey-7')


def create_stat_card(label: str, value: str, icon: str = '',
                     color: str = 'primary') -> None:
    """Создает карточку статистики.
    
    Args:
        label: Подпись статистики
        value: Значение
        icon: Иконка (emoji или material icon)
        color: Цвет акцента (primary, positive, negative, warning, info)
    """
    color_classes = {
        'primary': 'text-primary bg-primary-1',
        'positive': 'text-positive bg-positive-1',
        'negative': 'text-negative bg-negative-1',
        'warning': 'text-warning bg-warning-1',
        'info': 'text-info bg-info-1',
    }
    
    with ui.card().classes(f'p-4 min-w-[140px] flex-1 {color_classes.get(color, "")}'):
        with ui.row().classes('w-full items-center justify-between'):
            if icon:
                ui.label(icon).classes('text-2xl')
            ui.label(value).classes('text-h3 font-bold')
        ui.label(label).classes('text-subtitle2 text-grey-7 mt-1')


def create_section_card(title: str, icon: str = '') -> ui.card:
    """Создает карточку-секцию для группировки контента.
    
    Args:
        title: Заголовок секции
        icon: Иконка секции
    """
    card = ui.card().classes('w-full p-4')
    with card:
        with ui.row().classes('w-full items-center mb-3'):
            if icon:
                ui.label(icon).classes('text-xl mr-2')
            ui.label(title).classes('text-h6 font-medium')
    return card


def create_icon_button(icon: str, on_click: Callable, color: str = 'default',
                       tooltip: Optional[str] = None) -> ui.button:
    """Создает кнопку-иконку.
    
    Args:
        icon: Material icon или emoji
        on_click: Callback
        color: Цвет
        tooltip: Подсказка
    """
    btn = ui.button(icon=icon, on_click=on_click).props('flat dense round')
    if color != 'default':
        btn.props(f'color={color}')
    if tooltip:
        btn.tooltip(tooltip)
    return btn


def create_empty_state(icon: str, message: str, action_label: Optional[str] = None,
                       on_action: Optional[Callable] = None) -> None:
    """Создает состояние "пусто" для отображения когда нет данных.
    
    Args:
        icon: Иконка состояния
        message: Сообщение пользователю
        action_label: Текст кнопки действия
        on_action: Callback действия
    """
    with ui.column().classes('w-full items-center justify-center py-12'):
        ui.label(icon).classes('text-6xl text-grey-5 mb-4')
        ui.label(message).classes('text-subtitle1 text-grey-7 text-center')
        if action_label and on_action:
            ui.button(action_label, on_click=on_action).props('unelevated').classes('mt-4')


def create_status_chip(status: str) -> ui.chip:
    """Создает чип статуса.
    
    Args:
        status: Статус (running, stopped, healthy, unhealthy, public, internal)
    """
    status_config = {
        'running': {'label': 'Запущен', 'icon': 'play_circle', 'color': 'positive'},
        'stopped': {'label': 'Остановлен', 'icon': 'stop_circle', 'color': 'negative'},
        'partial': {'label': 'Частично', 'icon': 'remove_circle', 'color': 'warning'},
        'unknown': {'label': 'Неизвестно', 'icon': 'help_circle', 'color': 'grey'},
        'healthy': {'label': 'Здоров', 'icon': 'check_circle', 'color': 'positive'},
        'unhealthy': {'label': 'Болен', 'icon': 'error', 'color': 'negative'},
        'public': {'label': 'Публичный', 'icon': 'public', 'color': 'info'},
        'internal': {'label': 'Внутренний', 'icon': 'lock', 'color': 'secondary'},
    }
    
    config = status_config.get(status, status_config['unknown'])
    return ui.chip(config['label'], icon=config['icon']).props(f'color={config["color"]}')
