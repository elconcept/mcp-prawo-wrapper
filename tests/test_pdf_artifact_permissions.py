"""Worker root and resolver unprivileged UID share immutable PDF artifacts."""
from __future__ import annotations

import hashlib
import stat

from prawo_pl_mcp.legal_cite_pdf_adapter import _zapisz_niezmienny
from prawo_pl_mcp.local_corpus import (
    load_verified_artifact,
    verify_pdf_artifact,
    verify_report_artifact,
)
import json


def test_atomic_artifacts_readable_by_unprivileged_resolver(tmp_path, monkeypatch):
    """NamedTemporaryFile defaults to 0600; the resolver has a different UID."""
    monkeypatch.setenv("PRAWO_WEBWRIGHT_ARTIFACTS", str(tmp_path))
    pdf = b"%PDF-1.7\n" + b"PUBLIC ELl ORIGINAL" * 50
    text = "Art. 23. Odczyt testowy. " * 20
    report = {"silnik": "test", "wierny_odczyt": True}
    payloads = [
        (pdf, ".pdf"),
        (text.encode("utf-8"), ".txt"),
        (json.dumps(report, ensure_ascii=False, sort_keys=True).encode("utf-8"), ".json"),
    ]
    for payload, extension in payloads:
        digest, file = _zapisz_niezmienny(tmp_path, payload, extension)
        assert digest == hashlib.sha256(payload).hexdigest()
        mode = stat.S_IMODE(file.stat().st_mode)
        assert mode & stat.S_IRGRP
        assert mode & stat.S_IROTH  # resolver UID/GID may differ from worker
        assert not mode & stat.S_IWGRP
        assert not mode & stat.S_IWOTH
        assert file.read_bytes() == payload
    assert verify_pdf_artifact(hashlib.sha256(pdf).hexdigest() + ".pdf", hashlib.sha256(pdf).hexdigest())
    assert load_verified_artifact(hashlib.sha256(text.encode()).hexdigest() + ".txt", hashlib.sha256(text.encode()).hexdigest()) == text
    raw_report = payloads[2][0]
    assert verify_report_artifact(hashlib.sha256(raw_report).hexdigest(), report)
