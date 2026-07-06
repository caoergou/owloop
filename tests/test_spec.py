"""Tests for spec content classification."""

from owloop.cli import classify_spec


def test_classify_done_status():
    content = "# Spec\n\nStatus: COMPLETE\n"
    assert classify_spec(content) == "done"


def test_classify_done_status_lowercase():
    content = "# Spec\n\nstatus: complete\n"
    assert classify_spec(content) == "done"


def test_classify_done_status_bold():
    content = "# Spec\n\n**Status**: COMPLETE\n"
    assert classify_spec(content) == "done"


def test_classify_in_progress_status():
    content = "# Spec\n\nStatus: In Progress\n"
    assert classify_spec(content) == "in_progress"


def test_classify_in_progress_status_bold():
    content = "# Spec\n\n**Status**: In Progress\n"
    assert classify_spec(content) == "in_progress"


def test_classify_in_progress_checked_box():
    content = "## Requirements\n- [x] did the thing\n- [ ] todo\n"
    assert classify_spec(content) == "in_progress"


def test_classify_in_progress_checked_box_uppercase():
    content = "## Requirements\n- [X] did the thing\n"
    assert classify_spec(content) == "in_progress"


def test_classify_pending_empty():
    assert classify_spec("") == "pending"


def test_classify_pending_no_markers():
    content = "## Requirements\n- [ ] TODO: describe what needs to be done\n"
    assert classify_spec(content) == "pending"
