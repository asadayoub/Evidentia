"""Tests for the supported Python SDK boundary."""

from evidentia_sdk import sdk_version


def test_sdk_version_is_available() -> None:
    assert sdk_version() == "0.1.0"
