import io
import sys

from loguru import logger


def test_setup_logger_writes_unicode_messages_when_stdout_starts_as_gbk(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEBUG", "false")
    raw_stdout = io.BytesIO()
    gbk_stdout = io.TextIOWrapper(raw_stdout, encoding="gbk", errors="strict", write_through=True)
    monkeypatch.setattr(sys, "stdout", gbk_stdout)

    from app.utils import logger as logger_module

    logger_module.setup_logger()
    logger.info("✅ 中文日志内容")
    logger.complete()
    gbk_stdout.flush()

    output = raw_stdout.getvalue().decode("utf-8")
    assert "中文日志内容" in output
