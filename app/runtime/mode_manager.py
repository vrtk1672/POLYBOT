from __future__ import annotations

from app.runtime.contracts import ModeTransitionResult
from app.runtime.modes import RuntimeMode, parse_runtime_mode


class ModeManager:
    def evaluate_transition(
        self,
        *,
        from_mode: RuntimeMode | str | None,
        to_mode: RuntimeMode | str | None,
        actor: str | None,
        reason: str | None,
        metadata: dict[str, object] | None = None,
    ) -> ModeTransitionResult:
        metadata = metadata or {}
        try:
            parsed_to = parse_runtime_mode(to_mode) if to_mode is not None else None
            parsed_from = parse_runtime_mode(from_mode) if from_mode is not None else None
        except ValueError as exc:
            return ModeTransitionResult(False, None, None, f"invalid runtime mode: {exc}")

        if parsed_to is None:
            return ModeTransitionResult(False, parsed_from, None, "to_mode is required")
        if not actor or not actor.strip():
            return ModeTransitionResult(False, parsed_from, parsed_to, "actor is required")
        if not reason or not reason.strip():
            return ModeTransitionResult(False, parsed_from, parsed_to, "reason is required")

        if parsed_to == RuntimeMode.KILL:
            return ModeTransitionResult(True, parsed_from, parsed_to)
        if parsed_to == RuntimeMode.COOLDOWN:
            return ModeTransitionResult(True, parsed_from, parsed_to)
        if parsed_to == RuntimeMode.ATTACK_MODE:
            if metadata.get("governor_approved") is True:
                return ModeTransitionResult(
                    True,
                    parsed_from,
                    parsed_to,
                    warnings=["ATTACK_MODE remains zero-risk in V2.0 foundation."],
                )
            return ModeTransitionResult(
                False,
                parsed_from,
                parsed_to,
                "ATTACK_MODE requires governor_approved=true",
                ["governor_approved"],
            )

        if parsed_from is None:
            return ModeTransitionResult(parsed_to == RuntimeMode.DATA_ONLY, parsed_from, parsed_to, None if parsed_to == RuntimeMode.DATA_ONLY else "initial state must be DATA_ONLY")
        if parsed_from == parsed_to:
            return ModeTransitionResult(True, parsed_from, parsed_to, warnings=["mode is unchanged"])

        if parsed_from == RuntimeMode.DATA_ONLY:
            if parsed_to == RuntimeMode.PAPER:
                return ModeTransitionResult(True, parsed_from, parsed_to)
            return ModeTransitionResult(False, parsed_from, parsed_to, f"{parsed_from.value} -> {parsed_to.value} is blocked")
        if parsed_from == RuntimeMode.PAPER:
            if parsed_to in {RuntimeMode.DATA_ONLY, RuntimeMode.SHADOW_LIVE}:
                return ModeTransitionResult(True, parsed_from, parsed_to)
            return ModeTransitionResult(False, parsed_from, parsed_to, f"{parsed_from.value} -> {parsed_to.value} is blocked")
        if parsed_from == RuntimeMode.SHADOW_LIVE:
            if parsed_to == RuntimeMode.PAPER:
                return ModeTransitionResult(True, parsed_from, parsed_to)
            if parsed_to == RuntimeMode.SMALL_LIVE:
                if metadata.get("certification") is True or metadata.get("small_live_certified") is True:
                    return ModeTransitionResult(True, parsed_from, parsed_to, warnings=["SMALL_LIVE requires existing live guards; V2.0 does not enable live automatically."])
                return ModeTransitionResult(False, parsed_from, parsed_to, "SMALL_LIVE requires certification=true", ["certification"])
            return ModeTransitionResult(False, parsed_from, parsed_to, f"{parsed_from.value} -> {parsed_to.value} is blocked")
        if parsed_from == RuntimeMode.SMALL_LIVE:
            if parsed_to in {RuntimeMode.SHADOW_LIVE, RuntimeMode.COOLDOWN, RuntimeMode.KILL}:
                return ModeTransitionResult(True, parsed_from, parsed_to)
            return ModeTransitionResult(False, parsed_from, parsed_to, f"{parsed_from.value} -> {parsed_to.value} is blocked")
        if parsed_from == RuntimeMode.KILL:
            if parsed_to == RuntimeMode.DATA_ONLY:
                return ModeTransitionResult(True, parsed_from, parsed_to)
            if parsed_to == RuntimeMode.PAPER and metadata.get("post_kill_resume_verified") is True:
                return ModeTransitionResult(True, parsed_from, parsed_to)
            return ModeTransitionResult(False, parsed_from, parsed_to, f"KILL -> {parsed_to.value} is blocked")
        if parsed_from == RuntimeMode.COOLDOWN:
            if parsed_to in {RuntimeMode.DATA_ONLY, RuntimeMode.PAPER}:
                return ModeTransitionResult(True, parsed_from, parsed_to)
            return ModeTransitionResult(False, parsed_from, parsed_to, f"COOLDOWN -> {parsed_to.value} is blocked")

        return ModeTransitionResult(False, parsed_from, parsed_to, f"{parsed_from.value} -> {parsed_to.value} is blocked")
