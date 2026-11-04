"""The protocol file must ship inside the package so pip installs can find it."""

from pathlib import Path

import copilot
from copilot.rules import DEFAULT_PROTOCOL, load_protocol


def test_default_protocol_lives_inside_the_package():
    assert DEFAULT_PROTOCOL.is_file()
    assert Path(copilot.__file__).resolve().parent in DEFAULT_PROTOCOL.resolve().parents


def test_default_protocol_loads():
    assert load_protocol().rules
