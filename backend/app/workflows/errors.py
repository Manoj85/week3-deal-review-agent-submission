"""Structured incomplete-run errors preserve completed work without pretending success."""

from ..services.nebius import ProviderError


class WorkflowError(ProviderError):
    def __init__(self, stage: str, message: str, partial: dict):
        super().__init__(message)
        self.stage = stage
        self.partial = partial
