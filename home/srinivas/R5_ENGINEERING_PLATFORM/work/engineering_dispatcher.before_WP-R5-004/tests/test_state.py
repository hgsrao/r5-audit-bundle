from engineering_dispatcher.state_manager import BEGIN, END, StateManager


def snapshot(**overrides):
    base = {"queue": {"READY": 2, "RUNNING": 1, "DONE": 3, "FAILED": 0, "REVIEW": 1}, "running": ["P9"],
            "recent": [{"package_id": "P1", "state": "DONE", "worker": "claude", "finished_at": "t1"},
                       {"package_id": "P2", "state": "REVIEW", "worker": "qwen", "finished_at": "t2"}],
            "updated_at": "2024-01-01T00:00:00+00:00"}
    base.update(overrides)
    return base


def manager(tmp_path):
    return StateManager(tmp_path / "CURRENT_STATE.md", tmp_path / "R5_HANDOVER.md", tmp_path / "archive")


def test_block_renders_counts_running_and_recent(tmp_path):
    block = manager(tmp_path).render_block(snapshot())
    assert block.startswith(BEGIN) and block.rstrip().endswith(END)
    assert "| 2 | 1 | 3 | 0 | 1 |" in block and "Running: P9" in block
    assert block.index("P2") < block.index("P1")                                  # newest first
    assert "No packages dispatched yet." in manager(tmp_path).render_block(snapshot(recent=[], running=[]))
    assert "Running: none" in manager(tmp_path).render_block(snapshot(running=[]))


def test_missing_current_state_is_created(tmp_path):
    state = manager(tmp_path)
    state.update_current_state(snapshot())
    text = (tmp_path / "CURRENT_STATE.md").read_text()
    assert text.startswith("# CURRENT_STATE") and BEGIN in text


def test_existing_content_is_preserved_and_block_is_replaced_in_place(tmp_path):
    path = tmp_path / "CURRENT_STATE.md"
    path.write_text("# CURRENT_STATE\n\nHuman prose line.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n## Footer\ntail text\n")
    state = manager(tmp_path)
    state.update_current_state(snapshot())
    first = path.read_text()
    assert first.startswith("# CURRENT_STATE\n\nHuman prose line.") and first.count(BEGIN) == 1
    state.update_current_state(snapshot(queue={"READY": 0, "RUNNING": 0, "DONE": 9, "FAILED": 0, "REVIEW": 0}, running=[]))
    second = path.read_text()
    assert second.count(BEGIN) == 1 and "| 0 | 0 | 9 | 0 | 0 |" in second and "| 2 | 1 | 3 | 0 | 1 |" not in second
    assert second.startswith("# CURRENT_STATE\n\nHuman prose line.") and "Human prose line." in second


def test_block_in_the_middle_keeps_the_tail(tmp_path):
    path = tmp_path / "CURRENT_STATE.md"
    path.write_text(f"top\n{BEGIN}\nold\n{END}\n\n## Tail\nkeep me\n")
    manager(tmp_path).update_current_state(snapshot())
    text = path.read_text()
    assert "old" not in text and text.startswith("top\n") and text.rstrip().endswith("keep me")


def test_reversed_markers_are_treated_as_absent(tmp_path):
    path = tmp_path / "CURRENT_STATE.md"
    path.write_text(f"{END}\nx\n{BEGIN}\n")
    manager(tmp_path).update_current_state(snapshot())
    assert path.read_text().count(BEGIN) == 2


def test_handover_is_written_with_exception_and_requeue_info(tmp_path):
    state = manager(tmp_path)
    path = state.write_handover("boom", snapshot(), ["P9"], "Traceback...\nValueError: x")
    text = path.read_text()
    assert path == tmp_path / "R5_HANDOVER.md" and "Returned to READY for re-dispatch: P9" in text
    assert "```text" in text and "ValueError: x" in text and "--drain" in text and "boom" in text
    assert not (tmp_path / "archive").exists()


def test_existing_handover_is_archived_not_destroyed(tmp_path):
    (tmp_path / "R5_HANDOVER.md").write_text("HUMAN HANDOVER")
    manager(tmp_path).write_handover("why", snapshot(), [], "")
    archived = list((tmp_path / "archive").glob("R5_HANDOVER.*.md"))
    assert len(archived) == 1 and archived[0].read_text() == "HUMAN HANDOVER"
    text = (tmp_path / "R5_HANDOVER.md").read_text()
    assert "No package was RUNNING." in text and "## Exception" not in text


def test_atomic_text_cleans_up_when_the_write_fails(tmp_path, monkeypatch):
    import os

    import engineering_dispatcher.state_manager as module
    monkeypatch.setattr(module.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("full")))
    try:
        manager(tmp_path).update_current_state(snapshot())
    except OSError:
        pass
    assert [p for p in tmp_path.iterdir() if p.name.startswith(".tmp-")] == []
    monkeypatch.setattr(module.os, "unlink", lambda p: (_ for _ in ()).throw(FileNotFoundError(p)))
    try:
        manager(tmp_path).update_current_state(snapshot())
    except OSError:
        pass
