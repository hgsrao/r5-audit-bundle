"""SYNTHETIC fixtures only: deterministic pseudo-random OHLCV, no real market data, no real symbols' prices."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

IST = timezone(timedelta(hours=5, minutes=30))
GRID_NAMES = {"NIFTY_50_15MIN": "timestamp", "INDIA_VIX_15MIN": "date"}
FILE_TEMPLATE = "NSE_{sym}_minute_2023-07-03_2026-08-24.csv"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stamp(day: date, minute_of_session: int) -> str:
    t = datetime(day.year, day.month, day.day, 9, 15, tzinfo=IST) + timedelta(minutes=minute_of_session)
    return t.isoformat()


def stock_rows(symbol, days, bars, seed, base):
    rng = np.random.RandomState(abs(hash(symbol)) % 1000 + seed)
    rows, price = [], base
    for day in days:
        for m in range(bars):
            move = rng.normal(0, 0.15)
            o = round(price, 2)
            c = round(max(1.0, price + move), 2)
            h = round(max(o, c) + abs(rng.normal(0, 0.05)), 2)
            lo = round(min(o, c) - abs(rng.normal(0, 0.05)), 2)
            rows.append((stamp(day, m), o, h, max(0.5, lo), c, int(abs(rng.normal(1000, 200))) + 1))
            price = c
    return rows


def render(rows, *, header="timestamp,open,high,low,close,volume", newline="\n", bom=False):
    text = header + newline + newline.join(",".join(str(x) for x in r) for r in rows) + newline
    return (b"\xef\xbb\xbf" if bom else b"") + text.encode()


def grid_rows(days, step=15, bars=26):
    rng = np.random.RandomState(7)
    rows, level = [], 100.0
    for day in days:
        for k in range(bars):
            level = max(1.0, level + rng.normal(0, 0.2))
            rows.append((stamp(day, k * step), round(level, 2)))
    return rows


def weekdays(start: date, n: int):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


class World:
    """root/ (manifest roots), data/ (market csv), grid/ (feeds); everything synthetic."""

    def __init__(self, base: Path, **opt):
        self.base = Path(base)
        self.opt = opt
        self.symbols = opt.get("symbols", ("AAA", "BBB"))
        self.bars = opt.get("bars", 40)
        self.warmup = opt.get("warmup", 60)
        self.root = self.base / "root"
        self.data = self.base / "data"
        self.grid = self.base / "grid"
        for p in (self.root / "revision2", self.root / "local_workspace" / "records", self.data, self.grid):
            p.mkdir(parents=True, exist_ok=True)
        days = weekdays(date(2023, 11, 29), 12)
        self.pre = days[:3]                      # 120 warmup-capable bars before the block
        self.target = days[3:5]
        self.post = days[5:8]                    # sentinel day + poison tail
        self.sessions = [d.isoformat() for d in self.target]
        self.train_end = opt.get("train_end", "2025-07-01")
        self.write()

    def csv_path(self, sym):
        return self.data / FILE_TEMPLATE.format(sym=sym)

    def build_rows(self, sym):
        all_days = self.pre + self.target + self.post
        return stock_rows(sym, all_days, self.bars, 1, 100.0 + 10 * self.symbols.index(sym))

    def write(self):
        o = self.opt
        records = []
        for sym in self.symbols:
            rows = self.build_rows(sym)
            true_extent = (rows[0][0], rows[-1][0], len(rows))
            if "mutate_rows" in o:
                rows = o["mutate_rows"](sym, rows)
            blob = render(rows, header=o.get("header", "timestamp,open,high,low,close,volume"),
                          newline=o.get("newline", "\n"), bom=o.get("bom", False))
            if "mutate_blob" in o:
                blob = o["mutate_blob"](sym, blob)
            self.csv_path(sym).write_bytes(blob)
            first = true_extent[0] if "first_ts" not in o else o["first_ts"]
            records.append(dict(symbol=sym, filename=self.csv_path(sym).name, sha256=sha(blob), size_bytes=len(blob),
                                row_count=true_extent[2], first_timestamp=first, last_timestamp=true_extent[1]))
        records.sort(key=lambda r: r["symbol"])
        mhash = sha(json.dumps(records, sort_keys=True, default=str).encode())
        manifest = dict(built_at="2023-01-01T00:00:00+00:00", data_dir=str(o.get("data_dir", self.data)),
                        files=records, manifest_hash=o.get("stored_manifest_hash", mhash), symbol_count=len(records))
        (self.root / "revision2" / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
        self.manifest_hash = mhash
        grid_days = weekdays(date(2023, 11, 22), 20)
        feeds, entries = {}, []
        for name, col in GRID_NAMES.items():
            rows = grid_rows(grid_days)
            if "mutate_grid" in o:
                rows = o["mutate_grid"](name, rows)
            text = f"{col},close\n" + "\n".join(f"{t},{c}" for t, c in rows) + "\n"
            path = self.grid / f"{name}.csv"
            path.write_bytes(text.encode())
            feeds[name] = dict(sha256=sha(text.encode()), timestamp_column=col)
            entries.append(dict(name=name, path=str(o.get("grid_path_override", {}).get(name, path)), sha256=feeds[name]["sha256"]))
        (self.root / "local_workspace" / "records" / "grid.json").write_text(json.dumps(dict(files=entries)))
        self.protocol = dict(
            stock_dataset=dict(manifest="revision2/MANIFEST.json", manifest_hash=o.get("protocol_hash", mhash),
                               symbols=len(self.symbols)),
            grid_dataset=dict(availability_delay_minutes=15, feeds=feeds, local_manifest="local_workspace/records/grid.json"),
            block_execution_contract=dict(stock_warmup_bars_per_symbol=self.warmup, starting_equity_per_block=1000000.0),
            engine=dict(governor_authority="full", live_trading=o.get("live_trading", False), broker_network_access=False),
            periods=dict(train_start="2023-09-01", train_end_exclusive=self.train_end),
            sampling_plan=dict(stage_b=[dict(block=1, sessions=self.sessions)]))
        self.block = dict(block=1, sessions=list(self.sessions))

    def offsets(self, sym):
        """Independent byte offsets (from file text, not from the harness) of the first/last target row and sentinel."""
        data = self.csv_path(sym).read_bytes()
        lines = data.splitlines(keepends=True)
        pos, out = 0, {}
        first_day, last_day = self.sessions[0], self.sessions[-1]
        for i, line in enumerate(lines):
            ts = line.split(b",")[0].decode().lstrip("﻿")
            day = ts[:10]
            if not day[:4].isdigit():            # header line
                pos += len(line)
                continue
            if day == first_day and "first" not in out:
                out["first"] = pos
            if day > last_day and "sentinel" not in out:
                out["sentinel"] = pos
                out["sentinel_end"] = pos + len(line)
                out["after_sentinel"] = pos + len(line)
            pos += len(line)
        out["size"] = len(data)
        return out
