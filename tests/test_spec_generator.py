"""Tests for natural-language spec generation."""

from pathlib import Path

import pytest

from owloop.adapters import AgentResult, MockAdapter
from owloop.spec_generator import SpecGenerationError, SpecGenerator
from owloop.spec_queue import find_next_spec_number


def _done_spec_result(name: str = "refactor errors") -> AgentResult:
    return AgentResult(
        stdout=(
            f"# Spec: {name}\n\n"
            "## Priority: 3\n\n"
            "## Requirements\n"
            "- [ ] Unify error handling\n\n"
            "## Acceptance Criteria\n"
            "- [ ] `pytest tests/` exits 0\n\n"
            "## Exclusions\n"
            "- Do NOT modify pyproject.toml\n\n"
            "<promise>DONE</promise>"
        ),
        returncode=0,
        success=True,
        has_completion_signal=True,
        done_signal="<promise>DONE</promise>",
        promise_state="DONE",
    )


def test_generate_writes_spec_on_done_signal(tmp_path: Path) -> None:
    (tmp_path / ".owloop").mkdir()
    adapter = MockAdapter(responses=[_done_spec_result("unify errors")])
    generator = SpecGenerator(tmp_path, adapter)

    paths = generator.generate("unify error handling")

    assert len(paths) == 1
    path = paths[0]
    assert path.exists()
    assert path.parent.name == "specs"
    assert path.parent.parent.name == ".owloop"
    assert path.name == "01-unify-errors.md"
    content = path.read_text(encoding="utf-8")
    assert "# Spec: unify errors" in content
    assert "## Acceptance Criteria" in content


def test_generate_asks_clarification_then_writes_spec(tmp_path: Path) -> None:
    (tmp_path / ".owloop").mkdir()
    adapter = MockAdapter(responses=[
        AgentResult(
            stdout="<promise>DECIDE:Which module should I refactor?</promise>",
            returncode=0,
            success=True,
            has_completion_signal=True,
            done_signal="<promise>DECIDE:Which module should I refactor?</promise>",
            promise_state="DECIDE",
            promise_payload="Which module should I refactor?",
        ),
        _done_spec_result("refactor helpers"),
    ])
    generator = SpecGenerator(tmp_path, adapter)
    asked: list[list[str]] = []

    def fake_ask(questions: list[str]) -> list[str]:
        asked.append(questions)
        return ["owloop/helpers.py"]

    paths = generator.generate("refactor stuff", ask_fn=fake_ask)

    assert len(asked) == 1
    assert asked[0] == ["Which module should I refactor?"]
    path = paths[0]
    assert path.parent.parent.name == ".owloop"
    assert path.name == "01-refactor-helpers.md"


def test_generate_splits_multiple_specs(tmp_path: Path) -> None:
    (tmp_path / ".owloop").mkdir()
    multi_output = (
        "# Spec: extract-helpers\n\n"
        "## Priority: 1\n\n"
        "## Depends On\n- none\n\n"
        "## Requirements\n- [ ] Extract shared helpers\n\n"
        "## Acceptance Criteria\n- [ ] `pytest` exits 0\n\n"
        "## Exclusions\n- Do NOT modify config files\n\n"
        "---\n\n"
        "# Spec: refactor-api\n\n"
        "## Priority: 2\n\n"
        "## Depends On\n- extract-helpers\n\n"
        "## Requirements\n- [ ] Refactor API layer\n\n"
        "## Acceptance Criteria\n- [ ] `pytest` exits 0\n\n"
        "## Exclusions\n- Do NOT modify models\n\n"
        "<promise>DONE</promise>"
    )
    adapter = MockAdapter(responses=[
        AgentResult(
            stdout=multi_output,
            returncode=0,
            success=True,
            has_completion_signal=True,
            done_signal="<promise>DONE</promise>",
            promise_state="DONE",
        ),
    ])
    generator = SpecGenerator(tmp_path, adapter)

    paths = generator.generate("refactor the codebase")

    assert len(paths) == 2
    assert paths[0].name == "01-extract-helpers.md"
    assert paths[1].name == "02-refactor-api.md"
    assert "Depends On" in paths[1].read_text(encoding="utf-8")


def test_generate_gives_up_after_max_rounds(tmp_path: Path) -> None:
    adapter = MockAdapter(responses=[
        AgentResult(
            stdout="<promise>DECIDE:What is the scope?</promise>",
            returncode=0,
            success=True,
            has_completion_signal=True,
            promise_state="DECIDE",
            promise_payload="What is the scope?",
        ),
    ] * 3)
    generator = SpecGenerator(tmp_path, adapter)

    with pytest.raises(SpecGenerationError):
        generator.generate("do something", max_rounds=3, ask_fn=lambda _qs: ["unknown"])


def test_generate_requires_recognizable_output(tmp_path: Path) -> None:
    adapter = MockAdapter(responses=[
        AgentResult(
            stdout="I think I will just describe the task.",
            returncode=0,
            success=True,
            has_completion_signal=False,
        ),
    ])
    generator = SpecGenerator(tmp_path, adapter)

    with pytest.raises(SpecGenerationError):
        generator.generate("vague goal")


def test_find_next_spec_number_increments(tmp_path: Path) -> None:
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    (specs_dir / "01-first.md").write_text("# Spec\n", encoding="utf-8")
    (specs_dir / "02-second.md").write_text("# Spec\n", encoding="utf-8")

    assert find_next_spec_number(specs_dir) == 3


def test_find_next_spec_number_ignores_non_numeric_files(tmp_path: Path) -> None:
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    (specs_dir / "README.md").write_text("# Spec\n", encoding="utf-8")

    assert find_next_spec_number(specs_dir) == 1
