"""Launch-template cleanup concern extracted from AWSHandler.

The three methods here were previously inlined in ``AWSHandler``.  They form a
coherent *cleanup concern*: given a request ID, determine from config whether
cleanup is needed, then find and delete the matching ORB-managed launch
template.

``LaunchTemplateCleanupService`` owns this concern and is constructed by
``AWSHandler`` from its own injected dependencies.  ``AWSHandler`` retains
thin delegation wrappers (``_get_cleanup_config``, ``_cleanup_on_zero_capacity``,
``_delete_orb_launch_template``) so that existing call sites and test patches
are unaffected.
"""

from typing import Optional

from botocore.exceptions import ClientError

from orb.domain.base.ports import LoggingPort
from orb.domain.base.ports.configuration_port import ConfigurationPort
from orb.providers.aws.configuration.cleanup_config import CleanupConfig
from orb.providers.aws.infrastructure.aws_client import AWSClient


class LaunchTemplateCleanupService:
    """Handles ORB launch-template cleanup after a resource reaches zero capacity.

    All public methods are warning-only: they never propagate exceptions to
    callers so that cleanup logic cannot block the main return/cancel flow.

    Args:
        aws_client: AWS client used to describe and delete EC2 launch templates.
        config_port: Configuration port for reading cleanup settings.  When
            ``None`` the service behaves as if cleanup is disabled.
        logger: Logging port used to emit debug / info / warning messages.
    """

    def __init__(
        self,
        aws_client: AWSClient,
        config_port: Optional[ConfigurationPort],
        logger: LoggingPort,
    ) -> None:
        self._aws_client = aws_client
        self._config_port = config_port
        self._logger = logger

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_cleanup_config(self) -> CleanupConfig:
        """Read cleanup config from AWS provider defaults.

        Returns a default ``CleanupConfig`` (all-enabled) when the config port
        is absent, when the provider has no ``aws`` defaults block, or when
        reading raises.
        """
        try:
            if self._config_port is None:
                return CleanupConfig()
            provider_config = self._config_port.get_provider_config()
            if provider_config and provider_config.provider_defaults:
                defaults = provider_config.provider_defaults.get("aws")
                if defaults and defaults.cleanup is not None:
                    return CleanupConfig.model_validate(defaults.cleanup)
        except Exception as e:
            self._logger.warning("Failed to read cleanup config, using defaults: %s", e)
        return CleanupConfig()

    def cleanup_on_zero_capacity(self, resource_type: str, request_id: str) -> None:
        """Delete the ORB-managed launch template when a resource reaches zero capacity.

        Reads the cleanup config, checks that cleanup is enabled and that the
        resource type is included in the ``resources`` allow-list, then delegates
        to ``delete_orb_launch_template``.  All failures are warning-only so
        that cleanup never blocks the main return flow.

        Args:
            resource_type: Cleanup config resource key, e.g. ``"asg"``,
                ``"ec2_fleet"``, or ``"spot_fleet"``.
            request_id: The ORB request ID used to locate the launch template.
        """
        if self._config_port is None:
            return

        try:
            cleanup = self.get_cleanup_config()
        except Exception as e:
            self._logger.warning("Failed to read cleanup config, skipping cleanup: %s", e)
            return

        if not cleanup.enabled:
            return

        if not getattr(cleanup.resources, resource_type, True):
            return

        self.delete_orb_launch_template(request_id)

    def delete_orb_launch_template(self, request_id: str) -> None:
        """Delete the ORB-managed launch template for a request, if one exists.

        Reconstructs the launch template name from the request ID, verifies the
        ``orb:managed-by`` tag to confirm ORB ownership, then deletes it.
        Respects the cleanup config dry_run flag.  All failures are warning-only
        so that LT cleanup never blocks the main return flow.
        """
        if self._config_port is None:
            self._logger.warning(
                "config_port not injected; skipping launch template cleanup for %s", request_id
            )
            return

        try:
            cleanup = self.get_cleanup_config()
        except Exception as e:
            self._logger.warning("Could not read cleanup config, skipping LT cleanup: %s", e)
            return

        if not cleanup.enabled or not cleanup.delete_launch_template:
            return

        dry_run = cleanup.dry_run

        try:
            response = self._aws_client.ec2_client.describe_launch_templates(
                Filters=[{"Name": "tag:orb:request-id", "Values": [request_id]}]
            )
            templates = response.get("LaunchTemplates", [])
            if not templates:
                self._logger.debug(
                    "No launch templates found for request %s; nothing to clean up", request_id
                )
                return

            self._logger.info(
                "Found %d launch template(s) to clean up for request %s",
                len(templates),
                request_id,
            )

            for lt in templates:
                tags = {t["Key"]: t["Value"] for t in lt.get("Tags", [])}
                lt_id = lt["LaunchTemplateId"]
                lt_name = lt.get("LaunchTemplateName", lt_id)

                if tags.get("orb:managed-by") != "open-resource-broker":
                    self._logger.warning(
                        "Launch template %s (%s) is not ORB-managed (orb:managed-by tag absent"
                        " or wrong); skipping deletion",
                        lt_name,
                        lt_id,
                    )
                    continue

                if dry_run:
                    self._logger.info(
                        "[dry-run] Would delete launch template %s (%s) for request %s",
                        lt_name,
                        lt_id,
                        request_id,
                    )
                    continue

                try:
                    self._aws_client.ec2_client.delete_launch_template(LaunchTemplateId=lt_id)
                    self._logger.info(
                        "Deleted launch template %s (%s) for request %s",
                        lt_name,
                        lt_id,
                        request_id,
                    )
                except ClientError as e:
                    self._logger.warning(
                        "Failed to delete launch template %s (%s) for request %s: %s",
                        lt_name,
                        lt_id,
                        request_id,
                        e,
                    )

        except ClientError as e:
            self._logger.warning(
                "Failed to describe launch templates for request %s: %s",
                request_id,
                e,
            )
        except Exception as e:
            self._logger.warning(
                "Unexpected error cleaning up launch templates for request %s: %s",
                request_id,
                e,
            )
