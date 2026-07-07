"""Tests for the owloop engine loop and cross-iteration context features."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from owloop.adapters import AgentResult, MockAdapter
from owloop.engine import EngineConfig, OwloopEngine


def _git_init(repo: Path) -> None:
    """Initialize a git repo with an initial commit so HEAD exists."""
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("# test", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)


def _make_engine(repo: Path, adapter: MockAdapter, **kwargs) -> OwloopEngine:
    config = EngineConfig(project_dir=repo, worktree=False, **kwargs)
    return OwloopEngine(config=config, adapter=adapter)


def test_build_prompt_with_context_prepends_steering_and_run_notes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = MockAdapter()
    engine = _make_engine(repo, adapter)

    (repo / "STEERING.md").write_text("Focus on tests.", encoding="utf-8")
    (repo / "run-notes.md").write_text("Watch out for X.", encoding="utf-8")

    built = engine._build_prompt_with_context("PROMPT BODY")

    assert "STEERING.md" in built
    assert "Focus on tests." in built
    assert "previous iterations of this run" in built
    assert "Watch out for X." in built
    assert built.endswith("PROMPT BODY")


def test_build_prompt_with_context_no_files_returns_prompt_unchanged(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = MockAdapter()
    engine = _make_engine(repo, adapter)

    assert engine._build_prompt_with_context("PROMPT BODY") == "PROMPT BODY"


def test_build_prompt_with_context_emits_events(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = MockAdapter()
    engine = _make_engine(repo, adapter)
    events: list[tuple[str, dict]] = []
    engine.on_event = lambda kind, data: events.append((kind, data))

    (repo / "STEERING.md").write_text("Steer", encoding="utf-8")
    (repo / "run-notes.md").write_text("Note", encoding="utf-8")

    engine._build_prompt_with_context("PROMPT")

    kinds = [k for k, _ in events]
    assert "steering_loaded" in kinds
    assert "run_notes_loaded" in kinds


def test_append_run_note_creates_file_and_formats_entry(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = MockAdapter()
    engine = _make_engine(repo, adapter)
    events: list[tuple[str, dict]] = []
    engine.on_event = lambda kind, data: events.append((kind, data))

    engine._append_run_note(2, True, "fixed bug", "add tests")

    # No .owloop/ dir here, so run-notes falls back to the repo root (legacy layout).
    path = repo / "run-notes.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "## Iteration 2" in text
    assert "- Status: success" in text
    assert "- Summary: fixed bug" in text
    assert "- Learning: add tests" in text
    assert any(k == "run_note_appended" for k, _ in events)


def test_append_run_note_separates_entries_with_blank_line(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = MockAdapter()
    engine = _make_engine(repo, adapter)

    engine._append_run_note(1, True, "first")
    engine._append_run_note(2, False, "second")

    text = (repo / "run-notes.md").read_text(encoding="utf-8")
    # Two entries separated by a blank line.
    assert text.count("## Iteration ") == 2


def test_run_iteration_injects_context_and_logs_note(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / ".owloop" / "specs").mkdir(parents=True)
    (repo / ".owloop" / "specs" / "01-test.md").write_text("# spec", encoding="utf-8")

    adapter = MockAdapter(
        responses=[
            AgentResult(
                stdout="ok\n<promise>DONE</promise>",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>DONE</promise>",
            )
        ]
    )
    engine = _make_engine(repo, adapter)
    engine.log_dir.mkdir(parents=True, exist_ok=True)
    engine.session_log = engine.log_dir / "session.log"
    engine._write_prompt_file()

    (repo / "STEERING.md").write_text("Steer here.", encoding="utf-8")
    (repo / "run-notes.md").write_text("Note here.", encoding="utf-8")

    events: list[tuple[str, dict]] = []
    engine.on_event = lambda kind, data: events.append((kind, data))

    result = engine.run_iteration(1)

    assert result.success
    prompt, _cwd = adapter.calls[0]
    assert "Steer here." in prompt
    assert "Note here." in prompt
    assert "steering_loaded" in [k for k, _ in events]
    assert "run_notes_loaded" in [k for k, _ in events]


def test_run_appends_run_notes_after_iteration(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / ".owloop" / "specs").mkdir(parents=True)
    (repo / ".owloop" / "specs" / "01-test.md").write_text("# spec", encoding="utf-8")

    adapter = MockAdapter(
        responses=[
            AgentResult(
                stdout="plan done\n<promise>DONE</promise>",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>DONE</promise>",
            )
        ]
    )
    engine = _make_engine(repo, adapter, max_iterations=1)
    events: list[tuple[str, dict]] = []
    engine.on_event = lambda kind, data: events.append((kind, data))

    summary = engine.run()

    assert summary.iterations == 1
    # Loop metadata now lives under .owloop/ so the engine's own commits can
    # never pick it up via `git add -A`.
    run_notes = repo / ".owloop" / "run-notes.md"
    assert run_notes.is_file()
    text = run_notes.read_text(encoding="utf-8")
    assert "## Iteration 1" in text
    assert "- Status: success" in text
    assert "run_note_appended" in [k for k, _ in events]


def test_run_uses_commit_message_as_summary_when_available(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / ".owloop" / "specs").mkdir(parents=True)
    (repo / ".owloop" / "specs" / "01-test.md").write_text("# spec", encoding="utf-8")

    # Pre-seed a second commit so _check_fix_loop is safe in build mode.
    (repo / "dummy.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "agent commit message"], cwd=repo, check=True, capture_output=True)

    adapter = MockAdapter(
        responses=[
            AgentResult(
                stdout="done\n<promise>DONE</promise>",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>DONE</promise>",
            )
        ]
    )
    engine = _make_engine(repo, adapter, max_iterations=1)

    engine.run()

    text = (repo / ".owloop" / "run-notes.md").read_text(encoding="utf-8")
    assert "agent commit message" in text


def test_run_exponential_backoff_doubles_then_resets_on_success(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / ".owloop" / "specs").mkdir(parents=True)
    # Two specs so the single success (4th iteration) does not drain the queue
    # and end the run early — the loop must reach max_iterations to observe the
    # post-success backoff reset.
    (repo / ".owloop" / "specs" / "01-test.md").write_text("# spec", encoding="utf-8")
    (repo / ".owloop" / "specs" / "02-test.md").write_text("# spec", encoding="utf-8")

    sleeps: list[float] = []

    class FakeTime:
        def sleep(self, duration: float) -> None:
            sleeps.append(duration)

        def monotonic(self) -> float:
            return 0.0

    monkeypatch.setattr("owloop.engine.time", FakeTime())

    adapter = MockAdapter(
        responses=[
            AgentResult(stdout="f1", returncode=1, success=False, has_completion_signal=False),
            AgentResult(stdout="f2", returncode=1, success=False, has_completion_signal=False),
            AgentResult(stdout="f3", returncode=1, success=False, has_completion_signal=False),
            AgentResult(
                stdout="done\n<promise>DONE</promise>",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>DONE</promise>",
            ),
            # A failure *after* the success observes the reset backoff level.
            AgentResult(stdout="f4", returncode=1, success=False, has_completion_signal=False),
        ]
    )
    engine = _make_engine(
        repo,
        adapter,
        max_iterations=5,
        max_consecutive_failures=3,
        base_retry_delay=2.0,
        max_retry_delay=60.0,
        # Exercise the backoff path rather than the default hard-stop-on-stall.
        keep_retrying=True,
    )

    summary = engine.run()

    assert summary.iterations == 5
    # A verified success no longer sleeps at all and resets the backoff level,
    # so the post-success failure backs off at the base delay again.
    assert sleeps == [2.0, 2.0, 4.0, 2.0]


def test_run_exponential_backoff_continues_to_grow(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / ".owloop" / "specs").mkdir(parents=True)
    (repo / ".owloop" / "specs" / "01-test.md").write_text("# spec", encoding="utf-8")

    sleeps: list[float] = []

    class FakeTime:
        def sleep(self, duration: float) -> None:
            sleeps.append(duration)

        def monotonic(self) -> float:
            return 0.0

    monkeypatch.setattr("owloop.engine.time", FakeTime())

    responses = [
        AgentResult(stdout=f"f{i}", returncode=1, success=False, has_completion_signal=False)
        for i in range(5)
    ]
    adapter = MockAdapter(responses=responses)
    engine = _make_engine(
        repo,
        adapter,
        max_iterations=5,
        max_consecutive_failures=3,
        base_retry_delay=2.0,
        max_retry_delay=60.0,
        # Backoff continues to grow only in legacy keep-retrying mode; the
        # default would hard-stop with `stalled` after 3 failures.
        keep_retrying=True,
    )

    summary = engine.run()

    assert summary.iterations == 5
    assert sleeps == [2.0, 2.0, 4.0, 8.0, 16.0]


def test_run_blocked_signal_stops_loop_with_payload(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / ".owloop" / "specs").mkdir(parents=True)
    (repo / ".owloop" / "specs" / "01-test.md").write_text("# spec", encoding="utf-8")

    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    adapter = MockAdapter(
        responses=[
            AgentResult(
                stdout="<promise>BLOCKED:missing env var</promise>",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>BLOCKED:missing env var</promise>",
            )
        ]
    )
    engine = _make_engine(repo, adapter, max_iterations=5)
    events: list[tuple[str, dict]] = []
    engine.on_event = lambda kind, data: events.append((kind, data))

    summary = engine.run()

    assert summary.iterations == 1
    assert summary.stopped_reason == "blocked"
    assert summary.blocker == "missing env var"
    assert summary.decision_question is None
    assert any(kind == "blocked" and data.get("payload") == "missing env var" for kind, data in events)


def test_run_decide_signal_stops_loop_with_payload(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / ".owloop" / "specs").mkdir(parents=True)
    (repo / ".owloop" / "specs" / "01-test.md").write_text("# spec", encoding="utf-8")

    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    adapter = MockAdapter(
        responses=[
            AgentResult(
                stdout="<promise>DECIDE:which API to use?</promise>",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>DECIDE:which API to use?</promise>",
            )
        ]
    )
    engine = _make_engine(repo, adapter, max_iterations=5)
    events: list[tuple[str, dict]] = []
    engine.on_event = lambda kind, data: events.append((kind, data))

    summary = engine.run()

    assert summary.iterations == 1
    assert summary.stopped_reason == "decide"
    assert summary.decision_question == "which API to use?"
    assert summary.blocker is None
    assert any(kind == "decide" and data.get("payload") == "which API to use?" for kind, data in events)


def test_run_no_signal_counts_as_failure(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / ".owloop" / "specs").mkdir(parents=True)
    (repo / ".owloop" / "specs" / "01-test.md").write_text("# spec", encoding="utf-8")

    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    adapter = MockAdapter(
        responses=[
            AgentResult(
                stdout="some output without signal",
                returncode=0,
                success=True,
                has_completion_signal=False,
            )
        ]
    )
    engine = _make_engine(repo, adapter, max_iterations=1)
    events: list[tuple[str, dict]] = []
    engine.on_event = lambda kind, data: events.append((kind, data))

    summary = engine.run()

    assert summary.iterations == 1
    assert summary.stopped_reason == "max_iterations"
    assert any(kind == "no_done_signal" for kind, _ in events)
    assert not any(kind in {"blocked", "decide"} for kind, _ in events)


def test_engine_picks_dependency_ready_spec(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    engine = _make_engine(repo, MockAdapter())
    specs_dir = repo / ".owloop" / "specs"
    specs_dir.mkdir(parents=True)

    # 001-a has the lowest filename/priority but depends on 002-b, which is
    # still incomplete, so raw filename order would pick the wrong spec.
    (specs_dir / "001-a.md").write_text(
        "# Spec: a\n\n## Priority: 1\n\n## Depends On\n- 002-b\n\n"
        "## Requirements\nDo a thing.\n",
        encoding="utf-8",
    )
    (specs_dir / "002-b.md").write_text(
        "# Spec: b\n\n## Priority: 5\n\n## Requirements\nDo a thing.\n",
        encoding="utf-8",
    )
    (specs_dir / "003-c.md").write_text(
        "# Spec: c\n\n## Priority: 2\n\n## Requirements\nDo a thing.\n",
        encoding="utf-8",
    )

    status = engine._spec_status()

    assert status["first_incomplete"] == "003-c.md"


def test_copy_dot_dir_creates_target_when_missing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    engine = _make_engine(repo, MockAdapter())
    source = repo / ".owloop"
    source.mkdir()
    (source / "specs").mkdir()
    (source / "specs" / "01-test.md").write_text("# spec", encoding="utf-8")
    target_root = tmp_path / "worktree"
    target_root.mkdir()

    events: list[tuple[str, dict]] = []
    engine.on_event = lambda kind, data: events.append((kind, data))
    engine._copy_dot_dir(target_root, ".owloop", "owloop_dir_copied")

    assert (target_root / ".owloop" / "specs" / "01-test.md").read_text(encoding="utf-8") == "# spec"
    assert any(kind == "owloop_dir_copied" for kind, _ in events)


def test_copy_dot_dir_syncs_existing_target(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    engine = _make_engine(repo, MockAdapter())
    source = repo / ".owloop"
    source.mkdir()
    (source / "specs").mkdir()
    (source / "specs" / "01-old.md").write_text("# old", encoding="utf-8")
    (source / "specs" / "02-new.md").write_text("# new", encoding="utf-8")

    target_root = tmp_path / "worktree"
    target_root.mkdir()
    existing = target_root / ".owloop" / "specs"
    existing.mkdir(parents=True)
    (existing / "01-old.md").write_text("# stale", encoding="utf-8")

    events: list[tuple[str, dict]] = []
    engine.on_event = lambda kind, data: events.append((kind, data))
    engine._copy_dot_dir(target_root, ".owloop", "owloop_dir_copied")

    assert (existing / "01-old.md").read_text(encoding="utf-8") == "# old"
    assert (existing / "02-new.md").read_text(encoding="utf-8") == "# new"
    assert any(kind == "owloop_dir_copied_synced" for kind, _ in events)


def test_resolve_worktree_session_generates_unique_ids(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = MockAdapter()
    engine = _make_engine(repo, adapter)

    session_id, branch, path = engine._resolve_worktree_session()

    assert session_id
    assert branch.startswith("owloop/")
    assert session_id in branch
    assert session_id in str(path)
    # Session descriptor should be persisted in the main repo.
    assert engine._session_file().is_file()


def test_resolve_worktree_session_resumes_from_saved_session(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = MockAdapter()
    engine = _make_engine(repo, adapter, resume=True)

    # Pre-populate a previous session descriptor.
    engine._session_file().parent.mkdir(parents=True, exist_ok=True)
    engine._session_file().write_text(
        json.dumps(
            {"session_id": "abc123", "branch": "owloop/20260706-abc123", "path": "/tmp/wt"}
        ),
        encoding="utf-8",
    )

    session_id, branch, path = engine._resolve_worktree_session()

    assert session_id == "abc123"
    assert branch == "owloop/20260706-abc123"
    assert path.as_posix() == "/tmp/wt"


def test_resolve_worktree_session_resume_falls_back_to_latest_branch(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    adapter = MockAdapter()
    engine = _make_engine(repo, adapter, resume=True)

    # No session file; create a local owloop branch so there is something to resume.
    subprocess.run(["git", "branch", "owloop/20260706-xyz789"], cwd=repo, check=True, capture_output=True)

    session_id, branch, path = engine._resolve_worktree_session()

    assert session_id == "xyz789"
    assert branch == "owloop/20260706-xyz789"


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_events_jsonl_created(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = MockAdapter()
    engine = _make_engine(repo, adapter)

    events_path = engine._events_log_path()
    assert not events_path.exists()

    engine._emit("iteration_start", iteration=1)

    assert events_path.is_file()
    assert events_path.parent == engine.log_dir


def test_events_jsonl_schema(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = MockAdapter()
    engine = _make_engine(repo, adapter)
    engine.session_id = "sess123"

    engine._emit("iteration_start", iteration=1, timestamp="now")

    lines = _read_jsonl(engine._events_log_path())
    assert len(lines) == 1
    record = lines[0]
    assert {"ts", "session_id", "kind", "data"}.issubset(record.keys())
    assert record["session_id"] == "sess123"
    assert record["kind"] == "iteration_start"
    assert record["data"] == {"iteration": 1, "timestamp": "now"}


def test_events_jsonl_event_kinds(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / ".owloop" / "specs").mkdir(parents=True)
    (repo / ".owloop" / "specs" / "01-test.md").write_text("# spec", encoding="utf-8")

    adapter = MockAdapter(
        responses=[
            AgentResult(
                stdout="ok\n<promise>DONE</promise>",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>DONE</promise>",
                tokens_used=10,
            )
        ]
    )
    engine = _make_engine(repo, adapter, max_iterations=1)

    engine.run()

    kinds = {record["kind"] for record in _read_jsonl(engine._events_log_path())}
    assert "iteration_start" in kinds
    assert "iteration_end" in kinds
    assert "done_signal" in kinds


def test_on_event_callback_still_fires(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = MockAdapter()
    engine = _make_engine(repo, adapter)
    events: list[tuple[str, dict]] = []
    engine.on_event = lambda kind, data: events.append((kind, data))

    engine._emit("iteration_start", iteration=1)

    assert events == [("iteration_start", {"iteration": 1})]
    # Callback behavior is unchanged even though the event is now also logged.
    assert _read_jsonl(engine._events_log_path())[0]["kind"] == "iteration_start"


def test_engine_config_dry_run_defaults_false(tmp_path: Path) -> None:
    config = EngineConfig(project_dir=tmp_path)
    assert config.dry_run is False


def test_dry_run_stops_after_one_iteration_regardless_of_max_iterations(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / ".owloop" / "specs").mkdir(parents=True)
    (repo / ".owloop" / "specs" / "01-test.md").write_text(
        "# spec\n\n## Acceptance Criteria\n- `true`\n", encoding="utf-8"
    )
    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    adapter = MockAdapter(
        responses=[
            AgentResult(
                stdout="ok\n<promise>DONE</promise>",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>DONE</promise>",
                tokens_used=25,
            ),
            AgentResult(
                stdout="ok\n<promise>DONE</promise>",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>DONE</promise>",
            ),
        ]
    )
    engine = _make_engine(repo, adapter, dry_run=True, max_iterations=10)

    summary = engine.run()

    assert summary.iterations == 1
    assert summary.stopped_reason == "dry_run_complete"
    assert len(adapter.calls) == 1
    assert summary.dry_run_report is not None
    assert summary.dry_run_report.promise_done is True
    assert summary.dry_run_report.tokens_used == 25
    assert summary.dry_run_report.spec_name == "01-test.md"


def test_dry_run_report_counts_passed_and_failed_acceptance_criteria(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / ".owloop" / "specs").mkdir(parents=True)
    (repo / ".owloop" / "specs" / "01-test.md").write_text(
        "# spec\n\n## Acceptance Criteria\n- `true`\n- `false`\n", encoding="utf-8"
    )
    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    adapter = MockAdapter(
        responses=[
            AgentResult(
                stdout="ok\n<promise>DONE</promise>",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>DONE</promise>",
            )
        ]
    )
    engine = _make_engine(repo, adapter, dry_run=True)

    summary = engine.run()

    assert summary.dry_run_report is not None
    assert summary.dry_run_report.acceptance_passed == 1
    assert summary.dry_run_report.acceptance_failed == 1


class _CommittingAdapter(MockAdapter):
    """Simulates an agent that edits a file and commits before returning."""

    def __init__(self, repo: Path, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._repo = repo

    def run(self, prompt: str, cwd: Path, *, on_line=None) -> AgentResult:
        (self._repo / "agent_change.txt").write_text("changed", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self._repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "agent commit"], cwd=self._repo, check=True, capture_output=True
        )
        return super().run(prompt, cwd, on_line=on_line)


def test_dry_run_reverts_commit_and_skips_push(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / ".owloop" / "specs").mkdir(parents=True)
    (repo / ".owloop" / "specs" / "01-test.md").write_text(
        "# spec\n\n## Acceptance Criteria\n- `true`\n", encoding="utf-8"
    )
    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    original_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()

    adapter = _CommittingAdapter(
        repo,
        responses=[
            AgentResult(
                stdout="ok\n<promise>DONE</promise>",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>DONE</promise>",
            )
        ],
    )
    engine = _make_engine(repo, adapter, dry_run=True)

    push_calls: list[str] = []
    monkeypatch.setattr(engine, "_push", lambda branch: push_calls.append(branch))

    summary = engine.run()

    assert push_calls == []
    head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    assert head_after == original_head
    # The agent's file edit is preserved as an uncommitted change.
    assert (repo / "agent_change.txt").is_file()
    assert summary.dry_run_report is not None
    assert summary.dry_run_report.acceptance_passed == 1


class _InterruptingAdapter(MockAdapter):
    """Adapter that completes one iteration, then simulates Ctrl+C on the next."""

    def run(self, prompt: str, cwd: Path, *, on_line=None) -> AgentResult:
        if self.calls:
            raise KeyboardInterrupt
        return super().run(prompt, cwd, on_line=on_line)


def test_session_state_persisted_on_interrupt(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / ".owloop" / "specs").mkdir(parents=True)
    # Two specs so the first (successful) iteration does not drain the queue —
    # the second iteration then raises KeyboardInterrupt as intended.
    (repo / ".owloop" / "specs" / "01-test.md").write_text("# spec", encoding="utf-8")
    (repo / ".owloop" / "specs" / "02-test.md").write_text("# spec", encoding="utf-8")

    adapter = _InterruptingAdapter(
        responses=[
            AgentResult(
                stdout="ok\n<promise>DONE</promise>",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>DONE</promise>",
                tokens_used=42,
            )
        ]
    )
    engine = _make_engine(repo, adapter, max_iterations=5)

    summary = engine.run()

    assert summary.stopped_reason == "interrupted"
    assert summary.session_id

    session = json.loads(engine._session_file().read_text(encoding="utf-8"))
    assert session["session_id"] == summary.session_id
    assert session["status"] == "interrupted"
    # The engine's iteration counter increments before each attempt, so the
    # interrupted (second) attempt is counted even though it never completed.
    assert session["iterations"] == 2
    assert session["tokens_used"] == 42


def test_resume_continues_token_and_duration_budget(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / ".owloop" / "specs").mkdir(parents=True)
    # Two specs so the resumed success does not drain the queue — the loop then
    # continues and trips the carried-over token budget as intended.
    (repo / ".owloop" / "specs" / "01-test.md").write_text("# spec", encoding="utf-8")
    (repo / ".owloop" / "specs" / "02-test.md").write_text("# spec", encoding="utf-8")

    adapter = MockAdapter()
    engine = _make_engine(repo, adapter, resume=True, max_tokens=1000)

    engine._session_file().parent.mkdir(parents=True, exist_ok=True)
    engine._session_file().write_text(
        json.dumps(
            {
                "session_id": "abc123",
                "branch": "main",
                "path": str(repo),
                "status": "interrupted",
                "iterations": 3,
                "tokens_used": 800,
                "elapsed_seconds": 100.0,
                "current_spec": "01-test.md",
            }
        ),
        encoding="utf-8",
    )

    adapter._responses.append(
        AgentResult(
            stdout="ok\n<promise>DONE</promise>",
            returncode=0,
            success=True,
            has_completion_signal=True,
            done_signal="<promise>DONE</promise>",
            tokens_used=300,
        )
    )

    summary = engine.run()

    assert summary.session_id == "abc123"
    assert summary.resumed_from_session == "abc123"
    assert summary.iterations == 4
    assert summary.tokens_used == 1100
    assert summary.stopped_reason == "max_tokens"

    session = json.loads(engine._session_file().read_text(encoding="utf-8"))
    assert session["tokens_used"] == 1100
    assert session["iterations"] == 4


def test_copy_owloop_dir_skips_logs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    owloop_dir = repo / ".owloop"
    (owloop_dir / "specs").mkdir(parents=True)
    (owloop_dir / "specs" / "01-test.md").write_text("# spec", encoding="utf-8")
    (owloop_dir / "logs").mkdir()
    (owloop_dir / "logs" / "events.jsonl").write_text("{}", encoding="utf-8")

    engine = _make_engine(repo, MockAdapter())
    engine.main_repo_dir = repo
    worktree = tmp_path / "wt"
    worktree.mkdir()

    engine._copy_owloop_dir(worktree)

    assert (worktree / ".owloop" / "specs" / "01-test.md").is_file()
    # logs/ is dead weight in a fresh worktree and must not be copied.
    assert not (worktree / ".owloop" / "logs").exists()


def test_target_spec_injected_into_prompt(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    specs = repo / ".owloop" / "specs"
    specs.mkdir(parents=True)
    (specs / "02-feature.md").write_text(
        "# Spec: feature\n\n## Requirements\n- do the thing\n", encoding="utf-8"
    )

    engine = _make_engine(repo, MockAdapter())
    built = engine._build_prompt_with_context("PROMPT BODY", target_spec="02-feature.md")

    assert "## Target Spec" in built
    assert "02-feature.md" in built
    assert "do the thing" in built  # full spec content inlined
    assert built.endswith("PROMPT BODY")


def test_run_iteration_passes_engine_selected_spec_to_agent(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    specs = repo / ".owloop" / "specs"
    specs.mkdir(parents=True)
    (specs / "01-first.md").write_text("# Spec: first\n\ndetails-first\n", encoding="utf-8")
    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    adapter = MockAdapter(
        responses=[
            AgentResult(
                stdout="done\n<promise>DONE</promise>",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>DONE</promise>",
            )
        ]
    )
    engine = _make_engine(repo, adapter, max_iterations=1)
    monkeypatch.setattr(engine, "_push", lambda b: None)
    engine.run()

    prompt, _cwd = adapter.calls[0]
    assert "## Target Spec" in prompt
    assert "01-first.md" in prompt
    assert "details-first" in prompt


def test_missing_target_spec_falls_back_to_agent_discovery(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    engine = _make_engine(repo, MockAdapter())

    built = engine._build_prompt_with_context("PROMPT BODY", target_spec=None)

    assert "## Target Spec" not in built
    assert built == "PROMPT BODY"


def test_gate_failure_writes_failure_feedback(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    specs = repo / ".owloop" / "specs"
    specs.mkdir(parents=True)
    (specs / "01-test.md").write_text(
        "# Spec\n\n## Acceptance Criteria\n- check: `echo broken-thing >&2; exit 3`\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    adapter = MockAdapter(
        responses=[
            AgentResult(
                stdout="done\n<promise>DONE</promise>",
                returncode=0,
                success=True,
                has_completion_signal=True,
                done_signal="<promise>DONE</promise>",
            )
        ]
    )
    engine = _make_engine(repo, adapter, max_iterations=1)
    engine.run()

    feedback = (repo / ".owloop" / "last-failure.md").read_text(encoding="utf-8")
    assert "verification_failed" in feedback
    assert "echo broken-thing >&2; exit 3" in feedback  # the failing command
    assert "(exit 3)" in feedback  # its exit code
    assert "broken-thing" in feedback  # its output tail


def test_failure_feedback_injected_into_next_prompt_and_cleared_on_success(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    specs = repo / ".owloop" / "specs"
    specs.mkdir(parents=True)
    flag = repo / "fixed.flag"
    # Fails until the "agent" creates the flag file on its second attempt.
    (specs / "01-test.md").write_text(
        f"# Spec\n\n## Acceptance Criteria\n- check: `test -f {flag}`\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("owloop.engine.time.sleep", lambda _: None)

    class _FixingAdapter(MockAdapter):
        def run(self, prompt: str, cwd: Path, *, on_line=None) -> AgentResult:
            if len(self.calls) == 1:  # second attempt "fixes" the criterion
                flag.write_text("ok", encoding="utf-8")
            return super().run(prompt, cwd, on_line=on_line)

    done = AgentResult(
        stdout="done\n<promise>DONE</promise>",
        returncode=0,
        success=True,
        has_completion_signal=True,
        done_signal="<promise>DONE</promise>",
    )
    adapter = _FixingAdapter(responses=[done, done])
    engine = _make_engine(repo, adapter, max_iterations=2)
    monkeypatch.setattr(engine, "_push", lambda b: None)
    engine.run()

    # First prompt had no feedback; the retry prompt carried the diagnosis.
    first_prompt, _ = adapter.calls[0]
    retry_prompt, _ = adapter.calls[1]
    assert "FAILED verification" not in first_prompt
    assert "FAILED verification" in retry_prompt
    assert f"test -f {flag}" in retry_prompt
    # The verified success removed the feedback file.
    assert not (repo / ".owloop" / "last-failure.md").exists()


def test_trim_run_notes_keeps_only_newest_entries() -> None:
    from owloop.engine import trim_run_notes

    notes = "\n".join(
        f"## Iteration {i} — ts\n- Status: success\n- Summary: s{i}\n" for i in range(1, 10)
    )
    trimmed = trim_run_notes(notes, max_entries=3)

    assert "older iteration notes omitted" in trimmed
    assert "s9" in trimmed and "s8" in trimmed and "s7" in trimmed
    assert "s1" not in trimmed and "s6" not in trimmed
    # Under the cap (or unstructured content), nothing is touched.
    assert trim_run_notes("free-form note", max_entries=3) == "free-form note"
    assert trim_run_notes(notes, max_entries=20) == notes


def test_is_dirty_ignores_owloop_directory(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    adapter = MockAdapter()
    engine = _make_engine(repo, adapter)

    (repo / ".owloop" / "specs").mkdir(parents=True)
    (repo / ".owloop" / "specs" / "01-test.md").write_text("# test", encoding="utf-8")

    assert not engine._is_dirty()


def test_is_dirty_detects_other_untracked_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    adapter = MockAdapter()
    engine = _make_engine(repo, adapter)

    (repo / "untracked.txt").write_text("hi", encoding="utf-8")

    assert engine._is_dirty()


def test_is_dirty_detects_modified_tracked_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    adapter = MockAdapter()
    engine = _make_engine(repo, adapter)

    (repo / "README.md").write_text("modified", encoding="utf-8")

    assert engine._is_dirty()
