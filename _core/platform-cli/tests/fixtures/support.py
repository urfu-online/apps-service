"""Помощники subprocess-тестов T10 (``tests/test_cli_v2.py``, ``tests/test_tty.py``).

Запускают установленный entry ``platform2`` (и харнессы ``fixtures/*.py``)
отдельными процессами — реальный контур ``[project.scripts]``, без docker/сети
и без глобальных путей:

- :func:`make_env` — детерминированное окружение: конфиг-env (``OPS_*``,
  ``PLATFORM_*``) снят, ``XDG_CONFIG_HOME`` и ``COLUMNS``/``LINES``/``TERM``
  контролируются, дефолты прогона — ``NO_COLOR=1`` и ``PYTHONUTF8=1``;
  значение ``None`` в overrides удаляет переменную (для тестов цвета);
- :func:`run_platform2`/:func:`run_fixture` — ``subprocess.run`` с
  ``capture_output`` и таймаутом ``TIMEOUT`` (CI не виснет);
- :func:`run_platform2_tty` — схема **двух pty**: stdout и stderr подключены к
  разным slave-парам, поэтому слоты каналов различимы (master'ы читаются
  отдельно), а ``isatty()`` истинно для обоих потоков; ``stdin`` — ``/dev/null``
  (P1-команды ввод не читают, политика цвета §12.1 зависит только от
  stdout/stderr). Переводы строк pty (``\\r\\n``) нормализуются в ``\\n``;
- :func:`make_ops_project` — tmp-проект: маркер ``.ops-root``,
  ``.ops-config.yml``, заглушка ``services/public/demo/docker-compose.yml``;
- :func:`normalize_help`/:func:`strip_ansi` — нормализация help-вывода rich
  (рамки/пробелы/ANSI) для проверок содержимого независимо от ширины и TTY.
"""

from __future__ import annotations

import contextlib
import os
import pty
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

#: Таймаут одного запуска: тест падает, а не виснет (детерминизм CI).
TIMEOUT = 30.0

#: Конфиг-env, который тесты изолируют (как в ``test_ctx``/``test_boundary``).
ISOLATE_VARS: tuple[str, ...] = (
    "OPS_PROJECT_ROOT",
    "OPS_CONFIG_PATH",
    "PLATFORM_ENV",
    "PLATFORM_SSL_VERIFY",
    "PLATFORM_API_TOKEN",
)

#: ``platform2`` из ``pip install -e .``; ``None`` → тест падает с подсказкой.
PLATFORM2: str | None = shutil.which("platform2")

#: Директория фикстур (харнессы, golden) — для запуска из тестов.
FIXTURES_DIR: Path = Path(__file__).resolve().parent

#: Символы рамок rich — убираются :func:`normalize_help`.
_BOX_DRAWING: str = "─│┌┐└┘├┤┬┴┼╭╮╰╯═║╔╗╚╝╠╣╦╩╬"

#: ANSI-последовательности (цвет/стиль) — убираются :func:`strip_ansi`.
_ANSI_RE: re.Pattern[str] = re.compile(r"\x1b\[[0-9;]*m")


def require_platform2() -> str:
    """Абсолютный путь ``platform2`` или понятная ошибка настройки окружения."""
    if PLATFORM2 is None:
        raise AssertionError("platform2 не найден в PATH — выполните python -m pip install -e .")
    return PLATFORM2


def make_env(base: Path, overrides: Mapping[str, str | None] | None = None) -> dict[str, str]:
    """Детерминированное окружение subprocess-прогона.

    ``base`` — tmp-директория прогона (сюда уходит ``XDG_CONFIG_HOME``).
    ``overrides`` — правки после дефолтов: значение ``None`` удаляет ключ
    (например ``{"NO_COLOR": None, "TERM": "xterm"}`` — тест цветов на TTY).
    """
    env = {key: value for key, value in os.environ.items() if key not in ISOLATE_VARS}
    env["XDG_CONFIG_HOME"] = str(base / "xdg")
    env["NO_COLOR"] = "1"
    env["PYTHONUTF8"] = "1"
    env.pop("COLUMNS", None)
    env.pop("LINES", None)
    env.pop("TERM", None)
    for key, value in (overrides or {}).items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return env


def run_platform2(
    args: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    binary: bool = False,
) -> subprocess.CompletedProcess:
    """Запуск ``platform2`` отдельным процессом (каналы перехвачены, таймаут)."""
    return _run([require_platform2(), *args], cwd=cwd, env=env, binary=binary)


def run_fixture(
    script: str,
    args: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    binary: bool = False,
) -> subprocess.CompletedProcess:
    """Запуск харнесса ``tests/fixtures/<script>`` отдельным процессом."""
    return _run([sys.executable, str(FIXTURES_DIR / script), *args], cwd=cwd, env=env, binary=binary)


def _run(
    cmd: list[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    binary: bool,
) -> subprocess.CompletedProcess:
    if binary:
        return subprocess.run(  # noqa: S603 — свои процессы, без shell
            cmd, cwd=cwd, env=dict(env), capture_output=True, timeout=TIMEOUT
        )
    return subprocess.run(  # noqa: S603 — свои процессы, без shell
        cmd, cwd=cwd, env=dict(env), capture_output=True, encoding="utf-8", timeout=TIMEOUT
    )


def run_platform2_tty(
    args: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: float = TIMEOUT,
) -> tuple[int, str, str]:
    """Запуск ``platform2`` с TTY на stdout и stderr (два pty, §12.1).

    Возвращает ``(exit_code, stdout, stderr)``: master-дескрипторы разные, т.е.
    проверяется и TTY-статус каналов, и разделение слотов вывода.
    """
    master_out, slave_out = pty.openpty()
    master_err, slave_err = pty.openpty()
    try:
        proc = subprocess.Popen(  # noqa: S603 — свои процессы, без shell
            [require_platform2(), *args],
            stdin=subprocess.DEVNULL,
            stdout=slave_out,
            stderr=slave_err,
            cwd=cwd,
            env=dict(env),
        )
        # Родительские копии slave закрываются сразу: после выхода процесса
        # все slave закрыты → чтение master отдаёт буфер и завершается.
        os.close(slave_out)
        os.close(slave_err)
        try:
            code = proc.wait(timeout=timeout)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        out_raw = _drain(master_out)
        err_raw = _drain(master_err)
    finally:
        for fd in (slave_out, slave_err, master_out, master_err):
            # slave мог быть закрыт выше — двойное закрытие гасится.
            with contextlib.suppress(OSError):
                os.close(fd)
    return code, _decode_pty(out_raw), _decode_pty(err_raw)


def _drain(fd: int) -> bytes:
    """Читает master до конца: неблокирующе, пока данные есть (EAGAIN/EIO — стоп)."""
    os.set_blocking(fd, False)
    chunks: list[bytes] = []
    while True:
        try:
            chunk = os.read(fd, 65536)
        except OSError:
            break
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def _decode_pty(raw: bytes) -> str:
    """UTF-8 + нормализация ``\\r\\n`` (ONLCR пty) → канонические ``\\n``."""
    return raw.decode("utf-8", errors="replace").replace("\r\n", "\n")


def make_ops_project(root: Path) -> Path:
    """Валидный tmp-проект: маркер, ops-конфиг, заглушка compose-сервиса."""
    root.mkdir(parents=True, exist_ok=True)
    (root / ".ops-root").write_text("", encoding="utf-8")
    (root / ".ops-config.yml").write_text("master_url: http://master.test\n", encoding="utf-8")
    compose = root / "services" / "public" / "demo" / "docker-compose.yml"
    compose.parent.mkdir(parents=True, exist_ok=True)
    compose.write_text("services: {}\n", encoding="utf-8")
    return root


def normalize_help(text: str) -> str:
    """Help без рамок rich и без лишних пробелов — сравнение содержимого по ширинам."""
    return " ".join(text.translate(str.maketrans("", "", _BOX_DRAWING)).split())


def strip_ansi(text: str) -> str:
    """Текст без ANSI-кодов — проверки содержимого вывода на TTY."""
    return _ANSI_RE.sub("", text)
