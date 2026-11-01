"""One in-memory conversation. Only completed exchanges become model context."""

import copy
import uuid
from dataclasses import dataclass
from qtranslate.tasks.types import TaskRequest, TaskResult


@dataclass
class ChatTurn:
    id: str
    user: str
    text: str = ""
    state: str = "waiting"
    error: str | None = None


class ChatSession:
    def __init__(self):
        self.session_id = str(uuid.uuid4())
        self.history = []
        self.turns = []
        self.active_id = None
        self.draft = ""
        self.visible = True

    def begin(self, text):
        if self.active_id:
            raise ValueError("CHAT_BUSY")
        if not text.strip():
            raise ValueError("EMPTY_MESSAGE")
        id = str(uuid.uuid4())
        messages = copy.deepcopy(self.history) + [{"role": "user", "content": text}]
        self.turns.append(ChatTurn(id, text))
        self.active_id = id
        self.draft = ""
        return TaskRequest(id, "chat", text=text, messages=tuple(messages))

    def apply(self, result):
        if result.id != self.active_id or result.action != "chat":
            return False
        turn = self.turns[-1]
        turn.state, turn.error = result.state, result.error_code
        if result.state in ("streaming", "success"):
            turn.text = result.text
        if result.state == "success":
            self.history.extend(
                [
                    {"role": "user", "content": turn.user},
                    {"role": "assistant", "content": turn.text},
                ]
            )
        if result.state in ("success", "error", "cancelled"):
            self.active_id = None
        return True

    def stop(self):
        id = self.active_id
        if id:
            self.apply(TaskResult(id, "chat", "cancelled"))
        return id

    def clear(self):
        id = self.stop()
        self.history.clear()
        self.turns.clear()
        self.draft = ""
        self.session_id = str(uuid.uuid4())
        return id

    def hide(self):
        self.visible = False

    def show(self):
        self.visible = True

    def close(self):
        id = self.clear()
        self.hide()
        return id
