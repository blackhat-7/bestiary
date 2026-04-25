class ToolError(Exception):
    """Base class for errors raised by bestiary tools."""


class ValidationError(ToolError):
    """Tool input failed validation."""


class ApiError(ToolError):
    """An external API call failed."""
