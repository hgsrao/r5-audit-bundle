import json

from engineering_dispatcher.dispatcher import build_parser, main
from engineering_dispatcher.tests.conftest import FakeWorker, make_package


def config_file(tmp_path, extra=None):
    payload = {"platform_root": str(tmp_path / "platform"), "poll_seconds": 0,
               "workers": {"claude": {"command": ["claude", "-p"]}, "qwen": {"model": "m"}}}
    payload.update(extra or {})
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload))
    return str(path)


def workers():
    return {"claude": FakeWorker("claude"), "qwen": FakeWorker("qwen"), "gemini": FakeWorker("gemini")}


def test_submit_status_and_drain_flow(tmp_path, capsys):
    cfg = config_file(tmp_path)
    package = tmp_path / "pkg.json"
    package.write_text(json.dumps(make_package("CLI-1")))
    assert main(["--config", cfg, "--submit", str(package)], workers=workers()) == 0
    assert "submitted CLI-1" in capsys.readouterr().out
    assert main(["--config", cfg, "--status"], workers=workers()) == 0
    assert json.loads(capsys.readouterr().out)["queue"]["READY"] == 1
    assert main(["--config", cfg], workers=workers()) == 0
    assert "CLI-1\tDONE\tclaude" in capsys.readouterr().out


def test_once_dispatches_a_single_package(tmp_path, capsys):
    cfg = config_file(tmp_path)
    for name in ("A", "B"):
        (tmp_path / f"{name}.json").write_text(json.dumps(make_package(name)))
        assert main(["--config", cfg, "--submit", str(tmp_path / f"{name}.json")], workers=workers()) == 0
    capsys.readouterr()
    assert main(["--config", cfg, "--once"], workers=workers()) == 0
    assert capsys.readouterr().out.count("DONE") == 1


def test_failed_packages_give_a_nonzero_exit_code(tmp_path, capsys):
    cfg = config_file(tmp_path)
    (tmp_path / "p.json").write_text(json.dumps(make_package("A")))
    main(["--config", cfg, "--submit", str(tmp_path / "p.json")], workers=workers())
    failing = {"claude": FakeWorker("claude", ok=False), "qwen": FakeWorker("qwen"), "gemini": FakeWorker("gemini")}
    assert main(["--config", cfg, "--drain"], workers=failing) == 1


def test_bad_configuration_exits_2(tmp_path, capsys):
    assert main(["--config", str(tmp_path / "nope.json")]) == 2
    assert "configuration error" in capsys.readouterr().err
    cfg = config_file(tmp_path, {"default_worker": "ghost"})
    assert main(["--config", cfg]) == 2


def test_submit_refusals_exit_2(tmp_path, capsys):
    cfg = config_file(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text("{nope")
    assert main(["--config", cfg, "--submit", str(bad)], workers=workers()) == 2
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"id": "x"}))
    assert main(["--config", cfg, "--submit", str(invalid)], workers=workers()) == 2
    assert main(["--config", cfg, "--submit", str(tmp_path / "missing.json")], workers=workers()) == 2
    good = tmp_path / "good.json"
    good.write_text(json.dumps(make_package("D")))
    assert main(["--config", cfg, "--submit", str(good)], workers=workers()) == 0
    assert main(["--config", cfg, "--submit", str(good)], workers=workers()) == 2          # duplicate
    assert "submit refused" in capsys.readouterr().err


def test_parser_modes_are_mutually_exclusive():
    parser = build_parser()
    assert parser.parse_args(["--watch"]).watch
    try:
        parser.parse_args(["--once", "--drain"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("modes must be exclusive")


def test_sigterm_handler_turns_a_signal_into_a_system_exit_and_main_installs_it(tmp_path, monkeypatch):
    import signal

    import pytest

    from engineering_dispatcher import dispatcher as module
    with pytest.raises(SystemExit) as exit_info:
        module._terminate(signal.SIGTERM, None)
    assert exit_info.value.code == 128 + signal.SIGTERM
    installed = []
    monkeypatch.setattr(module.signal, "signal", lambda number, handler: installed.append((number, handler)))
    assert main(["--config", config_file(tmp_path), "--drain"], workers=workers(), install_signals=True) == 0
    assert installed == [(signal.SIGTERM, module._terminate)]


def test_a_sigterm_during_dispatch_requeues_and_writes_the_handover(tmp_path):
    cfg = config_file(tmp_path)
    (tmp_path / "p.json").write_text(json.dumps(make_package("A")))
    main(["--config", cfg, "--submit", str(tmp_path / "p.json")], workers=workers())
    import pytest
    with pytest.raises(SystemExit):
        main(["--config", cfg], workers={"claude": FakeWorker("claude", raises=SystemExit(143)), "qwen": FakeWorker("qwen"),
                                         "gemini": FakeWorker("gemini")})
    assert (tmp_path / "platform" / "R5_HANDOVER.md").exists()
    assert (tmp_path / "platform" / "queue" / "READY" / "A.json").exists()
