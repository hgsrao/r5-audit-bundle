"""Line coverage with the standard library only (the platform has no coverage package).

    python -m engineering_dispatcher.tests.measure_coverage
Runs the test suite under ``trace`` and reports executed / executable lines per source module.  Lines marked
``# pragma: no cover`` are excluded, as with coverage.py.
"""

from __future__ import annotations

import sys
import trace
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]


def executable_lines(path: Path) -> set[int]:
    lines = set(trace._find_executable_linenos(str(path)))
    source = path.read_text().splitlines()
    excluded: set[int] = set()
    for number, text in enumerate(source, start=1):
        if "pragma: no cover" in text:
            excluded.add(number)
            indent = len(text) - len(text.lstrip())
            if text.split("#")[0].rstrip().endswith(":"):             # exclude the whole block under a marked header
                for follow in range(number + 1, len(source) + 1):
                    nxt = source[follow - 1]
                    if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= indent:
                        break
                    excluded.add(follow)
    return lines - excluded


def main() -> int:
    import pytest

    tracer = trace.Trace(count=True, trace=False, ignoredirs=[sys.prefix, sys.exec_prefix])
    exit_code = tracer.runfunc(pytest.main, ["-q", "-p", "no:cacheprovider", "-x", str(PACKAGE / "tests")])
    counts = tracer.results().counts
    total_executable = total_hit = 0
    print(f"{'module':<34}{'lines':>7}{'hit':>6}{'cover':>8}")
    for source in sorted(p for p in PACKAGE.rglob("*.py") if "legacy" not in p.parts):   # DEPRECATED legacy code is not measured
        if "tests" in source.parts:
            continue
        lines = executable_lines(source)
        hit = {n for (filename, n), count in counts.items() if filename == str(source) and count and n in lines}
        total_executable += len(lines)
        total_hit += len(hit)
        pct = 100.0 * len(hit) / len(lines) if lines else 100.0
        print(f"{str(source.relative_to(PACKAGE)):<34}{len(lines):>7}{len(hit):>6}{pct:>7.1f}%")
        missing = sorted(lines - hit)
        if missing:
            print(f"    missing: {missing}")
    overall = 100.0 * total_hit / total_executable if total_executable else 100.0
    print(f"{'TOTAL':<34}{total_executable:>7}{total_hit:>6}{overall:>7.1f}%")
    return 0 if exit_code == 0 and overall >= 95.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
