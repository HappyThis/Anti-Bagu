from __future__ import annotations

import math
from dataclasses import dataclass

from anti_bagu.interview.events import Channel, CommittedFocus, ConversationTurn

NOISE_TEXT = frozenset({"嗯", "啊", "呃", "额", "咳", "哦", "唉", "哈"})


@dataclass(frozen=True, slots=True)
class ProjectedTurn:
    channel: Channel
    text: str
    start_turn_id: int
    end_turn_id: int
    last_created_at: float


@dataclass(frozen=True, slots=True)
class FocusPromptBuildResult:
    markdown: str
    estimated_total_tokens: int
    analysis_after_turn_id: int
    included_turn_ids: tuple[int, ...]
    included_focus_ids: tuple[str, ...]
    dialogue_start_turn_id: int | None
    through_turn_id: int
    removed_noise_turns: int
    compacted: bool


class TokenEstimator:
    def __init__(self, characters_per_token: float = 1.7) -> None:
        if characters_per_token <= 0:
            raise ValueError("characters_per_token must be positive")
        self.characters_per_token = characters_per_token

    def estimate(self, text: str) -> int:
        return max(1, math.ceil(len(text) / self.characters_per_token))


class FocusPromptBuilder:
    def __init__(
        self,
        *,
        system_prompt: str,
        target_tokens: int = 8_000,
        dialogue_target_tokens: int = 6_000,
        history_target_tokens: int = 1_600,
        fragment_merge_gap_seconds: float = 2.0,
        estimator: TokenEstimator | None = None,
    ) -> None:
        self.system_prompt = system_prompt.strip()
        self.target_tokens = target_tokens
        self.dialogue_target_tokens = dialogue_target_tokens
        self.history_target_tokens = history_target_tokens
        self.fragment_merge_gap_seconds = fragment_merge_gap_seconds
        self.estimator = estimator or TokenEstimator()

    def build(
        self,
        *,
        turns: tuple[ConversationTurn, ...],
        focuses: tuple[CommittedFocus, ...],
        after_turn_id: int = 0,
    ) -> FocusPromptBuildResult:
        pending_turns = tuple(turn for turn in turns if turn.turn_id > after_turn_id)
        focus_boundaries = {focus.source_end_turn_id for focus in focuses}
        projected_turns, noise_count = self._project_turns(
            pending_turns, focus_boundaries=focus_boundaries
        )
        selected_dialogue = self._take_recent_dialogue(
            projected_turns, self.dialogue_target_tokens
        )
        dialogue_start = (
            selected_dialogue[0].start_turn_id if selected_dialogue else None
        )
        latest_focus_id = focuses[-1].focus_id if focuses else None
        eligible_focuses = [
            focus
            for focus in focuses
            if focus.focus_id == latest_focus_id
            or dialogue_start is None
            or focus.source_end_turn_id < dialogue_start
        ]
        selected_focuses = self._take_recent_focuses(
            eligible_focuses, self.history_target_tokens
        )
        selected_dialogue, selected_focuses = self._borrow_unused_budget(
            projected_turns=projected_turns,
            eligible_focuses=eligible_focuses,
            selected_dialogue=selected_dialogue,
            selected_focuses=selected_focuses,
        )
        selected_dialogue, selected_focuses = self._fit_total_budget(
            selected_dialogue, selected_focuses
        )

        markdown = self._render(selected_focuses, selected_dialogue)
        included_turn_ids = tuple(
            turn_id
            for turn in selected_dialogue
            for turn_id in range(turn.start_turn_id, turn.end_turn_id + 1)
        )
        included_focus_ids = tuple(focus.focus_id for focus in selected_focuses)
        dialogue_start = (
            selected_dialogue[0].start_turn_id if selected_dialogue else None
        )
        compacted = (
            noise_count > 0
            or len(included_turn_ids) < len(pending_turns)
            or len(selected_focuses) < len(eligible_focuses)
        )
        return FocusPromptBuildResult(
            markdown=markdown,
            estimated_total_tokens=self._total_tokens(markdown),
            analysis_after_turn_id=after_turn_id,
            included_turn_ids=included_turn_ids,
            included_focus_ids=included_focus_ids,
            dialogue_start_turn_id=dialogue_start,
            through_turn_id=turns[-1].turn_id if turns else after_turn_id,
            removed_noise_turns=noise_count,
            compacted=compacted,
        )

    def _project_turns(
        self,
        turns: tuple[ConversationTurn, ...],
        *,
        focus_boundaries: set[int],
    ) -> tuple[list[ProjectedTurn], int]:
        projected: list[ProjectedTurn] = []
        noise_count = 0
        for turn in turns:
            text = " ".join(turn.text.split()).strip()
            normalized = text.rstrip("。！？,.!? ")
            if normalized in NOISE_TEXT:
                noise_count += 1
                continue
            if (
                projected
                and projected[-1].channel is turn.channel
                and projected[-1].end_turn_id + 1 == turn.turn_id
                and projected[-1].end_turn_id not in focus_boundaries
                and 0
                <= turn.created_at - projected[-1].last_created_at
                <= self.fragment_merge_gap_seconds
                and len(projected[-1].text) + len(text) <= 240
            ):
                previous = projected[-1]
                projected[-1] = ProjectedTurn(
                    channel=previous.channel,
                    text=f"{previous.text}{text}",
                    start_turn_id=previous.start_turn_id,
                    end_turn_id=turn.turn_id,
                    last_created_at=turn.created_at,
                )
            else:
                projected.append(
                    ProjectedTurn(
                        channel=turn.channel,
                        text=text,
                        start_turn_id=turn.turn_id,
                        end_turn_id=turn.turn_id,
                        last_created_at=turn.created_at,
                    )
                )
        return projected, noise_count

    def _take_recent_dialogue(
        self, turns: list[ProjectedTurn], token_budget: int
    ) -> list[ProjectedTurn]:
        selected: list[ProjectedTurn] = []
        for turn in reversed(turns):
            candidate = [turn, *selected]
            if self.estimator.estimate(self._render_dialogue(candidate)) > token_budget:
                break
            selected = candidate
        return selected

    def _take_recent_focuses(
        self, focuses: list[CommittedFocus], token_budget: int
    ) -> list[CommittedFocus]:
        selected: list[CommittedFocus] = []
        for focus in reversed(focuses):
            candidate = [focus, *selected]
            if self.estimator.estimate(self._render_history(candidate)) > token_budget:
                # The latest committed Focus is the semantic anchor for follow-up
                # questions. Keep it even when its code makes it exceed the soft
                # history allocation; the fixed total-budget pass will evict older
                # dialogue before considering this Focus.
                if not selected:
                    selected = [focus]
                break
            selected = candidate
        return selected

    def _borrow_unused_budget(
        self,
        *,
        projected_turns: list[ProjectedTurn],
        eligible_focuses: list[CommittedFocus],
        selected_dialogue: list[ProjectedTurn],
        selected_focuses: list[CommittedFocus],
    ) -> tuple[list[ProjectedTurn], list[CommittedFocus]]:
        dialogue_start_index = len(projected_turns) - len(selected_dialogue)
        while dialogue_start_index > 0:
            candidate_dialogue = [
                projected_turns[dialogue_start_index - 1], *selected_dialogue
            ]
            if self._total_tokens(
                self._render(selected_focuses, candidate_dialogue)
            ) > self.target_tokens:
                break
            selected_dialogue = candidate_dialogue
            dialogue_start_index -= 1

        dialogue_start = (
            selected_dialogue[0].start_turn_id if selected_dialogue else None
        )
        latest_focus_id = eligible_focuses[-1].focus_id if eligible_focuses else None
        eligible_focuses = [
            focus
            for focus in eligible_focuses
            if focus.focus_id == latest_focus_id
            or dialogue_start is None
            or focus.source_end_turn_id < dialogue_start
        ]
        selected_focuses = [
            focus
            for focus in selected_focuses
            if focus.focus_id == latest_focus_id
            or dialogue_start is None
            or focus.source_end_turn_id < dialogue_start
        ]
        selected_focus_ids = {focus.focus_id for focus in selected_focuses}
        for focus in reversed(eligible_focuses):
            if focus.focus_id in selected_focus_ids:
                continue
            candidate_focuses = sorted(
                [focus, *selected_focuses], key=lambda item: item.created_at
            )
            if self._total_tokens(
                self._render(candidate_focuses, selected_dialogue)
            ) > self.target_tokens:
                break
            selected_focuses = candidate_focuses
            selected_focus_ids.add(focus.focus_id)
        return selected_dialogue, selected_focuses

    def _fit_total_budget(
        self,
        dialogue: list[ProjectedTurn],
        focuses: list[CommittedFocus],
    ) -> tuple[list[ProjectedTurn], list[CommittedFocus]]:
        while self._total_tokens(self._render(focuses, dialogue)) > self.target_tokens:
            if len(focuses) > 1:
                focuses = focuses[1:]
            elif len(dialogue) > 1:
                dialogue = dialogue[1:]
            elif focuses:
                # Only an exceptionally large single Focus can reach this branch.
                # The hard 8K limit still wins when no further history or dialogue
                # can be removed.
                focuses = []
            else:
                break
        return dialogue, focuses

    def _total_tokens(self, markdown: str) -> int:
        return self.estimator.estimate(self.system_prompt) + self.estimator.estimate(
            markdown
        )

    def _render(
        self,
        focuses: list[CommittedFocus],
        dialogue: list[ProjectedTurn],
    ) -> str:
        return f"{self._render_history(focuses)}\n\n{self._render_dialogue(dialogue)}"

    @staticmethod
    def _render_history(focuses: list[CommittedFocus]) -> str:
        lines = ["# 历史分析结果"]
        if not focuses:
            return "# 历史分析结果\n无"
        for index, focus in enumerate(focuses, start=1):
            answer = " ".join(focus.recommended_answer.split()).strip() or "无"
            label = "当前 Focus" if index == len(focuses) else f"较早 Focus {index}"
            lines.extend(
                [
                    "",
                    f"## {label}",
                    f"Q: {' '.join(focus.question.split())}",
                    f"A: {answer}",
                ]
            )
            if index == len(focuses) and focus.code:
                lines.extend(["Code:", "```python", focus.code.strip(), "```"])
        return "\n".join(lines)

    @staticmethod
    def _render_dialogue(dialogue: list[ProjectedTurn]) -> str:
        lines = ["# 上次分析后新增的对话"]
        if not dialogue:
            return "# 上次分析后新增的对话\n无"
        latest_interviewer_index = next(
            (
                index
                for index in range(len(dialogue) - 1, -1, -1)
                if dialogue[index].channel is Channel.INTERVIEWER
            ),
            None,
        )
        for index, turn in enumerate(dialogue):
            if turn.channel is Channel.INTERVIEWER:
                role = "I（最新）" if index == latest_interviewer_index else "I"
            else:
                role = "C"
            lines.append(f"- {role}: {turn.text}")
        return "\n".join(lines)
