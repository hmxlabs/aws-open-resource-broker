"""Infrastructure adapter that satisfies SystemInfoPort using psutil/os."""

import importlib.metadata
import os
import time

import psutil

from orb.application.ports.system_info_port import SystemInfoPort


class PsutilSystemInfoAdapter(SystemInfoPort):
    """Concrete SystemInfoPort backed by psutil, os, and importlib.metadata."""

    def get_uptime_seconds(self) -> float:
        """Return seconds elapsed since system boot."""
        return time.time() - psutil.boot_time()

    def get_memory_usage_mb(self) -> float:
        """Return RSS memory of the current process in megabytes."""
        return psutil.Process().memory_info().rss / 1024 / 1024

    def get_cpu_usage_percent(self) -> float:
        """Return CPU usage percent with no blocking interval."""
        return psutil.cpu_percent(interval=None)

    def get_disk_usage_percent(self, path: str = "/") -> float:
        """Return disk usage percent for *path*."""
        return psutil.disk_usage(path).percent

    def get_file_mtime(self, path: str) -> float:
        """Return file modification time as a Unix timestamp."""
        return os.path.getmtime(path)

    def path_exists(self, path: str) -> bool:
        """Return True if *path* exists."""
        return os.path.exists(path)

    def get_env(self, key: str, default: str | None = None) -> str | None:
        """Return environment variable value or *default*."""
        return os.environ.get(key, default)

    def get_package_version(self, package: str) -> str:
        """Return installed package version or ``"unknown"``."""
        try:
            return importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            return "unknown"
