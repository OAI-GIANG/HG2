"""Compatibility exports for the centralized fail-closed policy module."""
from .policy import ALLOWED, FORBIDDEN, NEEDS_AUTH, Decision, authorize

__all__ = ["ALLOWED", "FORBIDDEN", "NEEDS_AUTH", "Decision", "authorize"]
