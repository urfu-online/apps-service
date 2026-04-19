"""apps_platform.caddy_parser

Небольшой (эвристический) парсер Caddyfile-конфигурации.

Цель: извлечь реальные домены/пути из сгенерированных `.caddy` файлов в `conf.d/`.
Парсер намеренно без внешних зависимостей и НЕ является полноценным парсером Caddyfile.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def parse_caddy_config(service_name: str, caddy_path: Path) -> list[dict[str, Any]]:
    """Парсинг Caddy-конфигурации для получения реальных доменов и путей.

    Парсер учитывает вложенные блоки за счёт балансировки фигурных скобок.

    Ограничения текущей реализации:
    - поддерживается один site label на строке (варианты вроде `example.com www.example.com {` или
      `example.com, www... {` будут распознаны частично)
    - не учитываются директивы `route`/`handle_path` и сложные конструкции Caddyfile
      (если появятся — нужен полноценный парсер)

    TODO(arch): Вместо чтения файлов и эвристик в CLI — получать актуальные URL через API master service
    (например, отдельный endpoint `GET /api/services/{service_name}/urls`).
    """

    routes: list[dict[str, Any]] = []

    # Ищем .caddy файлы в conf.d
    conf_d = caddy_path / "conf.d"
    if not conf_d.exists():
        return routes

    # Паттерны
    site_start_re = re.compile(r"^\s*([^\s{]+)\s*\{")
    handle_start_re = re.compile(r"^\s*handle(?:\s+([^\s{]+))?\s*\{")
    reverse_proxy_re = re.compile(r"\breverse_proxy\s+(?:http://)?([^\s]+)")

    def current_domain(stack: list[dict[str, Any]]) -> str | None:
        for ctx in reversed(stack):
            if ctx.get("type") == "site":
                return ctx.get("domain")
        return None

    def current_handle_path(stack: list[dict[str, Any]]) -> str | None:
        for ctx in reversed(stack):
            if ctx.get("type") == "handle":
                return ctx.get("path")
        return None

    def set_backend_for_last_route(*, domain: str, path: str | None, backend: str) -> None:
        # Ищем последнюю запись домена/подпапки и дописываем backend
        for entry in reversed(routes):
            if path is None and entry.get("type") == "domain" and entry.get("domain") == domain:
                entry["backend"] = backend
                return
            if (
                path is not None
                and entry.get("type") == "subfolder"
                and entry.get("domain") == domain
                and entry.get("path") == path
            ):
                entry["backend"] = backend
                return

    for caddy_file in conf_d.glob("*.caddy"):
        try:
            content = caddy_file.read_text()

            # Проверяем, относится ли файл к сервису
            if service_name not in caddy_file.name and service_name not in content:
                continue

            stack: list[dict[str, Any]] = []

            for raw_line in content.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("#"):
                    continue
                if line.startswith("import "):
                    # import не является блоком сайта и не влияет на стек
                    continue

                # Сколько скобок на строке — для балансировки вложенных блоков
                open_braces = line.count("{")
                close_braces = line.count("}")

                pushed = 0

                # handle { ... } / handle /path/* { ... }
                handle_match = handle_start_re.match(line)
                if handle_match and open_braces:
                    path = handle_match.group(1)
                    stack.append({"type": "handle", "path": path})
                    pushed += 1

                    domain = current_domain(stack)
                    if domain and path:
                        routes.append(
                            {
                                "type": "subfolder",
                                "domain": domain,
                                "path": path,
                                "source_file": caddy_file.name,
                            }
                        )

                # site block: example.com { ... }
                site_match = site_start_re.match(line)
                if site_match and open_braces and not handle_match:
                    domain = site_match.group(1)
                    # Исключаем служебные блоки
                    if domain not in ("{", "import") and domain != "handle":
                        stack.append({"type": "site", "domain": domain})
                        pushed += 1
                        routes.append({"type": "domain", "domain": domain, "source_file": caddy_file.name})

                # Если открыли "анонимные" блоки (tls {, route {, log { и т.п.) — учитываем их в стеке
                extra_opens = max(open_braces - pushed, 0)
                for _ in range(extra_opens):
                    stack.append({"type": "other"})

                # reverse_proxy — привязываем к ближайшему site/handle в стеке
                proxy_match = reverse_proxy_re.search(line)
                if proxy_match:
                    domain = current_domain(stack)
                    if domain:
                        backend = proxy_match.group(1)
                        path = current_handle_path(stack)
                        set_backend_for_last_route(domain=domain, path=path, backend=backend)

                # Закрываем блоки
                for _ in range(min(close_braces, len(stack))):
                    stack.pop()

        except Exception:
            continue

    return routes


# Backward-compat alias for older imports.
_parse_caddy_config = parse_caddy_config

