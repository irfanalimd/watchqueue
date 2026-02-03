"""Helper utilities for WatchQueue."""

from typing import TypeVar, Type
from bson import ObjectId
from fastapi import HTTPException, status

T = TypeVar("T")


def validate_object_id(id_str: str, field_name: str = "id") -> ObjectId:
    """Validate and convert string to ObjectId.

    Raises HTTPException 400 if invalid.
    """
    if not ObjectId.is_valid(id_str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name} format",
        )
    return ObjectId(id_str)


def get_service(service_class: Type[T], db) -> T:
    """Create a service instance with database dependency."""
    return service_class(db)
