#!/usr/bin/env python3
"""
Тестирование шаблона auto_subdomain.caddy.j2
Проверяет генерацию конфигураций для различных сценариев.
"""

import os
import sys
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

def load_template():
    """Загружает шаблон из директории templates."""
    template_dir = os.path.join(os.path.dirname(__file__), '_core/caddy/templates')
    env = Environment(loader=FileSystemLoader(template_dir), trim_blocks=True, lstrip_blocks=True)
    return env.get_template('auto_subdomain.caddy.j2')

def render_scenario(name, context):
    """Рендерит шаблон с заданным контекстом и выводит результат."""
    template = load_template()
    output = template.render(**context)
    print(f"\n{'='*60}")
    print(f"Сценарий: {name}")
    print(f"{'='*60}")
    print(output)
    return output

def test_scenarios():
    """Основные тестовые сценарии."""
    base_context = {
        'generated_at': datetime.utcnow().isoformat(),
        'base_domain': 'example.com',
    }
    
    # Сценарий 1: Внешний сервис с container_name и health check
    context1 = {
        **base_context,
        'service': {
            'name': 'myapp',
            'version': '1.0.0',
            'visibility': 'public',
            'health': {
                'enabled': True,
                'endpoint': '/health',
                'interval': '30s',
            }
        },
        'route': {
            'container_name': 'myapp-container',
            'internal_port': 8080,
        }
    }
    
    # Сценарий 2: Внешний сервис без container_name (использует host.docker.internal)
    context2 = {
        **base_context,
        'service': {
            'name': 'external-api',
            'version': '2.0.0',
            'visibility': 'public',
            'health': {
                'enabled': False,
            }
        },
        'route': {
            'container_name': None,
            'internal_port': 3000,
        }
    }
    
    # Сценарий 3: Внутренний сервис (internal) с health check
    context3 = {
        **base_context,
        'service': {
            'name': 'internal-service',
            'version': '0.1.0',
            'visibility': 'internal',
            'health': {
                'enabled': True,
                'endpoint': '/healthz',
                'interval': '10s',
            }
        },
        'route': {
            'container_name': 'internal-container',
            'internal_port': 5000,
        }
    }
    
    # Сценарий 4: Сервис без health check (проверяем отсутствие health_uri)
    context4 = {
        **base_context,
        'service': {
            'name': 'legacy-app',
            'version': '0.5.0',
            'visibility': 'public',
            'health': {
                'enabled': False,
            }
        },
        'route': {
            'container_name': 'legacy-container',
            'internal_port': 80,
        }
    }
    
    scenarios = [
        ("Внешний сервис с container_name и health check", context1),
        ("Внешний сервис без container_name", context2),
        ("Внутренний сервис с health check", context3),
        ("Сервис без health check", context4),
    ]
    
    outputs = []
    for name, context in scenarios:
        output = render_scenario(name, context)
        outputs.append((name, output))
    
    return outputs

def validate_outputs(outputs):
    """Проверяет сгенерированные конфигурации на наличие ожидаемых паттернов."""
    errors = []
    for name, output in outputs:
        # Проверяем, что есть блок reverse_proxy
        if 'reverse_proxy' not in output:
            errors.append(f"{name}: отсутствует reverse_proxy")
        
        # Проверяем, что есть tls { on_demand }
        if 'tls { on_demand }' not in output:
            errors.append(f"{name}: отсутствует tls on_demand")
        
        # Проверяем, что домен корректный
        if '.example.com {' not in output:
            errors.append(f"{name}: некорректный домен")
        
        # Проверяем импорты
        if 'import common_headers' not in output:
            errors.append(f"{name}: отсутствует import common_headers")
        if 'import logging' not in output:
            errors.append(f"{name}: отсутствует import logging")
    
    if errors:
        print("\n❌ Ошибки валидации:")
        for err in errors:
            print(f"  - {err}")
        return False
    else:
        print("\n✅ Все сценарии прошли базовую валидацию.")
        return True

if __name__ == '__main__':
    print("Тестирование шаблона auto_subdomain.caddy.j2")
    print("=" * 60)
    
    try:
        outputs = test_scenarios()
        success = validate_outputs(outputs)
        
        if success:
            print("\n✅ Тестирование завершено успешно.")
            sys.exit(0)
        else:
            print("\n❌ Тестирование выявило проблемы.")
            sys.exit(1)
    except Exception as e:
        print(f"\n⚠️  Ошибка во время тестирования: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)