"""In-sandbox bootstrap (PID 2 inside the bwrap namespaces). Never run outside the launcher.

1. probe the live kernel state and announce READY on stderr (the launcher then observes the sandbox from the host);
2. read ONE handshake line from stdin (stdin is then pointed at /dev/null);
3. re-verify the live boundary against the host observation, the code-tree pins and the input sha256 pins;
4. only then run the target in-process. Any failure => exit 97 with a BOOTSTRAP_FAILED marker; the target never starts.
"""
import json
import os
import runpy
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
sys.path.insert(0, HERE)
import os_isolation as osi  # noqa: E402


def fail(reason, **extra):
    sys.stderr.write(f"{osi.MARK_FAIL} {json.dumps(dict(reason=reason, **extra))}@@\n")
    sys.stderr.flush()
    os._exit(osi.BOOTSTRAP_FAIL_RC)


def main():
    probe = osi.probe_self()
    sys.stderr.write(f"{osi.MARK_READY} {json.dumps(dict(ns=probe['ns']))}@@\n")
    sys.stderr.flush()
    raw = sys.stdin.buffer.readline(osi.MAX_HANDSHAKE + 1)
    if not raw.endswith(b"\n") or len(raw) > osi.MAX_HANDSHAKE:
        fail("handshake missing or oversize")
    try:
        hand = json.loads(raw)
        exp, witness = hand["expectation"], hand["witness"]
        nonce, target = hand["nonce"], hand["target"]
        if witness.get("nonce") != nonce or witness.get("schema") != osi.WITNESS_SCHEMA:
            fail("witness nonce/schema mismatch")
        pins, inputs, args = hand["code_pins"], hand["inputs"], hand["target_args"]
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        fail("malformed handshake", error=str(exc))
    null = os.open("/dev/null", os.O_RDONLY)
    os.dup2(null, 0)
    os.close(null)
    bad = osi.verify_probe(osi.probe_self(), exp)
    if bad:
        fail("live boundary differs from host observation (forged or wrong witness)", violations=bad)
    for name, pin in sorted(pins.items()):
        try:
            actual = osi.tree_sha256(f"{osi.CODE_MOUNT}/{name}")
        except (OSError, osi.OSIsolationError) as exc:
            fail("code root unreadable", root=name, error=str(exc))
        if actual != pin:
            fail("code tree sha256 differs from pin", root=name, expected=pin, actual=actual)
    for alias, pin in sorted(inputs.items()):
        try:
            actual = osi.sha256_file(f"{osi.IN_MOUNT}/{alias}")
        except OSError as exc:
            fail("input unreadable", alias=alias, error=str(exc))
        if actual != pin:
            fail("input sha256 differs from pin", alias=alias, expected=pin, actual=actual)
    if sorted(os.listdir(osi.IN_MOUNT) if os.path.isdir(osi.IN_MOUNT) else []) != sorted(inputs):
        fail("/in content differs from the pinned inputs")
    osi.activate(exp, dict(witness, bootstrap_verified_live=True, verified_code_pins=pins,
                           verified_input_sha256=inputs))
    sys.argv = [target, *args]
    sys.stderr.write(f"{osi.MARK_START}@@\n")
    sys.stderr.flush()
    rc = 0
    try:
        runpy.run_path(target, run_name="__main__")
    except SystemExit as exc:
        rc = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    except BaseException:
        traceback.print_exc()
        rc = 1
    sys.stdout.flush()
    sys.stderr.write(f"{osi.MARK_END} {json.dumps(dict(rc=rc))}@@\n")
    sys.stderr.flush()
    os._exit(rc & 0xFF)


if __name__ == "__main__":
    main()
