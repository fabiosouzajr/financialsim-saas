import pytest
from pathlib import Path


def test_deliver_writes_eml_file(tmp_path):
    from finacialsim_saas.workers.maildir import MaildirChannel
    ch = MaildirChannel(str(tmp_path))
    ch.deliver(to="user@test.com", subject="Test", body="Hello")
    files = list(tmp_path.iterdir())
    assert len(files) == 1
    content = files[0].read_text()
    assert "To: user@test.com" in content
    assert "Hello" in content
