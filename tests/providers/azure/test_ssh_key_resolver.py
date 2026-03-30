"""Focused tests for Azure SSH key resolution."""

from unittest.mock import MagicMock

import pytest
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

from orb.providers.azure.infrastructure.services.ssh_key_resolver import resolve_ssh_keys


def test_resolve_ssh_keys_returns_inline_keys_without_sdk_lookup():
    compute_client = MagicMock()

    result = resolve_ssh_keys(
        ssh_key_name="orb-key",
        ssh_public_keys=["ssh-rsa inline test@host"],
        resource_group="test-rg",
        compute_client=compute_client,
    )

    assert result == ["ssh-rsa inline test@host"]
    compute_client.ssh_public_keys.get.assert_not_called()


def test_resolve_ssh_keys_fetches_named_azure_ssh_key():
    compute_client = MagicMock()
    ssh_resource = MagicMock()
    ssh_resource.public_key = "ssh-rsa resolved test@host"
    compute_client.ssh_public_keys.get.return_value = ssh_resource

    result = resolve_ssh_keys(
        ssh_key_name="orb-key",
        ssh_public_keys=[],
        resource_group="test-rg",
        compute_client=compute_client,
    )

    assert result == ["ssh-rsa resolved test@host"]


def test_resolve_ssh_keys_requires_name_or_inline_key_data():
    with pytest.raises(ValueError, match="neither 'ssh_key_name' nor 'ssh_public_keys'"):
        resolve_ssh_keys(
            ssh_key_name=None,
            ssh_public_keys=[],
            resource_group="test-rg",
            compute_client=MagicMock(),
        )


def test_resolve_ssh_keys_rejects_missing_ssh_key_resource():
    compute_client = MagicMock()
    compute_client.ssh_public_keys.get.side_effect = ResourceNotFoundError("missing")

    with pytest.raises(ValueError, match="was not found"):
        resolve_ssh_keys(
            ssh_key_name="orb-key",
            ssh_public_keys=[],
            resource_group="test-rg",
            compute_client=compute_client,
        )


def test_resolve_ssh_keys_rejects_transport_error():
    compute_client = MagicMock()
    compute_client.ssh_public_keys.get.side_effect = HttpResponseError("boom")

    with pytest.raises(ValueError, match="Failed to resolve Azure SSH Public Key"):
        resolve_ssh_keys(
            ssh_key_name="orb-key",
            ssh_public_keys=[],
            resource_group="test-rg",
            compute_client=compute_client,
        )

