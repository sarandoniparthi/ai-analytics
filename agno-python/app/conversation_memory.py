from collections import defaultdict
from threading import Lock
from typing import Any


class ConversationMemory:
    def __init__(self, max_messages: int = 8) -> None:
        self.max_messages = max_messages
        self._store: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._lock = Lock()

    def get_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._store.get(conversation_id, []))

    def append_exchange(
        self,
        conversation_id: str,
        user_content: str,
        assistant_content: str,
        reasoning_details: Any,
    ) -> None:
        with self._lock:
            history = self._store.get(conversation_id, [])
            history.append({"role": "user", "content": user_content})
            assistant: dict[str, Any] = {"role": "assistant", "content": assistant_content}
            if reasoning_details is not None:
                assistant["reasoning_details"] = reasoning_details
            history.append(assistant)
            self._store[conversation_id] = history[-self.max_messages :]
