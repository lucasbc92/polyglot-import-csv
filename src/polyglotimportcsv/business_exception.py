"""User-facing error taxonomy (shallow hierarchy, one class per failure category)."""


class BusinessException(Exception):
    """Base class for every error reported to the user by the CLI."""


class ConfigError(BusinessException):
    """Invalid JSON, JSON Schema violation, or backend without declared connection."""


class SourceError(BusinessException):
    """Unknown source, missing CSV file, or origin/source name collision."""


class MappingError(BusinessException):
    """Unknown column/index/range, or entity without a resolvable source."""


class ImportExecutionError(BusinessException):
    """Failure while connecting to or writing into a target SGBD."""
