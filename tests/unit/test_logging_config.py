import logging

import pytest

from config.logging_config import setup_logging


class TestSetupLogging:
    def test_json_format(self):
        root = setup_logging(log_level="DEBUG", log_format="json")
        assert root.level == logging.DEBUG
        assert len(root.handlers) == 1
        assert "Json" in root.handlers[0].formatter.__class__.__name__

    def test_text_format(self):
        root = setup_logging(log_level="INFO", log_format="text")
        assert root.level == logging.INFO
        assert len(root.handlers) == 1
        assert "Formatter" in root.handlers[0].formatter.__class__.__name__

    def test_case_insensitive_level(self):
        root = setup_logging(log_level="debug", log_format="json")
        assert root.level == logging.DEBUG

    def test_warning_level(self):
        root = setup_logging(log_level="WARNING", log_format="json")
        assert root.level == logging.WARNING
