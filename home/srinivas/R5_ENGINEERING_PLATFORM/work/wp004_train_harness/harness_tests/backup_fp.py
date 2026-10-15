"""Metadata-only tree fingerprint (path|size|mtime_ns|mode); opens no file."""
import hashlib
import os


def meta_fingerprint(root):
    h, n = hashlib.sha256(), 0
    for dp, dn, fn in os.walk(root):
        dn.sort()
        for f in sorted(fn):
            p = os.path.join(dp, f)
            st = os.lstat(p)
            h.update(f"{os.path.relpath(p, root)}|{st.st_size}|{st.st_mtime_ns}|{st.st_mode}\n".encode())
            n += 1
    return dict(files=n, metadata_sha256=h.hexdigest())
