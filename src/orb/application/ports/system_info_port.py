"""Application port for system-level I/O: filesystem, environment, process metrics."""

from abc import ABC, abstractmethod


class SystemInfoPort(ABC):
    """Port that abstracts all os/psutil/importlib.metadata calls from query handlers.

    The application layer depends only on this abstraction; the infrastructure
    layer provides a concrete adapter backed by psutil and os.
    """

    @abstractmethod
    def get_uptime_seconds(self) -> float:
        """Return system uptime in seconds since last boot."""

    @abstractmethod
    def get_memory_usage_mb(self) -> float:
        """Return current process RSS memory usage in megabytes."""

    @abstractmethod
    def get_cpu_usage_percent(self) -> float:
        """Return current process/system CPU usage as a percentage (0-100)."""

    @abstractmethod
    def get_disk_usage_percent(self, path: str = "/") -> float:
        """Return disk usage percentage for *path* (0-100)."""

    @abstractmethod
    def get_file_mtime(self, path: str) -> float:
        """Return the modification time of *path* as a Unix timestamp.

        Raises:
            OSError: if the path does not exist or is not accessible.
        """

    @abstractmethod
    def path_exists(self, path: str) -> bool:
        """Return True if *path* exists on the filesystem."""

    @abstractmethod
    def get_env(self, key: str, default: str | None = None) -> str | None:
        """Return the value of environment variable *key*, or *default*."""

    @abstractmethod
    def get_package_version(self, package: str) -> str:
        """Return the installed version string for *package*.

        Returns:
            Version string, or ``"unknown"`` if the package is not installed.
        """
