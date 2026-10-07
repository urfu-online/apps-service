"""Харнесс T10: boundary в отдельном процессе — exit 1/2/3 реальными запусками.

Запуск: ``python tests/fixtures/boundary_cli.py <command> [общие опции…]``.

Команды:

- ``ctx`` — собирает ``build_ctx`` лениво (как это в P2 будут делать настоящие
  команды): нет ops-конфига → ``config_not_found`` (exit 3), битый
  ``--project-dir`` → ``invalid_value`` (exit 2), валидный проект → exit 0
  без вывода;
- ``boom`` — бросает ``ValueError`` → ``internal_error`` (exit 1), traceback
  только при ``--verbose``.

Через ``platform2`` эти сценарии в P1 недостижимы (заглушки §7.5 не собирают
``Ctx``), поэтому exit-коды 1/3 и настоящий ``invalid_value`` проверяются этим
харнессом — тем же boundary ``run_app``, что и в приложении; in-process-контур
остаётся в ``tests/test_boundary.py``/``tests/test_ctx.py``.
"""

from __future__ import annotations

import sys

from apps_platform.cli import build_ctx, create_app, extract_global_opts, run_app


def main(argv: list[str] | None = None) -> int:
    """Приложение с командами ``ctx``/``boom`` + boundary ``run_app``."""
    opts, remainder = extract_global_opts(list(sys.argv[1:] if argv is None else argv))
    app = create_app()

    @app.command()
    def ctx() -> None:
        """Собирает Ctx: config_not_found(3)/invalid_value(2)/успех(0)."""
        build_ctx(opts, system_config_paths=())

    @app.command()
    def boom() -> None:
        """Неожиданное исключение → internal_error (exit 1)."""
        raise ValueError("boom")

    return run_app(app, remainder, opts)


if __name__ == "__main__":
    raise SystemExit(main())
