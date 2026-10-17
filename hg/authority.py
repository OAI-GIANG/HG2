from dataclasses import dataclass

ALLOWED = frozenset({"health.read", "session.create", "edge.register", "edge.heartbeat", "edge.status", "provider.invoke"})
NEEDS_AUTH = frozenset({"session.create", "edge.register", "edge.heartbeat", "edge.status", "provider.invoke"})
FORBIDDEN = frozenset({"file.read", "file.write", "shell.exec", "network.fetch", "deploy", "identity.change", "state.import"})


@dataclass(frozen=True)
class Decision:
    allowed: bool
    action: str
    reason: str


def authorize(action, *, authenticated=False):
    if not isinstance(action, str) or not action:
        return Decision(False, "", "INVALID_ACTION")
    if action in FORBIDDEN:
        return Decision(False, action, "EXPLICITLY_FORBIDDEN")
    if action not in ALLOWED:
        return Decision(False, action, "NOT_ALLOWLISTED")
    if action in NEEDS_AUTH and not authenticated:
        return Decision(False, action, "AUTHENTICATION_REQUIRED")
    return Decision(True, action, "ALLOWLISTED")
