"""Compatibility exports for the single fail-closed policy decision point."""
from .policy import (ALLOWED, FORBIDDEN, NEEDS_AUTH, Decision, authorize, authorize_principal)

__all__ = ["ALLOWED", "FORBIDDEN", "NEEDS_AUTH", "Decision", "authorize", "authorize_principal"]
