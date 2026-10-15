import json
from pathlib import Path

import pytest

from engineering_dispatcher.receipt_writer import RECEIPT_SCHEMA, RECENT_LIMIT, ReceiptWriter, package_digest, sha256_text
from engineering_dispatcher.tests.conftest import make_package
from engineering_dispatcher.workers.base import WorkerResult


@pytest.fixture
def writer(tmp_path):
    return ReceiptWriter(tmp_path / "receipts", tmp_path / "logs")


def ok_result(output="the answer", **kw):
    return WorkerResult("claude", True, output, None, 1.5, **kw)


def test_json_markdown_and_response_are_written(writer):
    written = writer.write(make_package(), "claude", "DONE", ok_result(), "2024-01-01T00:00:00+00:00", "2024-01-01T00:00:02+00:00")
    receipt = json.loads(Path(written["json"]).read_text())
    assert receipt["schema"] == RECEIPT_SCHEMA and receipt["state"] == "DONE" and receipt["worker"] == "claude" and receipt["ok"]
    assert receipt["output_sha256"] == sha256_text("the answer") and receipt["elapsed_seconds"] == 1.5
    assert Path(written["response"]).read_text() == "the answer" and receipt["response_file"] == "P1.response.txt"
    markdown = Path(written["markdown"]).read_text()
    assert "# Receipt P1" in markdown and "the answer" in markdown and "| state | DONE |" in markdown


def test_failed_receipt_has_error_and_no_response_file(writer):
    written = writer.write(make_package(), None, "FAILED", WorkerResult("none", False, error="no worker"), "s", "f")
    receipt = written["receipt"]
    assert receipt["error"] == "no worker" and receipt["response_file"] is None and receipt["output_sha256"] is None
    assert written["response"] is None and "## Error" in Path(written["markdown"]).read_text()


def test_long_output_is_truncated_in_markdown_only(writer):
    big = "x" * 5000
    written = writer.write(make_package(), "claude", "DONE", ok_result(big), "s", "f")
    assert len(Path(written["response"]).read_text()) == 5000 and "truncated" in Path(written["markdown"]).read_text()


def test_redispatch_never_overwrites_an_earlier_receipt(writer):
    first = writer.write(make_package(), "claude", "FAILED", WorkerResult("claude", False, error="e"), "s", "f")
    second = writer.write(make_package(), "claude", "DONE", ok_result(), "s", "f")
    third = writer.write(make_package(), "claude", "DONE", ok_result(), "s", "f")
    assert first["json"].endswith("P1.receipt.json") and second["json"].endswith("P1.attempt2.receipt.json")
    assert third["json"].endswith("P1.attempt3.receipt.json")


def test_package_digest_ignores_dispatch_section(writer):
    package = make_package()
    receipt = writer.write({**package, "dispatch": {"x": 1}}, "claude", "DONE", ok_result(), "s", "f")["receipt"]
    assert receipt["package_sha256"] == package_digest(package)


def test_recent_history_is_bounded_and_survives_a_new_writer(writer, tmp_path):
    for index in range(RECENT_LIMIT + 5):
        writer.write(make_package(f"P{index}"), "claude", "DONE", ok_result(), "s", f"f{index}")
    recent = ReceiptWriter(tmp_path / "receipts", tmp_path / "logs").recent()
    assert len(recent) == RECENT_LIMIT and recent[-1]["package_id"] == f"P{RECENT_LIMIT + 4}" and recent[0]["package_id"] == "P5"


@pytest.mark.parametrize("content", ["not json", "[]", '{"recent": 3}', '{"other": 1}'])
def test_corrupt_recent_file_reads_as_empty(writer, content):
    writer.recent_path.write_text(content)
    assert writer.recent() == []


def test_log_is_append_only_json_lines(writer):
    writer.log("START", package="P1")
    record = writer.log("END", package="P1", state="DONE")
    lines = [json.loads(line) for line in Path(writer.log_path).read_text().splitlines()]
    assert [l["event"] for l in lines] == ["START", "END"] and lines[1]["state"] == "DONE" and record["ts"]
