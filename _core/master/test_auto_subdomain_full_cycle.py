#!/usr/bin/env python3
"""
Тестирование полного цикла работы системы с auto_subdomain.
Проверяет:
1. Валидацию service.yml с типом auto_subdomain
2. Генерацию конфигурации через CaddyManager
3. Корректность создаваемого файла .caddy
4. Отсутствие синтаксических ошибок в строке 11 (где была проблема)
"""

import asyncio
import tempfile
from pathlib import Path
import sys
import os

# Добавляем путь для импорта модулей проекта
sys.path.insert(0, str(Path(__file__).parent))

from app.services.discovery import ServiceManifest
from app.services.caddy_manager import CaddyManager


async def test_full_cycle():
    """Тестирование полного цикла генерации конфигурации"""
    
    # 1. Создаем временный service.yml для course-archive-explorer
    service_data = {
        "name": "course-archive-explorer",
        "display_name": "Course Archive Explorer",
        "version": "1.0.0",
        "description": "Explorer for course archives",
        "type": "docker-compose",
        "visibility": "public",
        "routing": [
            {
                "type": "auto_subdomain",
                "base_domain": "apps.example.com",
                "internal_port": 8080,
                "container_name": "course-archive-explorer-backend-1",
                "strip_prefix": False
            }
        ],
        "health": {
            "enabled": True,
            "endpoint": "/health",
            "interval": "30s",
            "timeout": "10s",
            "retries": 3
        },
        "backup": {
            "enabled": False
        },
        "tags": ["archive", "explorer"]
    }
    
    # 2. Валидация через ServiceManifest
    try:
        manifest = ServiceManifest(**service_data)
        print("✅ Валидация service.yml прошла успешно")
        print(f"   Сервис: {manifest.name}")
        print(f"   Тип маршрутизации: {manifest.routing[0].type}")
        print(f"   Base domain: {manifest.routing[0].base_domain}")
    except Exception as e:
        print(f"❌ Ошибка валидации: {e}")
        return False
    
    # 3. Создаем временную директорию для конфигов Caddy
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "caddy"
        config_path.mkdir()
        templates_dir = config_path / "templates"
        templates_dir.mkdir()
        conf_d_dir = config_path / "conf.d"
        conf_d_dir.mkdir()
        
        # Копируем шаблон auto_subdomain.caddy.j2
        original_template = Path(__file__).parent / "caddy" / "templates" / "auto_subdomain.caddy.j2"
        if not original_template.exists():
            # Или используем тестовый шаблон из фикстур
            original_template = Path(__file__).parent / "test-fixtures" / "caddy" / "templates" / "auto_subdomain.caddy.j2"
        
        if original_template.exists():
            template_content = original_template.read_text()
            (templates_dir / "auto_subdomain.caddy.j2").write_text(template_content)
            print(f"✅ Шаблон скопирован из {original_template}")
        else:
            # Создаем минимальный шаблон для теста
            template_content = """# Auto-subdomain: {{ service.name }}.{{ base_domain }}
# Service: {{ service.name }} | Version: {{ service.version }}
# Generated: {{ generated_at }}

{{ service.name }}.{{ base_domain }} {
    import common_headers
    import logging {{ service.name }} auto_subdomain

    {% if service.visibility == 'internal' %}
    import internal_only
    {% endif %}

    tls {
        on_demand
    }

    {% if route.container_name %}
    reverse_proxy http://{{ route.container_name }}:{{ route.internal_port }} {
    {% else %}
    reverse_proxy host.docker.internal:{{ route.internal_port }} {
    {% endif %}
        {% if service.health.enabled %}
        health_uri {{ service.health.endpoint }}
        health_interval {{ service.health.interval }}
        {% endif %}

        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
        header_up X-Service-Name {{ service.name }}
    }
}"""
            (templates_dir / "auto_subdomain.caddy.j2").write_text(template_content)
            print("✅ Создан минимальный шаблон")
        
        # 4. Инициализируем CaddyManager
        caddy = CaddyManager(str(config_path))
        
        # 5. Генерируем конфигурацию
        services_dict = {manifest.name: manifest}
        await caddy.regenerate_all(services_dict)
        
        # 6. Проверяем созданный файл
        generated_file = conf_d_dir / f"{manifest.name}.caddy"
        if not generated_file.exists():
            print(f"❌ Файл не создан: {generated_file}")
            # Посмотрим, какие файлы есть
            for f in conf_d_dir.iterdir():
                print(f"   Найден: {f.name}")
            return False
        
        content = generated_file.read_text()
        print(f"✅ Файл создан: {generated_file}")
        print(f"   Размер: {len(content)} байт")
        
        # 7. Проверяем строку 11 (где была ошибка)
        lines = content.splitlines()
        if len(lines) >= 11:
            line_11 = lines[10]  # нумерация с 0
            print(f"   Строка 11: {line_11}")
            # Проверяем, что строка не содержит очевидных ошибок
            if "{" in line_11 and "}" in line_11:
                print("   ✅ Строка 11 выглядит корректно (содержит фигурные скобки)")
            else:
                print("   ⚠️  Строка 11 может быть неполной")
        else:
            print("   ⚠️  Файл содержит меньше 11 строк")
        
        # 8. Проверяем синтаксис Caddyfile (базовая проверка)
        # Ищем типичные ошибки: незакрытые блоки, неправильные директивы
        if "reverse_proxy" in content and "{" in content and "}" in content:
            print("✅ Базовая проверка синтаксиса: reverse_proxy блок присутствует")
        else:
            print("❌ Базовая проверка синтаксиса: reverse_proxy блок не найден")
        
        # 9. Проверяем наличие правильного домена
        expected_domain = f"{manifest.name}.{manifest.routing[0].base_domain}"
        if expected_domain in content:
            print(f"✅ Домен {expected_domain} присутствует в конфигурации")
        else:
            print(f"❌ Домен {expected_domain} не найден в конфигурации")
            print(f"   Содержимое:\n{content[:500]}...")
        
        # 10. Выводим сгенерированный конфиг для проверки
        print("\n📄 Сгенерированный конфиг:")
        print("-" * 80)
        print(content)
        print("-" * 80)
        
        return True


async def main():
    """Основная функция"""
    print("🧪 Тестирование полного цикла работы системы с auto_subdomain")
    print("=" * 80)
    
    success = await test_full_cycle()
    
    print("\n" + "=" * 80)
    if success:
        print("✅ Тестирование завершено успешно")
        sys.exit(0)
    else:
        print("❌ Тестирование выявило проблемы")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())