from __future__ import annotations

from Platform.api.app.services.log_rotation import open_rotating_append_log, rotate_log_file_if_needed


def test_open_rotating_append_log_rotates_when_file_exceeds_limit(tmp_path):
    log_path = tmp_path / "service.log"
    log_path.write_text("x" * 24, encoding="utf-8")
    (tmp_path / "service.log.1").write_text("previous", encoding="utf-8")

    with open_rotating_append_log(log_path, max_bytes=10, backups=2) as handle:
        handle.write("new\n")

    assert log_path.read_text(encoding="utf-8") == "new\n"
    assert (tmp_path / "service.log.1").read_text(encoding="utf-8") == "x" * 24
    assert (tmp_path / "service.log.2").read_text(encoding="utf-8") == "previous"


def test_rotate_log_file_deletes_current_when_backups_disabled(tmp_path):
    log_path = tmp_path / "service.log"
    log_path.write_text("x" * 24, encoding="utf-8")

    rotated = rotate_log_file_if_needed(log_path, max_bytes=10, backups=0)

    assert rotated is True
    assert not log_path.exists()
