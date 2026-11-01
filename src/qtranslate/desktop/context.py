from dataclasses import dataclass


@dataclass(frozen=True)
class SourceContext:
    window_id: str = ""
    app_id: str = ""
    source_epoch: str = ""
    monitor: int = 0
