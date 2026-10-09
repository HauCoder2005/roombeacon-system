"""Domain errors; the presentation layer maps each one to an HTTP status."""

from __future__ import annotations

from typing import Sequence


class DomainError(Exception):
    """Base class for errors the API reports to clients."""


class NotFoundError(DomainError):
    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(f"{resource} not found")
        self.resource = resource
        self.identifier = identifier


class AmbiguousLocationError(DomainError):
    def __init__(self, choices: Sequence[object]) -> None:
        super().__init__("location name matches several places")
        self.choices = list(choices)


class InvalidParameterError(DomainError):
    def __init__(self, field: str, code: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.code = code
        self.message = message


class DependencyUnavailableError(DomainError):
    def __init__(self, dependency: str) -> None:
        super().__init__(dependency)
        self.dependency = dependency
