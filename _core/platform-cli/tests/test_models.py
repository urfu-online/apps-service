"""Тесты доменных типов core/models.py (T2): frozen-модели, enum, Deadline (§10.4, ADR-001)."""

from __future__ import annotations

import ast
import dataclasses
import inspect
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from apps_platform.core import models
from apps_platform.core.models import (
    Deadline,
    DeadlinePolicy,
    Finding,
    FindingLevel,
    FixSuggestion,
    Observation,
    ObservationSource,
    Routing,
    SectionState,
    ServiceRef,
    Visibility,
)

FORBIDDEN_IMPORTS = {"typer", "rich", "docker", "requests"}

P2_RESULT_TYPES = ("SectionResult", "ValidationReport", "DeploymentResult", "ListResult")


def test_serviceref_frozen() -> None:
    ref = ServiceRef(name="api", path=Path("services/public/api"), visibility=Visibility.PUBLIC)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ref.name = "other"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        ref.visibility = Visibility.CORE  # type: ignore[misc]


def test_serviceref_fields_and_default_routing() -> None:
    ref = ServiceRef(name="api", path=Path("services/public/api"), visibility=Visibility.PUBLIC)
    assert ref.routing is None
    assert {f.name for f in dataclasses.fields(ServiceRef)} == {"name", "path", "visibility", "routing"}


def test_observation_frozen() -> None:
    obs = Observation(source=ObservationSource.MASTER, observed_at=datetime.now(UTC))
    with pytest.raises(dataclasses.FrozenInstanceError):
        obs.stale = True  # type: ignore[misc]
    assert {f.name for f in dataclasses.fields(Observation)} == {"source", "observed_at", "stale", "note"}
    assert obs.stale is False
    assert obs.note is None


def test_fixsuggestion_frozen() -> None:
    fix = FixSuggestion(description="перезапустить сервис", commands=(("platform", "service", "restart", "api"),))
    with pytest.raises(dataclasses.FrozenInstanceError):
        fix.risky = True  # type: ignore[misc]
    assert {f.name for f in dataclasses.fields(FixSuggestion)} == {"description", "root_cause", "commands", "risky"}


def test_fixsuggestion_commands_are_tuple_of_tuples() -> None:
    commands = (("platform", "service", "deploy", "api"), ("docker", "network", "inspect", "platform_network"))
    fix = FixSuggestion(description="задеплоить", commands=commands)
    assert isinstance(fix.commands, tuple)
    assert all(isinstance(argv, tuple) for argv in fix.commands)
    assert fix.commands == commands
    default_fix = FixSuggestion(description="ничего не делать")
    assert default_fix.commands == ()


def test_finding_frozen() -> None:
    finding = Finding(
        level=FindingLevel.WARNING,
        check="visibility-dir",
        object="services/public/legacy",
        message="сервис лежит не в том каталоге",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        finding.level = FindingLevel.ERROR  # type: ignore[misc]
    assert finding.service is None
    assert finding.fix is None


def test_finding_has_no_warnings_field() -> None:
    names = {f.name for f in dataclasses.fields(Finding)}
    assert names == {"level", "check", "object", "message", "service", "fix"}
    assert "warnings" not in names


def test_deadline_frozen() -> None:
    deadline = Deadline(2.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        deadline.budget_s = 10.0  # type: ignore[misc]


def test_deadline_policy_frozen() -> None:
    policy = DeadlinePolicy()
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.budget_s = 5.0  # type: ignore[misc]


@pytest.mark.parametrize(
    ("enum_cls", "expected"),
    [
        (Visibility, {"public", "internal", "core"}),
        (Routing, {"domain", "subfolder", "port", "none"}),
        (SectionState, {"complete", "partial", "unavailable"}),
        (FindingLevel, {"error", "warning", "note"}),
        (ObservationSource, {"filesystem", "docker", "caddy", "master", "direct_probe"}),
    ],
)
def test_enum_closed_value_set(enum_cls, expected) -> None:
    assert {member.value for member in enum_cls} == expected
    for value in expected:
        assert enum_cls(value).value == value


def test_enum_members_by_name() -> None:
    assert Visibility.PUBLIC.value == "public"
    assert Visibility.INTERNAL.value == "internal"
    assert Visibility.CORE.value == "core"
    assert Routing.DOMAIN.value == "domain"
    assert Routing.SUBFOLDER.value == "subfolder"
    assert Routing.PORT.value == "port"
    assert Routing.NONE.value == "none"
    assert SectionState.COMPLETE.value == "complete"
    assert SectionState.PARTIAL.value == "partial"
    assert SectionState.UNAVAILABLE.value == "unavailable"
    assert FindingLevel.ERROR.value == "error"
    assert FindingLevel.WARNING.value == "warning"
    assert FindingLevel.NOTE.value == "note"
    assert ObservationSource.FILESYSTEM.value == "filesystem"
    assert ObservationSource.DOCKER.value == "docker"
    assert ObservationSource.CADDY.value == "caddy"
    assert ObservationSource.MASTER.value == "master"
    assert ObservationSource.DIRECT_PROBE.value == "direct_probe"


def test_str_enum_is_plain_str_for_json() -> None:
    assert Visibility.PUBLIC == "public"
    assert str(FindingLevel.WARNING) == "warning"
    assert Routing("domain") == Routing.DOMAIN
    assert json.dumps({"level": FindingLevel.NOTE}) == '{"level": "note"}'


def test_deadline_after_classmethod() -> None:
    deadline = Deadline.after(5.0)
    assert isinstance(deadline, Deadline)
    assert deadline.budget_s == 5.0
    assert not deadline.expired()
    assert 0.0 < deadline.remaining() <= 5.0


def test_deadline_remaining_decreases() -> None:
    deadline = Deadline.after(5.0)
    first = deadline.remaining()
    time.sleep(0.05)
    second = deadline.remaining()
    assert 0.0 < second < first <= 5.0


def test_deadline_remaining_never_below_zero() -> None:
    deadline = Deadline(0.001)
    time.sleep(0.05)
    assert deadline.remaining() == 0.0
    assert deadline.expired()


def test_deadline_expired_with_injected_now() -> None:
    past_deadline = Deadline(2.0, now=time.monotonic() - 100.0)
    assert past_deadline.remaining() == 0.0
    assert past_deadline.expired()
    fresh_deadline = Deadline(2.0, now=time.monotonic())
    assert not fresh_deadline.expired()
    assert fresh_deadline.remaining() <= 2.0


def test_deadline_default_budget_policy() -> None:
    policy = DeadlinePolicy()
    assert policy.budget_s == 2.0
    deadline = policy.new_deadline()
    assert isinstance(deadline, Deadline)
    assert deadline.budget_s == 2.0
    assert not deadline.expired()
    custom = DeadlinePolicy(budget_s=10.0).new_deadline()
    assert custom.budget_s == 10.0


def test_p2_result_types_are_absent() -> None:
    for name in P2_RESULT_TYPES:
        assert not hasattr(models, name)


def test_domain_module_imports_are_clean() -> None:
    source_path = Path(inspect.getfile(models))
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    assert roots.isdisjoint(
        FORBIDDEN_IMPORTS
    ), f"запрещённые импорты в {source_path.name}: {sorted(roots & FORBIDDEN_IMPORTS)}"
