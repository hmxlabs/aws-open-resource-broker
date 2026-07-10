"""Serialization components for storage operations."""

import json
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Optional, TypeVar

from orb.infrastructure.logging.logger import get_logger
from orb.infrastructure.utilities.common.serialization import (
    deserialize_enum as _deserialize_enum,
    serialize_enum as _serialize_enum,
)

E = TypeVar("E", bound=Enum)


class SerializationManager(ABC):
    """Base interface for serialization managers."""

    @abstractmethod
    def serialize(self, data: dict[str, Any]) -> Any:
        """Serialize data for storage."""

    @abstractmethod
    def deserialize(self, data: Any) -> dict[str, Any]:
        """Deserialize data from storage."""


class JSONSerializer(SerializationManager):
    """JSON serialization manager with enum support."""

    def __init__(self) -> None:
        """Initialize the instance."""
        self.logger = get_logger(__name__)

    def serialize(self, data: dict[str, Any]) -> str:
        """
        Serialize data to JSON string.

        Args:
            data: Dictionary to serialize

        Returns:
            JSON string representation
        """
        try:
            # Handle enum serialization
            serializable_data = self._prepare_for_serialization(data)
            return json.dumps(serializable_data, indent=2, default=str, ensure_ascii=False)
        except Exception as e:
            self.logger.error("JSON serialization failed: %s", e)
            raise

    def deserialize(self, data: str) -> dict[str, Any]:
        """
        Deserialize JSON string to dictionary.

        Args:
            data: JSON string to deserialize

        Returns:
            Dictionary representation
        """
        try:
            if not data or not data.strip():
                return {}
            return json.loads(data)
        except json.JSONDecodeError as e:
            self.logger.error("JSON deserialization failed: %s", e)
            raise
        except Exception as e:
            self.logger.error("Unexpected deserialization error: %s", e)
            raise

    def _prepare_for_serialization(self, data: dict[str, Any]) -> dict[str, Any]:
        """Prepare data for JSON serialization by handling special types."""
        if not isinstance(data, dict):
            return data

        result = {}
        for key, value in data.items():
            if isinstance(value, Enum):
                result[key] = self.serialize_enum(value)
            elif isinstance(value, dict):
                result[key] = self._prepare_for_serialization(value)
            elif isinstance(value, list):
                result[key] = [
                    (
                        self._prepare_for_serialization(item)
                        if isinstance(item, dict)
                        else (self.serialize_enum(item) if isinstance(item, Enum) else item)
                    )
                    for item in value
                ]
            else:
                result[key] = value

        return result

    @staticmethod
    def serialize_enum(enum_value: Optional[Enum]) -> Optional[str]:
        """Serialize enum to string value. Delegates to the shared utility."""
        return _serialize_enum(enum_value)

    @staticmethod
    def deserialize_enum(
        enum_class: type[E], value: Any, default: Optional[E] = None
    ) -> Optional[E]:
        """Deserialize string to enum value. Delegates to the shared utility."""
        return _deserialize_enum(enum_class, value, default)
