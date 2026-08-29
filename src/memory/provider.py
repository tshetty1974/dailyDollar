"""
The bridge between the memory file on disk and the model's prompt.

`store.py` decides where memory lives. This decides how it reaches the
model. Implementing the framework's ContextProvider interface means the
memory is injected automatically before every run of the agent it is
attached to, rather than each call site having to remember to paste it
in -- which is the failure mode that makes memory quietly stop working.
"""

from typing import Any

from agent_framework import ContextProvider

from memory.store import load_memory


class UserMemoryProvider(ContextProvider):
    """
    Injects what we know about the user ahead of every agent run.

    Deliberately read-only. Writes go through `store.save_memory`, so
    there is one path that changes memory and this class cannot drift
    out of step with the file.

    Attached only to the conversational agent. The specialist analysts
    study companies, not users, so giving them the user's history would
    be wasted tokens and prompt noise.
    """

    def __init__(
        self,
        user_id: str = "default",
        source_id: str = "user_memory",
    ):
        super().__init__(source_id=source_id)

        self.user_id = user_id

    async def before_run(
        self,
        *,
        agent: Any,
        session: Any,
        context: Any,
        state: dict[str, Any],
    ) -> None:
        """
        Read memory from disk and add it to the agent's instructions.

        Re-read on every run rather than cached at construction: an
        analysis finishing mid-conversation writes a new recommendation
        to disk, and the very next question is usually about it. The
        file is small, so this costs nothing next to a model call.
        """

        memory = load_memory(self.user_id)

        brief = memory.recall_brief()

        if not brief:
            return

        context.instructions.append(
            f"""
The following is what you remember about this user from previous
sessions. Treat it as established fact you already know. Do not ask the
user to repeat any of it, and refer to it naturally when answering
questions about past recommendations.

{brief}
""".strip()
        )
