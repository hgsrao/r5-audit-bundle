import json
import os

import pytest

from engineering_dispatcher.tests.conftest import make_package
from engineering_dispatcher.queue_manager import PackageError, QueueError, QueueManager, validate_package


@pytest.fixture
def queue(tmp_path):
    return QueueManager(tmp_path / "queue")


def test_all_five_states_exist_and_start_empty(queue):
    assert queue.counts() == {"READY": 0, "RUNNING": 0, "DONE": 0, "FAILED": 0, "REVIEW": 0}


@pytest.mark.parametrize("mutation,message", [
    ({"id": ""}, "id is required"), ({"id": "../x"}, "id may contain"), ({"id": ".hidden"}, "id may contain"),
    ({"type": " "}, "type is required"), ({"objective": 5}, "objective"), ({"prompt": ""}, "prompt"),
    ({"extra": 1}, "unknown fields"), ({"rules": "x"}, "rules must be"), ({"priority": True}, "priority"),
    ({"priority": "1"}, "priority"), ({"files": [""]}, "non-empty"), ({"depends_on": [3]}, "non-empty"),
    ({"metadata": []}, "metadata"), ({"requires_review": "yes"}, "requires_review")])
def test_package_validation(mutation, message):
    with pytest.raises(PackageError, match=message):
        validate_package(make_package(**mutation))


def test_non_object_package_rejected():
    with pytest.raises(PackageError, match="JSON object"):
        validate_package(["x"])


def test_defaults_are_filled(queue):
    stored = queue.submit(make_package())
    assert stored["rules"] == [] and stored["priority"] == 0 and stored["depends_on"] == [] and "submitted_at" in stored
    assert queue.state_of("P1") == "READY" and queue.get("P1")[0] == "READY"


def test_duplicate_ids_are_refused_in_any_state(queue):
    queue.submit(make_package())
    with pytest.raises(QueueError, match="already exists"):
        queue.submit(make_package())
    queue.claim_next()
    with pytest.raises(QueueError, match="already exists"):
        queue.submit(make_package())


def test_priority_then_age_then_id_ordering(queue):
    queue.submit(make_package("b", priority=1, submitted_at="2024-01-02"))
    queue.submit(make_package("a", priority=1, submitted_at="2024-01-02"))
    queue.submit(make_package("c", priority=5, submitted_at="2024-01-03"))
    queue.submit(make_package("d", priority=1, submitted_at="2024-01-01"))
    assert queue.peek_order() == ["c", "d", "a", "b"]
    assert [queue.claim_next()["id"] for _ in range(4)] == ["c", "d", "a", "b"]
    assert queue.claim_next() is None


def test_dependencies_block_selection_until_done(queue):
    queue.submit(make_package("child", depends_on=["parent"], priority=9))
    queue.submit(make_package("parent"))
    first = queue.claim_next()
    assert first["id"] == "parent" and queue.claim_next() is None                 # child still blocked (parent RUNNING)
    queue.complete("parent", "DONE", {"ok": True})
    assert queue.claim_next()["id"] == "child"


def test_failed_dependency_keeps_child_blocked(queue):
    queue.submit(make_package("child", depends_on=["parent"]))
    queue.submit(make_package("parent"))
    queue.claim_next()
    queue.complete("parent", "FAILED", {})
    assert queue.claim_next() is None and queue.ids("READY") == ["child"]


def test_complete_records_dispatch_info_and_moves_state(queue):
    queue.submit(make_package())
    queue.claim_next()
    assert queue.counts()["RUNNING"] == 1
    done = queue.complete("P1", "REVIEW", {"worker": "claude"})
    assert done["dispatch"] == {"worker": "claude"} and queue.state_of("P1") == "REVIEW"
    assert queue.counts() == {"READY": 0, "RUNNING": 0, "DONE": 0, "FAILED": 0, "REVIEW": 1}
    assert queue.get("P1")[1]["dispatch"]["worker"] == "claude"


def test_complete_rejects_bad_state_or_missing_running(queue):
    queue.submit(make_package())
    with pytest.raises(QueueError, match="only complete into"):
        queue.complete("P1", "READY", {})
    with pytest.raises(QueueError, match="not RUNNING"):
        queue.complete("P1", "DONE", {})


def test_unknown_state_and_unknown_package(queue):
    with pytest.raises(QueueError, match="unknown queue state"):
        queue.ids("BOGUS")
    with pytest.raises(QueueError, match="no such package"):
        queue.get("nope")
    assert queue.state_of("nope") is None


def test_malformed_ready_file_is_quarantined_not_blocking(queue):
    (queue.root / "READY" / "broken.json").write_text("{not json")
    queue.submit(make_package())
    assert queue.claim_next()["id"] == "P1"
    assert queue.ids("FAILED") == ["broken"] and queue.ids("READY") == []
    assert queue.peek_order() == []


def test_peek_order_skips_unreadable_entries(queue):
    (queue.root / "READY" / "broken.json").write_text("[]")
    queue.submit(make_package())
    assert queue.peek_order() == ["P1"]


def test_unreadable_known_package_raises(queue):
    (queue.root / "DONE" / "x.json").write_text("garbage")
    with pytest.raises(QueueError, match="unreadable"):
        queue.get("x")


def test_requeue_running_increments_attempts(queue):
    queue.submit(make_package())
    queue.submit(make_package("Q"))
    queue.claim_next(), queue.claim_next()
    assert queue.requeue_running("P1", note="boom") == ["P1"]
    assert queue.get("P1")[1]["dispatch"]["requeues"] == 1 and queue.state_of("Q") == "RUNNING"
    assert sorted(queue.requeue_running()) == ["Q"]
    queue.claim_next()
    queue.requeue_running("P1")
    assert queue.get("P1")[1]["dispatch"]["requeues"] == 2
    assert queue.requeue_running("not-running") == []


def test_claim_race_loser_moves_on(queue, monkeypatch):
    queue.submit(make_package("a"))
    queue.submit(make_package("b"))
    real_replace = os.replace
    calls = []

    def racing(source, target):
        calls.append(source)
        if len(calls) == 1:
            real_replace(source, queue.root / "RUNNING" / "stolen-by-other.json")   # another dispatcher took 'a' first
            raise FileNotFoundError(source)
        return real_replace(source, target)

    monkeypatch.setattr(os, "replace", racing)
    assert queue.claim_next()["id"] == "b"


def test_atomic_write_cleans_up_on_failure(queue, monkeypatch):
    import engineering_dispatcher.queue_manager as module
    monkeypatch.setattr(module.json, "dump", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk")))
    with pytest.raises(RuntimeError):
        queue.submit(make_package())
    assert list((queue.root / "READY").iterdir()) == []


def test_atomic_write_survives_missing_temp_on_cleanup(queue, monkeypatch):
    import engineering_dispatcher.queue_manager as module
    real_unlink = os.unlink

    def vanish(path):
        real_unlink(path)
        raise FileNotFoundError(path)

    monkeypatch.setattr(module.json, "dump", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk")))
    monkeypatch.setattr(module.os, "unlink", vanish)
    with pytest.raises(RuntimeError, match="disk"):
        queue.submit(make_package())


def test_quarantine_of_vanished_file_is_harmless(queue):
    queue._quarantine("ghost")
    assert queue.ids("FAILED") == []


def test_submitted_files_are_valid_json_on_disk(queue):
    queue.submit(make_package())
    data = json.loads((queue.root / "READY" / "P1.json").read_text())
    assert data["id"] == "P1"


def make_stale(queue, package_id, **change):
    from engineering_dispatcher.queue_manager import _atomic_write
    owner = queue.owner_of(package_id)
    owner.update(change)
    _atomic_write(queue._owner_path(package_id), owner)


def test_claim_records_the_owner_and_completion_releases_it(queue):
    queue.submit(make_package("P1"))
    queue.claim_next()
    owner = queue.owner_of("P1")
    assert owner["pid"] == os.getpid() and owner["package"] == "P1" and owner["start_ticks"]
    queue.complete("P1", "DONE", {})
    assert queue.owner_of("P1") is None


def test_a_running_package_is_reclaimable_only_if_the_owner_is_gone_or_the_heartbeat_expired(tmp_path):
    now = [1000.0]
    queue = QueueManager(tmp_path / "q", heartbeat_timeout=300, clock=lambda: now[0])
    for name in ("LIVE", "DEAD", "REUSED", "SILENT", "REMOTE"):
        queue.submit(make_package(name))
    while queue.claim_next():
        pass
    make_stale(queue, "DEAD", pid=2 ** 22 + 12345)                                    # no such process
    make_stale(queue, "REUSED", start_ticks="1")                                      # pid alive but a different process
    make_stale(queue, "SILENT", heartbeat=1000.0 - 301)                               # alive, heartbeat expired
    make_stale(queue, "REMOTE", host="another-host", heartbeat=1000.0 - 10)           # other host: heartbeat only, still fresh
    assert [queue.is_reclaimable(n) for n in ("LIVE", "DEAD", "REUSED", "SILENT", "REMOTE")] == [False, True, True, True, False]
    assert sorted(queue.reclaim_stale("test")) == ["DEAD", "REUSED", "SILENT"]
    assert sorted(queue.ids("RUNNING")) == ["LIVE", "REMOTE"] and queue.owner_of("DEAD") is None
    now[0] += 400
    make_stale(queue, "REMOTE", host="another-host", heartbeat=1000.0)               # heartbeat now 400 s old
    assert queue.is_reclaimable("LIVE") is True                                       # a silent owner loses its package once the timeout passes
    assert queue.reclaim_stale("test") == ["LIVE", "REMOTE"] and queue.ids("RUNNING") == []


def test_a_running_package_without_an_owner_record_is_judged_by_its_file_age(tmp_path):
    now = [os.stat(tmp_path).st_mtime]
    queue = QueueManager(tmp_path / "q", heartbeat_timeout=300, clock=lambda: now[0])
    queue.submit(make_package("P1"))
    queue.claim_next()
    queue._owner_path("P1").unlink()
    now[0] = queue._path("RUNNING", "P1").stat().st_mtime + 10
    assert not queue.is_reclaimable("P1")
    now[0] += 400
    assert queue.is_reclaimable("P1") and queue.reclaim_stale("x") == ["P1"]
    assert not queue.is_reclaimable("not-running")


def test_heartbeat_only_by_the_owner(queue):
    queue.submit(make_package("P1"))
    queue.claim_next()
    assert queue.heartbeat("P1") is True
    make_stale(queue, "P1", pid=os.getpid() + 1)
    assert queue.heartbeat("P1") is False and queue.heartbeat("missing") is False


def test_owner_is_alive_for_this_process_and_not_for_a_dead_pid():
    from engineering_dispatcher.queue_manager import current_owner, owner_is_alive
    assert owner_is_alive(current_owner()) and not owner_is_alive({**current_owner(), "pid": 2 ** 22 + 99})
    assert owner_is_alive({**current_owner(), "host": "elsewhere"}) and not owner_is_alive({"host": current_owner()["host"]})
