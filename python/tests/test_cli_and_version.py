import io
import logging
import re
from pathlib import Path

import pytest

import sanadamaru
from sanadamaru.__main__ import main


def test_demo_runs_and_leaves_logging_as_it_was():
    lib_logger = logging.getLogger("sanadamaru")
    before = lib_logger.level
    out = io.StringIO()
    assert main(["demo"], out=out) == 0
    text = out.getvalue()
    assert "A decoy door" in text and "A bait key" in text and "sources: 1" in text
    assert lib_logger.level == before


def test_demo_in_japanese():
    out = io.StringIO()
    assert main(["--lang", "ja", "demo"], out=out) == 0
    text = out.getvalue()
    assert "偽の扉です" in text and "偽の鍵です" in text and "送り元 1か所" in text


def test_doors_lists_default_doors():
    out = io.StringIO()
    assert main(["doors"], out=out) == 0
    assert "/.env" in out.getvalue() and "/.git/config" in out.getvalue()
    assert out.getvalue().startswith("Default decoy doors")


def test_doors_in_japanese():
    out = io.StringIO()
    assert main(["--lang", "ja", "doors"], out=out) == 0
    text = out.getvalue()
    assert text.startswith("既定の扉") and "/.env" in text and "/.git/config" in text


def test_version_option(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    assert sanadamaru.__version__ in capsys.readouterr().out


def test_version_matches_pyproject():
    text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'^version = "([^"]+)"', text, re.M).group(1) == sanadamaru.__version__
