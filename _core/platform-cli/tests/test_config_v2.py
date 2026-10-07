"""Тесты ``apps_platform.config`` (v2, T4): §11.1 — 5 уровней root, приоритеты, AppConfig.

Только env (``monkeypatch`` ``os.environ``) + ``tmp_path`` + явные параметры
функций — без патчей внутренних имён.
"""

from __future__ import annotations

import logging
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
import yaml

from apps_platform.config import (
    AppConfig,
    UserPrefs,
    load_ops_config,
    load_user_prefs,
    make_app_config,
    resolve_project_root,
)
from apps_platform.core.errors import PlatformError

_DEFAULT_MASTER_URL = "http://localhost:8001"


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Чистое окружение: env-переменные конфига сняты, user config отсутствует."""
    for var in (
        "OPS_PROJECT_ROOT",
        "OPS_CONFIG_PATH",
        "PLATFORM_ENV",
        "PLATFORM_SSL_VERIFY",
        "PLATFORM_API_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


class TestResolveProjectRoot:
    """Пять уровней резолвинга project root (§11.1)."""

    def test_level1_project_dir_beats_env_and_marker(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``--project-dir`` авторитарен: выше env и маркера."""
        project_dir = tmp_path / "cli-root"
        project_dir.mkdir()
        env_root = tmp_path / "env-root"
        env_root.mkdir()
        marker_root = tmp_path / "marker-root"
        marker_root.mkdir()
        (marker_root / ".ops-root").touch()

        monkeypatch.setenv("OPS_PROJECT_ROOT", str(env_root))
        monkeypatch.chdir(marker_root)

        assert resolve_project_root(project_dir) == project_dir

    def test_level1_project_dir_nonexistent_is_invalid_value(
        self,
        tmp_path: Path,
    ) -> None:
        """Несуществующий ``--project-dir`` → ``PlatformError(invalid_value)``, exit 2."""
        missing = tmp_path / "does-not-exist"
        with pytest.raises(PlatformError) as exc_info:
            resolve_project_root(missing)

        err = exc_info.value
        assert err.code == "invalid_value"
        assert err.exit_code == 2
        assert err.object == str(missing)

    def test_level1_project_dir_file_is_invalid_value(
        self,
        tmp_path: Path,
    ) -> None:
        """``--project-dir`` на файл → ``PlatformError(invalid_value)``."""
        target = tmp_path / "file.txt"
        target.write_text("x")
        with pytest.raises(PlatformError) as exc_info:
            resolve_project_root(target)

        assert exc_info.value.code == "invalid_value"
        assert exc_info.value.object == str(target)

    def test_level2_env_beats_marker(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``OPS_PROJECT_ROOT`` выигрывает у маркера (уровень 2 > уровень 3)."""
        env_root = tmp_path / "env-root"
        env_root.mkdir()
        marker_root = tmp_path / "marker-root"
        marker_root.mkdir()
        (marker_root / ".ops-root").touch()

        monkeypatch.setenv("OPS_PROJECT_ROOT", str(env_root))
        monkeypatch.chdir(marker_root)

        assert resolve_project_root(None) == env_root

    def test_level2_env_nonexistent_is_invalid_value(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Невалидный ``OPS_PROJECT_ROOT`` → ``PlatformError(invalid_value)``, exit 2."""
        monkeypatch.setenv("OPS_PROJECT_ROOT", str(tmp_path / "missing"))
        with pytest.raises(PlatformError) as exc_info:
            resolve_project_root(None)

        err = exc_info.value
        assert err.code == "invalid_value"
        assert err.exit_code == 2
        assert "OPS_PROJECT_ROOT" in err.message

    def test_level3_marker_beats_system_config(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Маркер ``.ops-root`` выигрывает у ``project_root`` системного конфига."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / ".ops-root").touch()
        sub = project_root / "a" / "b"
        sub.mkdir(parents=True)

        declared_root = tmp_path / "declared"
        declared_root.mkdir()
        sys_cfg = tmp_path / "system.yml"
        sys_cfg.write_text(yaml.safe_dump({"project_root": str(declared_root)}))

        monkeypatch.chdir(sub)
        assert resolve_project_root(system_config_paths=(sys_cfg,)) == project_root

    def test_level4_project_root_from_system_config(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``project_root`` из системного конфига — уровень 4 (нет env/маркера)."""
        declared_root = tmp_path / "declared"
        declared_root.mkdir()
        sys_cfg = tmp_path / "system.yml"
        sys_cfg.write_text(yaml.safe_dump({"project_root": str(declared_root)}))

        workdir = tmp_path / "work"
        workdir.mkdir()
        monkeypatch.chdir(workdir)

        assert resolve_project_root(system_config_paths=(sys_cfg,)) == declared_root

    def test_level5_fallback_to_cwd(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Ни один источник не сработал → CWD (уровень 5)."""
        workdir = tmp_path / "work"
        workdir.mkdir()
        monkeypatch.chdir(workdir)

        assert resolve_project_root(system_config_paths=()) == workdir

    def test_resolve_project_root_not_cached(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Кэш живёт в legacy-делегатах: здесь каждый вызов свежий."""
        first = tmp_path / "first"
        first.mkdir()
        second = tmp_path / "second"
        second.mkdir()

        monkeypatch.setenv("OPS_PROJECT_ROOT", str(first))
        assert resolve_project_root(None) == first

        monkeypatch.setenv("OPS_PROJECT_ROOT", str(second))
        assert resolve_project_root(None) == second


class TestLoadOpsConfig:
    """Загрузка ops-конфига и приоритет кандидатов."""

    def test_ops_config_path_beats_root_config(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``OPS_CONFIG_PATH`` выигрывает у ``root/.ops-config.yml``."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / ".ops-config.yml").write_text(yaml.safe_dump({"src": "root"}))

        override = tmp_path / "override.yml"
        override.write_text(yaml.safe_dump({"src": "env"}))

        monkeypatch.setenv("OPS_CONFIG_PATH", str(override))
        cfg = load_ops_config(project_root, system_config_paths=())
        assert cfg == {"src": "env"}

    def test_root_config_found(
        self,
        tmp_path: Path,
    ) -> None:
        """``root/.ops-config.yml`` читается, когда env не задан."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / ".ops-config.yml").write_text(yaml.safe_dump({"a": 1}))

        assert load_ops_config(project_root, system_config_paths=()) == {"a": 1}

    def test_system_candidate_after_root(
        self,
        tmp_path: Path,
    ) -> None:
        """Системный кандидат используется, если корневого конфига нет."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        sys_cfg = tmp_path / "system.yml"
        sys_cfg.write_text(yaml.safe_dump({"src": "system"}))

        assert load_ops_config(project_root, system_config_paths=(sys_cfg,)) == {"src": "system"}

    def test_local_override_deep_merged(
        self,
        tmp_path: Path,
    ) -> None:
        """``.ops-config.local.yml`` deep-merge'ится поверх найденного конфига."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / ".ops-config.yml").write_text(
            yaml.safe_dump({"a": 1, "b": {"c": "base", "d": "base"}}),
        )
        (project_root / ".ops-config.local.yml").write_text(
            yaml.safe_dump({"b": {"c": "local", "e": "local"}}),
        )

        cfg = load_ops_config(project_root, system_config_paths=())
        assert cfg == {"a": 1, "b": {"c": "local", "d": "base", "e": "local"}}

    def test_config_not_found_raises_platform_error(
        self,
        tmp_path: Path,
    ) -> None:
        """Нигде нет конфига → ``PlatformError(config_not_found)``, exit 3, hint §12.4."""
        with pytest.raises(PlatformError) as exc_info:
            load_ops_config(tmp_path, system_config_paths=())

        err = exc_info.value
        assert err.code == "config_not_found"
        assert err.exit_code == 3
        assert err.hint is not None
        assert "OPS_CONFIG_PATH" in err.hint
        assert err.to_json()["schema_version"] == 1


class TestMakeAppConfig:
    """``AppConfig``: master_url, ssl_verify, api_token, user_prefs, frozen."""

    def test_end_to_end_from_marker_root(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Полный путь: маркер + ``.ops-config.yml`` → root и master_url из конфига."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / ".ops-root").touch()
        (project_root / ".ops-config.yml").write_text(
            yaml.safe_dump({"master_url": "http://ops:8001"}),
        )

        monkeypatch.chdir(project_root)
        cfg = make_app_config()

        assert cfg.root == project_root
        assert cfg.master_url == "http://ops:8001"
        assert cfg.ssl_verify is True
        assert cfg.api_token is None
        assert cfg.user_prefs == UserPrefs()

    def test_master_url_default(
        self,
        tmp_path: Path,
    ) -> None:
        """Дефолт ``http://localhost:8001``, если в ops-конфиге нет ``master_url``."""
        cfg = make_app_config(root=tmp_path, ops_config={})
        assert cfg.master_url == _DEFAULT_MASTER_URL

    def test_master_url_from_ops_config(
        self,
        tmp_path: Path,
    ) -> None:
        """``master_url`` берётся из ``.ops-config.yml``."""
        cfg = make_app_config(root=tmp_path, ops_config={"master_url": "http://ops:9000"})
        assert cfg.master_url == "http://ops:9000"

    def test_master_url_cli_beats_ops_config(
        self,
        tmp_path: Path,
    ) -> None:
        """CLI-уровень (параметр) выше ops-конфига (§11.1)."""
        cfg = make_app_config(
            root=tmp_path,
            ops_config={"master_url": "http://ops:9000"},
            master_url="http://cli:7000",
        )
        assert cfg.master_url == "http://cli:7000"

    def test_ssl_verify_production_forces_true(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``PLATFORM_ENV=production`` → verify=True всегда, флаги игнорируются."""
        monkeypatch.setenv("PLATFORM_ENV", "production")
        monkeypatch.setenv("PLATFORM_SSL_VERIFY", "false")

        cfg = make_app_config(root=tmp_path, ops_config={}, insecure=True)
        assert cfg.ssl_verify is True

    def test_ssl_verify_env_false(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``PLATFORM_SSL_VERIFY=false`` вне production → verify=False."""
        monkeypatch.setenv("PLATFORM_SSL_VERIFY", "false")
        cfg = make_app_config(root=tmp_path, ops_config={})
        assert cfg.ssl_verify is False

    def test_ssl_verify_default_true(
        self,
        tmp_path: Path,
    ) -> None:
        """Без env — verify включён по умолчанию."""
        cfg = make_app_config(root=tmp_path, ops_config={})
        assert cfg.ssl_verify is True

    def test_ssl_verify_insecure_flag(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """CLI-флаг ``--insecure`` вне production → verify=False."""
        monkeypatch.setenv("PLATFORM_ENV", "development")
        cfg = make_app_config(root=tmp_path, ops_config={}, insecure=True)
        assert cfg.ssl_verify is False

    def test_api_token_from_env_only(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Токен берётся только из env, не из ops-конфига, и не попадает в repr."""
        monkeypatch.setenv("PLATFORM_API_TOKEN", "s3cret-token")
        cfg = make_app_config(root=tmp_path, ops_config={"api_token": "from-config"})

        assert cfg.api_token == "s3cret-token"
        assert "s3cret-token" not in repr(cfg)

    def test_api_token_absent_without_env(
        self,
        tmp_path: Path,
    ) -> None:
        """Env не задан → ``None``."""
        cfg = make_app_config(root=tmp_path, ops_config={})
        assert cfg.api_token is None

    def test_ops_config_stored_read_only(
        self,
        tmp_path: Path,
    ) -> None:
        """``ops_config`` — read-only Mapping (frozen-семантика)."""
        cfg = make_app_config(root=tmp_path, ops_config={"a": 1})
        assert cfg.ops_config == {"a": 1}
        with pytest.raises(TypeError):
            cfg.ops_config["a"] = 2  # type: ignore[index]

    def test_app_config_is_frozen(
        self,
        tmp_path: Path,
    ) -> None:
        """``AppConfig`` — frozen dataclass."""
        cfg = make_app_config(root=tmp_path, ops_config={})
        with pytest.raises(FrozenInstanceError):
            cfg.master_url = "http://changed"  # type: ignore[misc]

    def test_user_prefs_cli_beats_file(
        self,
        tmp_path: Path,
    ) -> None:
        """CLI-уровень preferences выше user config (§11.1)."""
        user_cfg = tmp_path / "xdg" / "platform" / "config.yml"
        user_cfg.parent.mkdir(parents=True)
        user_cfg.write_text(yaml.safe_dump({"status": {"compact": False}}))

        cli_prefs = UserPrefs(compact=True)
        cfg = make_app_config(root=tmp_path, ops_config={}, user_prefs=cli_prefs)
        assert cfg.user_prefs == cli_prefs


class TestUserPrefs:
    """User config (§8.2): дефолты, чтение файла, игнорирование неизвестного."""

    def test_defaults_when_file_absent(self) -> None:
        """Файла нет → дефолты §8."""
        prefs = load_user_prefs()
        assert prefs == UserPrefs(
            sections=("services", "health", "problems"),
            deadline_s=2.0,
            compact=False,
            stale_after_s=90.0,
        )

    def test_read_from_file(
        self,
        tmp_path: Path,
    ) -> None:
        """Чтение ``${XDG_CONFIG_HOME}/platform/config.yml`` с длительностями ``Ns``."""
        user_cfg = tmp_path / "xdg" / "platform" / "config.yml"
        user_cfg.parent.mkdir(parents=True)
        user_cfg.write_text(
            yaml.safe_dump(
                {
                    "status": {"sections": ["services", "health"], "compact": True, "deadline": "5s"},
                    "health": {"stale_after": "120s"},
                },
            ),
        )

        prefs = load_user_prefs()
        assert prefs == UserPrefs(
            sections=("services", "health"),
            deadline_s=5.0,
            compact=True,
            stale_after_s=120.0,
        )

    def test_unknown_keys_ignored_with_warning(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Неизвестные ключи игнорируются с warning, валидные — применяются."""
        user_cfg = tmp_path / "xdg" / "platform" / "config.yml"
        user_cfg.parent.mkdir(parents=True)
        user_cfg.write_text(
            yaml.safe_dump(
                {
                    "color": "blue",
                    "status": {"compact": True, "mystery": 1, "sections": ["services", "typo-section"]},
                    "unknown_block": {"a": 1},
                },
            ),
        )

        with caplog.at_level(logging.WARNING, logger="apps_platform.config"):
            prefs = load_user_prefs()

        assert prefs.compact is True
        assert prefs.deadline_s == 2.0  # не затронут
        assert prefs.sections == ("services", "typo-section")  # сохранены, warning выдан
        warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("color" in w for w in warnings)
        assert any("unknown_block" in w for w in warnings)
        assert any("mystery" in w for w in warnings)
        assert any("typo-section" in w for w in warnings)

    def test_malformed_file_falls_back_to_defaults(
        self,
        tmp_path: Path,
    ) -> None:
        """битый YAML в user config → warning и дефолты (не падение)."""
        user_cfg = tmp_path / "xdg" / "platform" / "config.yml"
        user_cfg.parent.mkdir(parents=True)
        user_cfg.write_text("invalid: : yaml: ]")

        assert load_user_prefs() == UserPrefs()

    def test_make_app_config_reads_user_prefs(
        self,
        tmp_path: Path,
    ) -> None:
        """``make_app_config`` подтягивает preferences из user config."""
        user_cfg = tmp_path / "xdg" / "platform" / "config.yml"
        user_cfg.parent.mkdir(parents=True)
        user_cfg.write_text(yaml.safe_dump({"status": {"deadline": "7s"}}))

        cfg = make_app_config(root=tmp_path, ops_config={})
        assert cfg.user_prefs.deadline_s == 7.0
        assert cfg.user_prefs == UserPrefs(deadline_s=7.0)


def test_make_app_config_type_contract(tmp_path: Path) -> None:
    """Контракт полей ``AppConfig`` (типы §11.1)."""
    cfg = make_app_config(root=tmp_path, ops_config={})
    assert isinstance(cfg, AppConfig)
    assert isinstance(cfg.root, Path)
    assert isinstance(cfg.user_prefs, UserPrefs)
    assert cfg.api_token is None or isinstance(cfg.api_token, str)
