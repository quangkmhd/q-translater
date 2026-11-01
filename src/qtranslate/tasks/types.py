from dataclasses import dataclass, field, asdict
from qtranslate.desktop.context import SourceContext


@dataclass(frozen=True)
class TaskRequest:
    id: str
    action: str
    text: str | None = None
    image_path: str | None = None
    context: SourceContext = field(default_factory=SourceContext)
    target: str | None = None
    started_at: float | None = None
    messages: tuple[dict, ...] = ()


@dataclass(frozen=True)
class TaskResult:
    id: str
    action: str
    state: str
    text: str = ""
    provider: str | None = None
    model: str | None = None
    error_code: str | None = None

    def to_dict(self):
        return asdict(self)
