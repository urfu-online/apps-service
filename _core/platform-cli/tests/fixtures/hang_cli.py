"""Харнесс T10: висящая команда через exception boundary — реальный SIGINT → 130.

Запуск: ``python tests/fixtures/hang_cli.py <marker-path> [общие опции…]``.

Команда ``hang`` сначала пишет маркер готовности (тест шлёт SIGINT только после
него — детерминированность) и затем спит; ``KeyboardInterrupt`` от SIGINT
гасится boundary :func:`apps_platform.cli.run_app` (T9) → ``cancelled`` →
exit 130 без traceback. Заглушки §7.5 из ``create_app`` в argv не участвуют.

P1-команды ``platform2`` мгновенны, поэтому SIGINT проверяется на этом
синтетическом приложении с тем же boundary, что и приложение (см. отчёт T10).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from apps_platform.cli import create_app, extract_global_opts, run_app


def main(argv: list[str] | None = None) -> int:
    """Висячая команда ``hang`` + boundary ``run_app`` (возвращает exit-код)."""
    opts, remainder = extract_global_opts(list(sys.argv[1:] if argv is None else argv))
    marker = Path(remainder[0]) if remainder else None
    app = create_app()

    @app.command()
    def hang() -> None:
        """Маркер готовности, затем сон до SIGINT (boundary → cancelled, 130)."""
        if marker is not None:
            marker.write_text("ready", encoding="utf-8")
        time.sleep(60)

    return run_app(app, ["hang"], opts)


if __name__ == "__main__":
    raise SystemExit(main())
