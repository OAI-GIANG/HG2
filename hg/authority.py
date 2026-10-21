from dataclasses import dataclass

PRIVILEGED_ACTIONS = frozenset({"file.read", "file.write", "shell.exec", "network.fetch", "deploy", "identity.change", "state.import", "provider.invoke"})
ALLOWED = frozenset({"health.read", "session.create", "edge.register", "edge.heartbeat", "edge.status"}) | PRIVILEGED_ACTIONS
NEEDS_AUTH = frozenset({"session.create", "edge.register", "edge.heartbeat", "edge.status"}) | PRIVILEGED_ACTIONS
FORBIDDEN = frozenset()  # Blanket denies removed; elevated actions still require a sealed-principal path.


@dataclass(frozen=True)
class Decision:
    allowed: bool
    action: str
    reason: str


def authorize(action, *, authenticated=False):
    if not isinstance(action, str) or not action:
        return Decision(False, "", "INVALID_ACTION")
    if action in PRIVILEGED_ACTIONS:
        return Decision(False, action, "SEALED_PRINCIPAL_REQUIRED")
    if action not in ALLOWED:
        return Decision(False, action, "NOT_ALLOWLISTED")
    if action in NEEDS_AUTH and not authenticated:
        return Decision(False, action, "AUTHENTICATION_REQUIRED")
    return Decision(True, action, "ALLOWLISTED")
