"""Tests for the supported Python SDK boundary."""

from evidentia_sdk import ACCESS_OPERATION_IDS, sdk_version


def test_sdk_version_is_available() -> None:
    assert sdk_version() == "0.1.0"


def test_access_operations_are_generated_from_the_checked_contract() -> None:
    """Keep the SDK boundary synchronized with access operation identifiers.

    @skyhook-implements REQ-012
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    assert ACCESS_OPERATION_IDS == (
        "access_get_current_context",
        "access_login_local",
        "access_logout",
        "access_select_tenant",
    )
