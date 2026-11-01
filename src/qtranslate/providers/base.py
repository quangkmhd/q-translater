from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderChunk:
    delta: str


@dataclass(frozen=True)
class ProviderResponse:
    text: str = ""
    complete: bool = False
    finish_reason: str | None = None
    error_code: str | None = None
    status: int = 0
    retry_after: float = 60.0
