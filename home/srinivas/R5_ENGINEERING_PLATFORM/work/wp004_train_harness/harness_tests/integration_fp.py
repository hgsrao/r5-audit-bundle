"""Metadata-only fingerprint of the protected trees (no file content is opened). Prints JSON."""
import hashlib
import json
import os

P = "/home/srinivas/R5_ENGINEERING_PLATFORM/work/wp004_train_harness"


def meta(root):
    h, n = hashlib.sha256(), 0
    for dp, dn, fn in os.walk(root):
        dn.sort()
        for f in sorted(fn):
            p = os.path.join(dp, f)
            st = os.lstat(p)
            h.update(f"{os.path.relpath(p, root)}|{st.st_size}|{st.st_mtime_ns}|{st.st_mode}\n".encode())
            n += 1
    return dict(files=n, metadata_sha256=h.hexdigest())


if __name__ == "__main__":
    print(json.dumps(dict(
        snapshot=meta(P + "/snapshot"), original_repo=meta("/home/srinivas/projects/zerodha-r5-governor-refactor"),
        snapshot_manifest_sha256=hashlib.sha256(open(P + "/SNAPSHOT_MANIFEST.json", "rb").read()).hexdigest()),
        indent=2, sort_keys=True))
