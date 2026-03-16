"""Azure template extension configuration.

Provides provider-specific extension fields that are merged into the core
``Template`` when the provider type is ``azure``.  These are *defaults* –
a template can override any of them.
"""

from typing import Any, Optional

from pydantic import BaseModel, Field

#TODO: Verify
# ??? https://learn.microsoft.com/en-us/azure/cyclecloud/cluster-references/cluster-template-reference?view=cyclecloud-8
# ??? https://learn.microsoft.com/en-us/azure/azure-resource-manager/templates/overview
# ??? https://learn.microsoft.com/en-us/azure/templates/
class AzureTemplateExtensionConfig(BaseModel):
    """Azure-specific template extension defaults.

    Registered with ``TemplateExtensionRegistry`` so the template factory
    can apply Azure defaults when ``provider_type == "azure"``.
    """

    # VM configuration
    vm_size: str = Field(
        "Standard_D4s_v5",
        description="Default Azure VM size",
    )
    vm_sizes: Optional[list[str]] = Field(
        default=None,
        description="Additional VM size candidates for Spot / flexible allocation",
    )

    # Image defaults (Ubuntu 22.04 LTS Gen2 as sensible default)
    image_publisher: str = Field("Canonical", description="Default image publisher")
    image_offer: str = Field(
        "0001-com-ubuntu-server-jammy", description="Default image offer"
    )
    image_sku: str = Field("22_04-lts-gen2", description="Default image SKU")
    image_version: str = Field("latest", description="Default image version")

    # Pricing
    priority: str = Field("Regular", description="Default VM priority")
    interruptible: bool = Field(False, description="Whether to use Spot VMs")

    # Networking
    accelerated_networking: bool = Field(
        True, description="Enable accelerated networking where supported"
    )

    # OS disk
    os_disk_type: str = Field("Premium_LRS", description="Default OS disk type")
    os_disk_size_gb: Optional[int] = Field(
        None, description="OS disk size in GiB (None = image default)"
    )

    # Identity
    admin_username: str = Field("azureuser", description="Default admin username")

    # Freeform attributes
    node_attributes: dict[str, Any] = Field(
        default_factory=dict,
        description="Freeform attributes merged into the template",
    )

    def to_template_defaults(self) -> dict[str, Any]:
        """Convert extension to a dict of default values for template creation."""
        defaults: dict[str, Any] = {
            "vm_size": self.vm_size,
            "priority": self.priority,
            "admin_username": self.admin_username,
            "node_attributes": self.node_attributes,
        }
        if self.vm_sizes:
            defaults["vm_sizes"] = self.vm_sizes
        if self.os_disk_size_gb is not None:
            defaults["os_disk"] = {
                "storage_account_type": self.os_disk_type,
                "disk_size_gb": self.os_disk_size_gb,
            }
        return defaults
