"""Runtime evaluation gate."""

from __future__ import annotations

from dataclasses import dataclass

from .models import RuntimeState


@dataclass(slots=True)
class EvaluationResult:
    done: bool
    final_score: float
    test_pass_rate: float
    spec_alignment: float
    reviewer_score: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "done": self.done,
            "final_score": self.final_score,
            "test_pass_rate": self.test_pass_rate,
            "spec_alignment": self.spec_alignment,
            "reviewer_score": self.reviewer_score,
            "reason": self.reason,
        }


class Evaluator:
    """Compute DONE using the v0.1 scoring formula."""

    done_threshold = 0.85

    def evaluate(self, state: RuntimeState) -> EvaluationResult:
        nodes = state.task_graph.nodes
        if not nodes:
            return EvaluationResult(False, 0.0, 0.0, 0.0, 0.0, "No task graph nodes exist.")

        completed = [node for node in nodes if node.status == "completed"]
        failed = [node for node in nodes if node.status in {"failed", "blocked"}]
        test_nodes = [node for node in nodes if node.type == "test"]
        review_nodes = [node for node in nodes if node.type == "review"]

        test_pass_rate = self._ratio_completed(test_nodes) if test_nodes else self._ratio_completed(nodes)
        spec_alignment = len(completed) / len(nodes)
        reviewer_score = self._ratio_completed(review_nodes) if review_nodes else 0.0

        final_score = round(test_pass_rate * 0.5 + spec_alignment * 0.3 + reviewer_score * 0.2, 4)
        all_complete = len(completed) == len(nodes)
        done = all_complete and not failed and final_score >= self.done_threshold

        if failed:
            reason = "One or more required tasks failed or are blocked."
        elif not all_complete:
            reason = "Task graph still has unfinished nodes."
        elif final_score < self.done_threshold:
            reason = f"Final score {final_score:.2f} is below {self.done_threshold:.2f}."
        else:
            reason = "DONE condition met."

        return EvaluationResult(
            done=done,
            final_score=final_score,
            test_pass_rate=round(test_pass_rate, 4),
            spec_alignment=round(spec_alignment, 4),
            reviewer_score=round(reviewer_score, 4),
            reason=reason,
        )

    def _ratio_completed(self, nodes: list) -> float:
        if not nodes:
            return 0.0
        return len([node for node in nodes if node.status == "completed"]) / len(nodes)
