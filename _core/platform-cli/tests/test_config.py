"""
Тесты для функций конфигурации CLI: ``get_project_root`` и ``get_config``.

Покрывает все источники конфигурации и приоритеты:
- OPS_PROJECT_ROOT (env override)
- .ops-root marker
- project_root из системного конфига
- Fallback на CWD
- OPS_CONFIG_PATH
- .ops-config.local.yml override
- Отсутствие конфига → typer.Exit(1)
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import typer
import yaml
from typer.testing import CliRunner

from apps_platform import cli
from apps_platform.cli import app, get_config, get_project_root

Exit = typer.Exit

runner = CliRunner()


@pytest.fixture(autouse=True)
def _clear_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Сбрасывает lru_cache и очищает переменные окружения перед каждым тестом."""
    get_project_root.cache_clear()
    get_config.cache_clear()
    for var in (
        "OPS_PROJECT_ROOT",
        "OPS_CONFIG_PATH",
        "PLATFORM_ENV",
        "PLATFORM_SSL_VERIFY",
    ):
        monkeypatch.delenv(var, raising=False)


class TestGetProjectRoot:
    """Тесты ``get_project_root()``."""

    def test_ops_project_root_env_valid(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """OPS_PROJECT_ROOT указывает на валидную директорию → возвращается."""
        monkeypatch.setenv("OPS_PROJECT_ROOT", str(tmp_path))
        assert get_project_root() == tmp_path

    def test_ops_project_root_env_nonexistent(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """OPS_PROJECT_ROOT указывает на несуществующую директорию → typer.Exit(1)."""
        nonexistent = tmp_path / "does-not-exist"
        monkeypatch.setenv("OPS_PROJECT_ROOT", str(nonexistent))
        with pytest.raises(Exit):
            get_project_root()

    def test_ops_project_root_env_is_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """OPS_PROJECT_ROOT указывает на файл, а не директорию → typer.Exit(1)."""
        target = tmp_path / "file.txt"
        target.write_text("x")
        monkeypatch.setenv("OPS_PROJECT_ROOT", str(target))
        with pytest.raises(Exit):
            get_project_root()

    def test_marker_found_in_parent(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """````.ops-root`` найден в родительской директории → возврат корня."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / ".ops-root").touch()
        sub = project_root / "a" / "b" / "c"
        sub.mkdir(parents=True)

        monkeypatch.chdir(sub)
        # Переменная OPS_PROJECT_ROOT не задана → fallthrough на поиск маркера.
        with patch("apps_platform.cli._SYSTEM_CONFIG_PATHS", ()):
            assert get_project_root() == project_root

    def test_marker_search_stops_at_filesystem_root(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Поиск маркера не уходит за пределы ФС и возвращает None, если не найден."""
        isolated = tmp_path / "isolated"
        isolated.mkdir()
        monkeypatch.chdir(isolated)
        with patch("apps_platform.cli._SYSTEM_CONFIG_PATHS", ()):
            # Маркера нигде нет → fallback на cwd
            assert get_project_root() == Path.cwd()

    def test_fallback_to_cwd(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Все источники отсутствуют → fallback на ``Path.cwd()``."""
        monkeypatch.chdir(tmp_path)
        with patch("apps_platform.cli._SYSTEM_CONFIG_PATHS", ()):
            assert get_project_root() == tmp_path

    def test_project_root_from_system_config(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``project_root`` из системного конфига используется, если директория валидна."""
        declared_root = tmp_path / "declared"
        declared_root.mkdir()
        cfg_path = tmp_path / "config.yml"
        cfg_path.write_text(yaml.safe_dump({"project_root": str(declared_root)}))

        # Запускаем из произвольной директории без маркера
        workdir = tmp_path / "work"
        workdir.mkdir()
        monkeypatch.chdir(workdir)

        with patch("apps_platform.cli._SYSTEM_CONFIG_PATHS", (cfg_path,)):
            assert get_project_root() == declared_root

    def test_project_root_from_system_config_nonexistent(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``project_root`` указывает на несуществующую директорию → fallback."""
        cfg_path = tmp_path / "config.yml"
        cfg_path.write_text(yaml.safe_dump({"project_root": "/definitely/missing"}))

        monkeypatch.chdir(tmp_path)
        with patch("apps_platform.cli._SYSTEM_CONFIG_PATHS", (cfg_path,)):
            # Fallback на cwd, т.к. путь не существует
            assert get_project_root() == tmp_path

    def test_system_config_oserror_skipped(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """OSError при чтении конфига пропускается, fallback на cwd."""
        workdir = tmp_path / "work"
        workdir.mkdir()
        monkeypatch.chdir(workdir)

        bad_cfg = tmp_path / "bad.yml"
        bad_cfg.write_text("placeholder")  # Файл существует, но open() падает

        with (
            patch("apps_platform.cli._SYSTEM_CONFIG_PATHS", (bad_cfg,)),
            patch("builtins.open", side_effect=OSError("boom")),
        ):
            assert get_project_root() == workdir

    def test_env_takes_priority_over_marker(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """OPS_PROJECT_ROOT имеет приоритет над поиском маркера."""
        env_root = tmp_path / "from_env"
        env_root.mkdir()
        marker_root = tmp_path / "from_marker"
        marker_root.mkdir()
        (marker_root / ".ops-root").touch()

        monkeypatch.setenv("OPS_PROJECT_ROOT", str(env_root))
        monkeypatch.chdir(marker_root)

        assert get_project_root() == env_root


class TestGetConfig:
    """Тесты ``get_config()``."""

    def test_ops_config_path_takes_priority(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """OPS_CONFIG_PATH используется первым, даже если есть .ops-config.yml в корне."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        # В корне есть дефолтный конфиг
        default_cfg = project_root / ".ops-config.yml"
        default_cfg.write_text(yaml.safe_dump({"a": 1, "b": {"c": "default"}}))

        # OPS_CONFIG_PATH указывает на другой файл
        override_cfg = tmp_path / "override.yml"
        override_cfg.write_text(yaml.safe_dump({"a": 999, "b": {"c": "override"}}))

        monkeypatch.setenv("OPS_PROJECT_ROOT", str(project_root))
        monkeypatch.setenv("OPS_CONFIG_PATH", str(override_cfg))
        with patch("apps_platform.cli._SYSTEM_CONFIG_PATHS", ()):
            cfg = get_config()
            assert cfg == {"a": 999, "b": {"c": "override"}}

    def test_local_override_merged(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``.ops-config.local.yml`` применяется через ``_deep_merge``."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        base = project_root / ".ops-config.yml"
        base.write_text(
            yaml.safe_dump({"a": 1, "b": {"c": "base", "d": "base"}}),
        )
        local = project_root / ".ops-config.local.yml"
        local.write_text(
            yaml.safe_dump({"b": {"c": "local", "e": "local"}}),
        )

        monkeypatch.setenv("OPS_PROJECT_ROOT", str(project_root))
        with patch("apps_platform.cli._SYSTEM_CONFIG_PATHS", ()):
            cfg = get_config()
            # b.c — перезаписан, b.d — сохранён, b.e — добавлен
            assert cfg == {"a": 1, "b": {"c": "local", "d": "base", "e": "local"}}

    def test_first_existing_candidate_wins(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Если есть несколько кандидатов, первый существующий выигрывает."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        first = project_root / ".ops-config.yml"
        first.write_text(yaml.safe_dump({"src": "first"}))

        second = tmp_path / "second.yml"
        second.write_text(yaml.safe_dump({"src": "second"}))

        monkeypatch.setenv("OPS_PROJECT_ROOT", str(project_root))
        with patch("apps_platform.cli._SYSTEM_CONFIG_PATHS", (second,)):
            cfg = get_config()
            assert cfg == {"src": "first"}

    def test_no_config_raises_exit(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Конфиг отсутствует → ``typer.Exit(1)``."""
        monkeypatch.setenv("OPS_PROJECT_ROOT", str(tmp_path))
        with patch("apps_platform.cli._SYSTEM_CONFIG_PATHS", ()):
            with pytest.raises(Exit):
                get_config()

    def test_oserror_on_config_skipped_then_exit(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """OSError на чтении первого кандидата → переход к следующему → если нет — Exit(1)."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        broken = project_root / ".ops-config.yml"
        broken.write_text("placeholder")

        monkeypatch.setenv("OPS_PROJECT_ROOT", str(project_root))
        with (
            patch("apps_platform.cli._SYSTEM_CONFIG_PATHS", ()),
            patch("builtins.open", side_effect=OSError("nope")),
        ):
            with pytest.raises(Exit):
                get_config()

    def test_empty_yaml_returns_empty_dict(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Пустой YAML-файл → ``{}`` (без KeyError)."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / ".ops-config.yml").write_text("")

        monkeypatch.setenv("OPS_PROJECT_ROOT", str(project_root))
        with patch("apps_platform.cli._SYSTEM_CONFIG_PATHS", ()):
            assert get_config() == {}

    def test_malformed_yaml_treated_as_missing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Некорректный YAML → yaml.YAMLError → ``typer.Exit(1)``."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / ".ops-config.yml").write_text("invalid: : yaml: ]")

        monkeypatch.setenv("OPS_PROJECT_ROOT", str(project_root))
        with patch("apps_platform.cli._SYSTEM_CONFIG_PATHS", ()):
            with pytest.raises((Exit, yaml.YAMLError)):
                get_config()


class TestCacheInvalidation:
    """Тесты кэширования lru_cache."""

    def test_caches_are_per_process(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """lru_cache возвращает одно и то же значение при повторном вызове."""
        monkeypatch.setenv("OPS_PROJECT_ROOT", str(tmp_path))
        first = get_project_root()
        second = get_project_root()
        assert first == second == tmp_path

    def test_cache_clear_allows_recomputation(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """После ``cache_clear()`` функция пересчитывает."""
        target1 = tmp_path / "first"
        target1.mkdir()
        monkeypatch.setenv("OPS_PROJECT_ROOT", str(target1))
        assert get_project_root() == target1

        target2 = tmp_path / "second"
        target2.mkdir()
        monkeypatch.setenv("OPS_PROJECT_ROOT", str(target2))
        get_project_root.cache_clear()
        assert get_project_root() == target2


class TestCliHelp:
    """Smoke-тест CLI."""

    def test_help_runs(self) -> None:
        """``platform --help`` запускается без падения."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
