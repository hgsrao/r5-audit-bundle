import importlib.util
import io
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("acquire", Path(__file__).resolve().parents[2] / "scripts" / "acquire_kite_metadata.py")
acq = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(acq)

CSV = (b"instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,tick_size,lot_size,instrument_type,segment,exchange\n"
       + b"".join(f"{i},{i},SYM{i},N{i},0,,0,0.05,1,EQ,NSE,NSE\n".encode() for i in range(200)))
SECRET, API_KEY, ACCESS, REQUEST = "s3cretvalue", "keyvalue123", "accesstokenvalue", "requesttok123"


def settings(tmp_path, **kw):
    base = acq.load_settings()
    base.update(output_dir=str(tmp_path / "raw"), **kw)
    return base


class FakeKite:
    instances = []

    def __init__(self, api_key):
        self.api_key, self.invalidated, self.fail_invalidate = api_key, [], False
        FakeKite.instances.append(self)

    def generate_session(self, request_token, api_secret):
        assert request_token == REQUEST and api_secret == SECRET
        return {"access_token": ACCESS, "user_id": "ZZ0000"}

    def invalidate_access_token(self, token):
        if self.fail_invalidate:
            raise RuntimeError("boom")
        self.invalidated.append(token)


class Response(io.BytesIO):
    def __init__(self, body, status=200, headers=None):
        super().__init__(body)
        self.status, self.headers = status, headers or {"Content-Type": "text/csv", "Set-Cookie": "kf_session=zzz", "Content-Length": str(len(body))}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_for(body=CSV, status=200, seen=None):
    def opener(request, timeout):
        if seen is not None:
            seen.append((request.full_url, dict(request.header_items()), timeout))
        return Response(body, status)
    return opener


def run(tmp_path, **kw):
    FakeKite.instances.clear()
    args = dict(api_key=API_KEY, api_secret=SECRET, token_text=REQUEST, kite_factory=FakeKite, opener=opener_for(), now=lambda: "T")
    args.update(kw)
    return acq.acquire(settings(tmp_path), **args)


def test_the_config_holds_no_secrets_and_names_only_environment_variables():
    text = (Path(__file__).resolve().parents[2] / "config" / "kite_connect.json").read_text()
    config = json.loads(text)
    assert config["api_key_env"] == "KITE_API_KEY" and config["api_secret_env"] == "KITE_API_SECRET"
    assert "access_token" not in config and "password" not in text.lower().replace("password/totp", "")
    assert config["exchange"] == "NSE" and config["instruments_endpoint"].startswith("https://api.kite.trade/")


def test_load_settings_requires_every_key(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"exchange": "NSE"}))
    with pytest.raises(acq.AcquisitionError, match="lacks"):
        acq.load_settings(path)


def test_credentials_come_from_the_environment_then_hidden_prompts():
    config = acq.load_settings()
    assert acq.read_credentials(config, {"KITE_API_KEY": " k ", "KITE_API_SECRET": " s "}) == ("k", "s")
    prompts = []
    assert acq.read_credentials(config, {}, prompt=lambda p: prompts.append(p) or "v") == ("v", "v")
    assert len(prompts) == 2 and all("hidden" in p for p in prompts)
    with pytest.raises(acq.AcquisitionError, match="required"):
        acq.read_credentials(config, {}, prompt=lambda p: "  ")
    assert acq.read_credentials(config, {"KITE_API_KEY": "`abc123`", "KITE_API_SECRET": ' "xyz9" '}) == ("abc123", "xyz9")
    with pytest.raises(acq.AcquisitionError, match="nothing was sent"):
        acq.read_credentials(config, {"KITE_API_KEY": "ab`c", "KITE_API_SECRET": "xyz9"})


def test_login_url_is_the_official_one():
    assert acq.login_url(acq.load_settings(), "abc") == "https://kite.zerodha.com/connect/login?v=3&api_key=abc"


@pytest.mark.parametrize("text,expected", [
    ("tok123", "tok123"), ("  tok123\n", "tok123"),
    ("https://127.0.0.1/?action=login&type=login&status=success&request_token=tok123", "tok123"),
    ("http://localhost:5000/cb?request_token=abc9&action=login&status=success", "abc9"),
    ("?status=success&request_token=tok123", "tok123")])
def test_request_token_parsing(text, expected):
    assert acq.parse_request_token(text) == expected


@pytest.mark.parametrize("text,message", [
    ("", "no request token"), ("   ", "no request token"), ("https://x/?status=failed&request_token=abc", "did not succeed"),
    ("https://x/?status=success", "alphanumeric"), ("not a token!", "alphanumeric"), ("https://x/?request_token=a$b&status=success", "alphanumeric")])
def test_request_token_refusals(text, message):
    with pytest.raises(acq.AcquisitionError, match=message):
        acq.parse_request_token(text)


def test_download_validation():
    assert acq.validate_download(200, {}, CSV) == 200
    with pytest.raises(acq.AcquisitionError, match="HTTP status 403"):
        acq.validate_download(403, {}, CSV)
    with pytest.raises(acq.AcquisitionError, match="not an instruments CSV"):
        acq.validate_download(200, {}, b'{"status":"error","message":"Invalid token"}')
    with pytest.raises(acq.AcquisitionError, match="implausibly small"):
        acq.validate_download(200, {}, CSV.split(b"\n")[0] + b"\n1,1,A,A,0,,0,0.05,1,EQ,NSE,NSE\n")


def test_successful_acquisition_saves_the_raw_bytes_unchanged_with_provenance(tmp_path):
    seen = []
    result = run(tmp_path, opener=opener_for(seen=seen))
    outdir = Path(result["outdir"])
    assert (outdir / "kite_connect_instruments_NSE.csv").read_bytes() == CSV
    assert result["sha256"] == acq.sha256_bytes(CSV) and result["rows"] == 200 and result["session_invalidated"] is True
    url, headers, timeout = seen[0]
    assert url == "https://api.kite.trade/instruments/NSE" and headers["Authorization"] == f"token {API_KEY}:{ACCESS}"
    assert headers["X-kite-version"] == "3" and timeout == 60
    record = json.loads((outdir / "ACQUISITION_RECORD.json").read_text())
    assert record["http_status"] == 200 and record["size_bytes"] == len(CSV) and record["sha256"] == acq.sha256_bytes(CSV)
    assert record["access_token_stored"] is False and record["api_secret_stored"] is False and record["endpoint"].endswith("/NSE")
    assert record["api_key_fingerprint_sha256_12"] == acq.sha256_bytes(API_KEY.encode())[:12]
    sums = (outdir / "SHA256SUMS.txt").read_text().splitlines()
    assert len(sums) == 3 and sums[0].startswith(acq.sha256_bytes(CSV))
    headers_saved = json.loads((outdir / "kite_connect_instruments_NSE.csv.headers.json").read_text())
    assert "Set-Cookie" not in headers_saved and headers_saved["Content-Type"] == "text/csv"
    assert FakeKite.instances[0].invalidated == [ACCESS]


def test_no_secret_is_ever_written_to_disk(tmp_path):
    result = run(tmp_path)
    for path in Path(result["outdir"]).rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            for secret in (SECRET, ACCESS, REQUEST):
                assert secret.encode() not in data and API_KEY.encode() not in data.replace(CSV, b"")


def test_secret_scan_deletes_a_contaminated_file_and_raises(tmp_path):
    outdir = tmp_path / "raw"
    outdir.mkdir()
    (outdir / "leak.txt").write_text(f"token={ACCESS}")
    (outdir / "clean.txt").write_text("fine")
    with pytest.raises(acq.AcquisitionError, match="secret was found"):
        acq.assert_no_secrets(outdir, [ACCESS, ""])
    assert not (outdir / "leak.txt").exists() and (outdir / "clean.txt").exists()


def test_an_error_body_or_bad_status_is_never_saved_as_data(tmp_path):
    for body, status in ((b'{"status":"error"}', 200), (CSV, 500)):
        with pytest.raises(acq.AcquisitionError):
            run(tmp_path, opener=opener_for(body, status))
        assert not (tmp_path / "raw" / "kite_connect_instruments_NSE.csv").exists()
        assert FakeKite.instances[0].invalidated == [ACCESS]                       # the session is still invalidated on failure


def test_raw_acquisitions_are_never_overwritten(tmp_path):
    run(tmp_path)
    with pytest.raises(acq.AcquisitionError, match="already exists"):
        run(tmp_path)
    assert (tmp_path / "raw" / "kite_connect_instruments_NSE.csv").read_bytes() == CSV


def test_a_failed_invalidation_is_recorded_not_fatal(tmp_path):
    class Flaky(FakeKite):
        def __init__(self, api_key):
            super().__init__(api_key)
            self.fail_invalidate = True

    result = run(tmp_path, kite_factory=Flaky)
    record = json.loads((Path(result["outdir"]) / "ACQUISITION_RECORD.json").read_text())
    assert record["session_invalidated"] is False and record["invalidate_error"] == "RuntimeError"


def test_invalidation_can_be_disabled_by_configuration(tmp_path):
    FakeKite.instances.clear()
    config = settings(tmp_path, invalidate_session_after_download=False)
    acq.acquire(config, api_key=API_KEY, api_secret=SECRET, token_text=REQUEST, kite_factory=FakeKite, opener=opener_for())
    assert FakeKite.instances[0].invalidated == []


def test_a_bad_login_stops_before_any_network_call(tmp_path):
    calls = []
    with pytest.raises(acq.AcquisitionError, match="did not succeed"):
        run(tmp_path, token_text="https://x/?status=failed", opener=lambda *a, **k: calls.append(1))
    assert calls == []


def test_main_flow_prints_the_login_url_waits_for_the_operator_and_never_prints_secrets(tmp_path, monkeypatch, capsys):
    import kiteconnect
    monkeypatch.setattr(kiteconnect, "KiteConnect", FakeKite)
    config = json.loads(Path(acq.DEFAULT_CONFIG).read_text())
    config["output_dir"] = str(tmp_path / "raw")
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps(config))
    monkeypatch.setenv("KITE_API_KEY", API_KEY)
    monkeypatch.setenv("KITE_API_SECRET", SECRET)
    monkeypatch.setattr("builtins.input", lambda prompt="": f"https://127.0.0.1/?status=success&request_token={REQUEST}")
    monkeypatch.setattr(acq, "urlopen", opener_for())
    monkeypatch.setattr(acq, "fetch_instruments", lambda s, k, t, o=None: (200, {"Content-Type": "text/csv"}, CSV, "https://api.kite.trade/instruments/NSE"))
    assert acq.main(["--config", str(cfg)]) == 0
    out = capsys.readouterr()
    assert "kite.zerodha.com/connect/login" in out.out and "Paste the redirected URL" not in out.err
    for secret in (SECRET, ACCESS, REQUEST):
        assert secret not in out.out and secret not in out.err
    assert "Saved 200 instruments" in out.out


def test_main_reports_failures_without_saving(tmp_path, monkeypatch, capsys):
    import kiteconnect
    monkeypatch.setattr(kiteconnect, "KiteConnect", FakeKite)
    config = json.loads(Path(acq.DEFAULT_CONFIG).read_text())
    config["output_dir"] = str(tmp_path / "raw")
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps(config))
    monkeypatch.setenv("KITE_API_KEY", API_KEY)
    monkeypatch.setenv("KITE_API_SECRET", SECRET)
    monkeypatch.setattr("builtins.input", lambda prompt="": "https://x/?status=failed")
    assert acq.main(["--config", str(cfg)]) == 1
    assert "ACQUISITION FAILED" in capsys.readouterr().err and not (tmp_path / "raw").exists()
    monkeypatch.setattr("builtins.input", lambda prompt="": REQUEST)
    monkeypatch.setattr(acq, "acquire", lambda *a, **k: (_ for _ in ()).throw(ValueError("network down")))
    assert acq.main(["--config", str(cfg)]) == 1
    assert "ValueError" in capsys.readouterr().err


def test_then_dispatch_goes_through_the_dispatcher_only(tmp_path, monkeypatch):
    import kiteconnect
    monkeypatch.setattr(kiteconnect, "KiteConnect", FakeKite)
    config = json.loads(Path(acq.DEFAULT_CONFIG).read_text())
    config["output_dir"] = str(tmp_path / "raw")
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps(config))
    monkeypatch.setenv("KITE_API_KEY", API_KEY)
    monkeypatch.setenv("KITE_API_SECRET", SECRET)
    monkeypatch.setattr("builtins.input", lambda prompt="": REQUEST)
    monkeypatch.setattr(acq, "fetch_instruments", lambda s, k, t, o=None: (200, {}, CSV, "u"))
    calls = []
    monkeypatch.setattr(acq.subprocess, "run", lambda cmd, cwd=None: calls.append(cmd) or type("R", (), {"returncode": 0})())
    assert acq.main(["--config", str(cfg), "--then-dispatch"]) == 0
    assert [c[-2:] for c in calls] == [["--submit", str(acq.QUALIFICATION_PACKAGE)], ["--once"][-1:] * 0 or ["dispatcher.py"] and calls[1][-2:]]
    assert all("engineering_dispatcher.dispatcher" in c for c in calls) and calls[1][-1] == "--once"


def test_dispatch_helper_stops_when_the_submit_fails(monkeypatch):
    seen = []
    monkeypatch.setattr(acq.subprocess, "run", lambda cmd, cwd=None: seen.append(cmd) or type("R", (), {"returncode": 1})())
    assert acq.dispatch_qualification("python", Path("/x")) == 2 and len(seen) == 1


def test_missing_kiteconnect_library_is_reported(monkeypatch, capsys):
    import builtins
    real_import = builtins.__import__

    def deny(name, *a, **k):
        if name == "kiteconnect":
            raise ImportError
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", deny)
    assert acq.main([]) == 2
