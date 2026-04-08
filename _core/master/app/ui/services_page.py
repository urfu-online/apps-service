"""Страница управления сервисами."""
from nicegui import ui
from typing import List, Optional

from app.ui.components.base import (
    create_header,
    create_icon_button,
    create_empty_state,
)


class ServicesPage:
    """Класс страницы управления сервисами."""

    def __init__(self):
        self.services: List = []
        self.filtered_services: List = []
        self.table: Optional[ui.table] = None
        self.search_input: Optional[ui.input] = None
        self.visibility_filter: Optional[ui.select] = None
        self.status_filter: Optional[ui.select] = None

    async def render(self):
        """Рендер страницы сервисов."""
        from app.main import app

        self.services = list(app.state.discovery.services.values())
        self.filtered_services = self.services.copy()

        # Заголовок
        create_header(title='Сервисы', show_refresh=True)

        # Фильтры
        with ui.row().classes('w-full px-6 gap-4 mt-4 items-end'):
            with ui.column().classes('flex-1'):
                self.search_input = ui.input(label='Поиск', placeholder='Название или описание') \
                    .props('outlined dense').classes('min-w-[200px]')
            with ui.column():
                self.visibility_filter = ui.select(
                    options=['all', 'public', 'internal'],
                    value='all',
                    label='Видимость',
                    on_change=lambda _: self._apply_filters()
                ).props('outlined dense')
            with ui.column():
                self.status_filter = ui.select(
                    options=['all', 'running', 'stopped', 'partial'],
                    value='all',
                    label='Статус',
                    on_change=lambda _: self._apply_filters()
                ).props('outlined dense')
            ui.button('Применить', icon='filter_list', on_click=self._apply_filters) \
                .props('unelevated')

        # Таблица сервисов
        await self._render_table()

    async def _render_table(self):
        """Рендер таблицы сервисов."""
        columns = [
            {'name': 'status', 'label': '', 'field': 'status', 'align': 'center', 'style': 'width: 50px'},
            {'name': 'name', 'label': 'Название', 'field': 'name', 'align': 'left'},
            {'name': 'version', 'label': 'Версия', 'field': 'version', 'align': 'center', 'style': 'width: 100px'},
            {'name': 'visibility', 'label': 'Видимость', 'field': 'visibility', 'align': 'center', 'style': 'width: 100px'},
            {'name': 'routing', 'label': 'Маршруты', 'field': 'routing', 'align': 'left'},
            {'name': 'actions', 'label': 'Действия', 'field': 'actions', 'align': 'center', 'style': 'width: 150px'},
        ]

        rows = self._build_table_rows(self.filtered_services)

        self.table = ui.table(
            columns=columns,
            rows=rows,
            row_key='name'
        ).classes('w-full px-6 mt-4').props('flat bordered').props(
            'pagination-label="Строк на странице" pagination-rows-per-page-options="5,10,20,50,100" '
            'pagination-rows-per-page=10'
        )

        self._add_action_slots()
        self._add_table_events()

        # Показываем empty state если нет данных
        if not rows:
            self.table.clear()
            with self.table:
                create_empty_state('📭', 'Нет сервисов для отображения')

    def _build_table_rows(self, services: List) -> List[dict]:
        """Построение строк таблицы."""
        rows = []
        for service in services:
            rows.append({
                'name': service.display_name or service.name,
                'version': service.version or '—',
                'visibility': service.visibility,
                'routing': self._format_routing(service.routing),
                'service_name': service.name,
                'status': service.status,
            })
        return rows

    def _format_routing(self, routing) -> str:
        """Форматирование маршрутов."""
        if not routing:
            return '—'
        
        parts = []
        for route in routing:
            if route.type == 'domain':
                parts.append(f"🌐 {route.domain}")
            elif route.type == 'subfolder':
                parts.append(f"📁 {route.base_domain}{route.path}")
            elif route.type == 'port':
                parts.append(f"🔌 :{route.port}")
        
        return ' | '.join(parts) if parts else '—'

    def _add_action_slots(self):
        """Добавление слотов для кнопок действий."""
        self.table.add_slot('body-cell-status', '''
            <q-td :props="props">
                <q-badge :color="props.row.status === 'running' ? 'positive' : 
                               props.row.status === 'stopped' ? 'negative' : 
                               props.row.status === 'partial' ? 'warning' : 'grey'">
                    {{ props.row.status === 'running' ? '●' : 
                       props.row.status === 'stopped' ? '●' : 
                       props.row.status === 'partial' ? '●' : '●' }}
                </q-badge>
            </q-td>
        ''')

        self.table.add_slot('body-cell-visibility', '''
            <q-td :props="props">
                <q-badge outline :color="props.row.visibility === 'public' ? 'info' : 'secondary'">
                    {{ props.row.visibility === 'public' ? '🌍 Публичный' : '🔒 Внутренний' }}
                </q-badge>
            </q-td>
        ''')

        self.table.add_slot('body-cell-actions', '''
            <q-td :props="props">
                <div class="row q-gutter-xs justify-center">
                    <q-btn flat dense round icon="visibility" 
                           @click="$parent.$emit('view', props.row)" 
                           color="primary" />
                    <q-btn flat dense round icon="refresh" 
                           @click="$parent.$emit('restart', props.row)" />
                    <q-btn flat dense round :icon="props.row.status === 'running' ? 'stop' : 'play_arrow'" 
                           @click="$parent.$emit('toggle', props.row)" 
                           :color="props.row.status === 'running' ? 'negative' : 'positive'" />
                </div>
            </q-td>
        ''')

    def _add_table_events(self):
        """Добавление обработчиков событий таблицы."""
        self.table.on('view', lambda e: ui.navigate.to(f'/services/{e.args["service_name"]}'))
        self.table.on('restart', lambda e: self._handle_action(e.args["service_name"], 'restart'))
        self.table.on('toggle', lambda e: self._handle_toggle(e.args))

    def _handle_toggle(self, args: dict):
        """Обработка кнопки запуска/остановки."""
        service_name = args["service_name"]
        status = args.get("status", "unknown")
        action = 'deploy' if status != 'running' else 'stop'
        self._handle_action(service_name, action)

    def _apply_filters(self):
        """Применение фильтров."""
        search = (self.search_input.value or '').lower() if self.search_input else ''
        visibility = self.visibility_filter.value if self.visibility_filter else 'all'
        status = self.status_filter.value if self.status_filter else 'all'

        filtered = self.services

        # Поиск по названию
        if search:
            filtered = [s for s in filtered 
                       if search in s.name.lower() 
                       or (s.display_name and search in s.display_name.lower())]

        # Фильтр по видимости
        if visibility != 'all':
            filtered = [s for s in filtered if s.visibility == visibility]

        # Фильтр по статусу
        if status != 'all':
            filtered = [s for s in filtered if s.status == status]

        self.filtered_services = filtered
        self._update_table()

    def _update_table(self):
        """Обновление таблицы."""
        if self.table:
            self.table.rows = self._build_table_rows(self.filtered_services)
            self.table.update()

    async def _handle_action(self, service_name: str, action: str):
        """Обработка действий с сервисом."""
        from app.main import app

        service = app.state.discovery.get_service(service_name)
        if not service:
            ui.notify(f'Сервис {service_name} не найден', type='negative')
            return

        actions = {
            'deploy': ('Запуск', app.state.docker.deploy_service),
            'restart': ('Перезапуск', app.state.docker.restart_service),
            'stop': ('Остановка', app.state.docker.stop_service),
        }

        action_label, action_func = actions.get(action, ('Действие', None))
        if not action_func:
            return

        ui.notify(f'{action_label} {service_name}...', type='info')
        result = await action_func(service)

        if result.get('success'):
            ui.notify(f'{service_name}: {action_label.lower()} успешно', type='positive')
            ui.navigate.reload()
        else:
            msg = result.get('message', 'Неизвестная ошибка')
            ui.notify(f'Ошибка: {msg}', type='negative')


async def render_services_page():
    """Рендер страницы сервисов."""
    page = ServicesPage()
    await page.render()
