import json
from pathlib import Path

import pytest

from engineering_dispatcher.dispatcher import Dispatcher
from engineering_dispatcher.tests.conftest import FakeWorker, make_config, make_package


@pytest.fixture
def dispatcher(config, fakes):
    return Dispatcher(config, workers=fakes, sleep=lambda s: None)


def submit(dispatcher, *packages):
    for package in packages:
        dispatcher.queue.submit(package)


def test_empty_queue_dispatches_nothing(dispatcher):
    assert dispatcher.run_once() is None and dispatcher.run() == []


def test_full_cycle_receipts_state_and_log(dispatcher, fakes, config):
    submit(dispatcher, make_package("A", type="CODE_IMPLEMENTATION"), make_package("B", type="REVIEW_CODE"))
    outcomes = dispatcher.run()
    assert [(o.package_id, o.worker, o.state) for o in outcomes] == [("A", "claude", "DONE"), ("B", "qwen", "DONE")]
    assert dispatcher.queue.counts() == {"READY": 0, "RUNNING": 0, "DONE": 2, "FAILED": 0, "REVIEW": 0}
    receipt = json.loads(Path(outcomes[0].receipt_json).read_text())
    assert receipt["package_id"] == "A" and receipt["state"] == "DONE" and Path(outcomes[0].receipt_markdown).read_text()
    state_text = config.current_state_path.read_text()
    assert "| 0 | 0 | 2 | 0 | 0 |" in state_text and "| A | DONE | claude" in state_text
    events = [json.loads(l)["event"] for l in Path(dispatcher.receipts.log_path).read_text().splitlines()]
    assert events == ["START", "DISPATCH", "END", "START", "DISPATCH", "END"]
    assert dispatcher.queue.get("A")[1]["dispatch"]["receipt"] == outcomes[0].receipt_json
    assert not config.handover_path.exists()                                           # a clean run writes no handover


def test_priority_and_dependencies_are_respected_end_to_end(dispatcher, fakes):
    submit(dispatcher, make_package("late", priority=0), make_package("urgent", priority=9),
           make_package("child", priority=9, depends_on=["late"]))
    order = [o.package_id for o in dispatcher.run()]
    assert order == ["urgent", "late", "child"]


def test_failed_worker_result_is_failed_and_receipted(config):
    dispatcher = Dispatcher(config, workers={"claude": FakeWorker("claude", ok=False, error="exit 2")}, sleep=lambda s: None)
    submit(dispatcher, make_package("A"))
    [outcome] = dispatcher.run()
    assert outcome.state == "FAILED" and dispatcher.queue.state_of("A") == "FAILED"
    assert json.loads(Path(outcome.receipt_json).read_text())["error"] == "exit 2"


def test_review_state_for_flagged_packages_and_worker_requests(config):
    dispatcher = Dispatcher(config, workers={"claude": FakeWorker("claude"), "qwen": FakeWorker("qwen", needs_review=True)},
                            sleep=lambda s: None)
    submit(dispatcher, make_package("A", requires_review=True, worker="qwen"), make_package("B", type="REVIEW_CODE"))
    # FakeWorker only reports needs_review when told; the package flag alone is honoured by real workers (see worker tests)
    states = {o.package_id: o.state for o in dispatcher.run()}
    assert states == {"A": "REVIEW", "B": "REVIEW"} and dispatcher.queue.counts()["REVIEW"] == 2


def test_routing_failure_becomes_a_failed_receipt_without_a_worker(config):
    dispatcher = Dispatcher(config, workers={"claude": FakeWorker("claude")}, sleep=lambda s: None)
    submit(dispatcher, make_package("A", worker="gemini"))
    [outcome] = dispatcher.run()
    assert outcome.state == "FAILED" and outcome.worker is None
    assert "disabled" in json.loads(Path(outcome.receipt_json).read_text())["error"]


def test_worker_exception_inside_execute_is_a_unexpected_exit_with_requeue_and_handover(config):
    worker = FakeWorker("claude", raises=KeyboardInterrupt())
    dispatcher = Dispatcher(config, workers={"claude": worker}, sleep=lambda s: None)
    submit(dispatcher, make_package("A"), make_package("B"))
    with pytest.raises(KeyboardInterrupt):
        dispatcher.run()
    assert dispatcher.queue.state_of("A") == "READY" and dispatcher.queue.get("A")[1]["dispatch"]["requeues"] == 1
    text = config.handover_path.read_text()
    assert "KeyboardInterrupt" in text and "Returned to READY for re-dispatch: A" in text and "Traceback" in text
    assert "UNEXPECTED_EXIT" in Path(dispatcher.receipts.log_path).read_text()
    assert "| 2 | 0 | 0 | 0 | 0 |" in config.current_state_path.read_text()


def test_plain_exceptions_in_the_pipeline_also_produce_a_handover(config, fakes, monkeypatch):
    dispatcher = Dispatcher(config, workers=fakes, sleep=lambda s: None)
    submit(dispatcher, make_package("A"))
    monkeypatch.setattr(dispatcher.queue, "complete", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("queue corrupted")))
    with pytest.raises(RuntimeError, match="queue corrupted"):
        dispatcher.run()
    assert "queue corrupted" in config.handover_path.read_text() and dispatcher.queue.state_of("A") == "READY"


def test_bookkeeping_failures_never_mask_the_original_exception(config, fakes, monkeypatch):
    dispatcher = Dispatcher(config, workers=fakes, sleep=lambda s: None)
    submit(dispatcher, make_package("A"))
    monkeypatch.setattr(dispatcher.queue, "complete", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("original")))
    real_requeue, calls = dispatcher.queue.requeue_running, []

    def flaky_requeue(*a, **k):
        calls.append(1)
        if len(calls) > 1:                                      # the start-up recovery works; the exit-time requeue fails
            raise OSError("fs")
        return real_requeue(*a, **k)

    monkeypatch.setattr(dispatcher.queue, "requeue_running", flaky_requeue)
    monkeypatch.setattr(dispatcher.state, "write_handover", lambda *a, **k: (_ for _ in ()).throw(OSError("fs2")))
    with pytest.raises(RuntimeError, match="original"):
        dispatcher.run()


def test_previously_running_packages_are_recovered_at_start(config, fakes):
    first = Dispatcher(config, workers=fakes, sleep=lambda s: None)
    submit(first, make_package("A"))
    first.queue.claim_next()                                                         # a crashed dispatcher left A RUNNING
    second = Dispatcher(config, workers=fakes, sleep=lambda s: None)
    assert [o.package_id for o in second.run()] == ["A"]
    assert "RECOVERED" in Path(second.receipts.log_path).read_text()
    assert second.queue.get("A")[1]["dispatch"]["state"] == "DONE"


def test_max_packages_limits_the_run(dispatcher):
    submit(dispatcher, make_package("A"), make_package("B"), make_package("C"))
    assert [o.package_id for o in dispatcher.run(max_packages=2)] == ["A", "B"]
    assert dispatcher.queue.ids("READY") == ["C"]


def test_watch_mode_polls_until_interrupted(config, fakes):
    polls = []

    def sleep(seconds):
        polls.append(seconds)
        if len(polls) == 2:
            raise KeyboardInterrupt

    dispatcher = Dispatcher(config, workers=fakes, sleep=sleep)
    submit(dispatcher, make_package("A"))
    with pytest.raises(KeyboardInterrupt):
        dispatcher.run(stop_when_empty=False)
    assert polls == [config.poll_seconds, config.poll_seconds] and dispatcher.queue.state_of("A") == "DONE"
    assert config.handover_path.exists()


def test_snapshot_reports_queue_running_and_recent(dispatcher):
    submit(dispatcher, make_package("A"), make_package("B"))
    dispatcher.queue.claim_next()
    snapshot = dispatcher.snapshot()
    assert snapshot["queue"]["READY"] == 1 and snapshot["running"] == ["A"] and snapshot["recent"] == [] and snapshot["updated_at"]


def test_default_construction_builds_real_adapters_from_configuration(tmp_path):
    config = make_config(tmp_path / "p")
    dispatcher = Dispatcher(config)
    assert set(dispatcher.router.workers) == {"claude", "qwen", "gemini", "auditor"}


def test_current_state_shows_the_package_as_running_while_it_runs(config):
    observed = []

    class Probe(FakeWorker):
        def execute(self, package):
            observed.append(config.current_state_path.read_text())
            return super().execute(package)

    dispatcher = Dispatcher(config, workers={"claude": Probe("claude")}, sleep=lambda s: None)
    submit(dispatcher, make_package("A"))
    dispatcher.run()
    assert "| 0 | 1 | 0 | 0 | 0 |" in observed[0] and "Running: A" in observed[0]            # visible DURING execution
    assert "| 0 | 0 | 1 | 0 | 0 |" in config.current_state_path.read_text()                    # and updated again afterwards
