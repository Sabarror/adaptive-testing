"""Предметный алгоритм: не зависит от Django и HTTP."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
import random

class AdaptiveStrategy(ABC):
    @abstractmethod
    def next_target(self, actual: int, correct: bool) -> int: ...

class StepAdaptiveStrategy(AdaptiveStrategy):
    def next_target(self, actual, correct):
        return max(1, min(5, actual + (1 if correct else -1)))

@dataclass(frozen=True)
class Candidate:
    id: int
    difficulty: int

class QuestionSelector:
    def __init__(self, rng=None):
        self.rng = rng if rng is not None else random.Random()
    def choose(self, candidates, target):
        if not candidates:
            raise ValueError('Доступные вопросы закончились.')
        level = min({q.difficulty for q in candidates}, key=lambda v: (abs(v-target), v))
        question = self.rng.choice(sorted([q for q in candidates if q.difficulty == level], key=lambda q: q.id))
        reason = ('Вопрос целевого уровня.' if level == target else f'Уровень {target} исчерпан; ближайший доступный — {level}. При равенстве выбирается меньший уровень.')
        return question, reason

class AdaptiveEngine:
    def __init__(self, strategy=None, selector=None):
        self.strategy = strategy or StepAdaptiveStrategy()
        self.selector = selector or QuestionSelector()
    def choose(self, bank, target): return self.selector.choose(bank, target)
    def next_target(self, actual, correct): return self.strategy.next_target(actual, correct)

def simulate(initial, outcomes, counts, seed):
    engine = AdaptiveEngine(selector=QuestionSelector(random.Random(seed)))
    bank = [Candidate(level*1000+i, level) for level, count in enumerate(counts, 1) for i in range(count)]
    rows, target = [], initial
    for outcome in outcomes:
        if not bank: return rows, 'Моделирование остановлено: доступные вопросы закончились.'
        q, reason = engine.choose(bank, target)
        following = engine.next_target(q.difficulty, outcome)
        rows.append(dict(target=target, actual=q.difficulty, correct=outcome, following=following, reason=reason))
        bank.remove(q)
        target = following
    return rows, 'Моделирование завершено.'
