"""Errors shared by the agent's tools (kept apart so tools.py and actions.py can import each other's module)."""


class ToolError(Exception):
    """Bad arguments or a missing object: the message goes back to the model, never a crash."""
