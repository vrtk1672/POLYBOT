from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from app.ai_brain.contracts import AITaskType, normalize_task_type
from app.db.connection import DatabaseConnectionFactory
from app.repositories.ai_prompt_repository import AIPromptRepository


BASE_PROMPT_RULES = """Return strict JSON only. You are POLYBOT's semantic reasoning layer, not a trader.
Do not create orders, order intents, positions, risk approvals, or live execution recommendations.
Do not invent missing market data. If data is incomplete, return uncertainty and risk flags.
Always include confidence, risk_flags, summary, and cannot_trade_reason when relevant."""


DEFAULT_PROMPTS: dict[AITaskType, str] = {
    task: f"{BASE_PROMPT_RULES}\nTask: {task.value}. Interpret the supplied compact case file for this task."
    for task in AITaskType
}


@dataclass(slots=True)
class PromptVersion:
    prompt_version_id: str
    prompt_name: str
    prompt_type: str
    version: str
    template_text: str


class PromptVersionRegistry:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: AIPromptRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or AIPromptRepository()

    def get_active_prompt(self, task_type: AITaskType | str) -> PromptVersion:
        task = normalize_task_type(task_type)
        if self._factory.enabled:
            try:
                with self._factory.connect() as conn:
                    row = self._repository.get_active_prompt(conn, task.value)
                if row:
                    return PromptVersion(
                        prompt_version_id=row["prompt_version_id"],
                        prompt_name=row["prompt_name"],
                        prompt_type=row["prompt_type"],
                        version=row["version"],
                        template_text=row["template_text"],
                    )
            except Exception:
                pass
        return PromptVersion(
            prompt_version_id=f"default_{task.value.lower()}_v1",
            prompt_name=task.value.lower(),
            prompt_type=task.value,
            version="v1",
            template_text=DEFAULT_PROMPTS[task],
        )

    def register_prompt_version(
        self,
        *,
        task_type: AITaskType | str,
        template_text: str,
        version: str = "v1",
        prompt_name: str | None = None,
    ) -> PromptVersion:
        task = normalize_task_type(task_type)
        prompt = PromptVersion(
            prompt_version_id=f"prompt_{uuid4().hex}",
            prompt_name=prompt_name or task.value.lower(),
            prompt_type=task.value,
            version=version,
            template_text=template_text,
        )
        if self._factory.enabled:
            with self._factory.connect() as conn:
                self._repository.register_prompt_version(
                    conn,
                    prompt_version_id=prompt.prompt_version_id,
                    prompt_name=prompt.prompt_name,
                    prompt_type=prompt.prompt_type,
                    version=prompt.version,
                    template_text=prompt.template_text,
                )
                conn.commit()
        return prompt

    def deactivate_prompt_version(self, prompt_version_id: str) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn:
            self._repository.deactivate_prompt_version(conn, prompt_version_id)
            conn.commit()
