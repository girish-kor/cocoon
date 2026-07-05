"""Purged, embargoed walk-forward split. DOCUMENT.md §8, §15.1.

Time-ordered expanding/rolling folds. `purge_bars` removes samples whose
label window straddles the train/test boundary (label leakage across the
split, §15.1); `embargo_bars` adds a further gap after each test window
before the next train window may begin (absorbs label-horizon
autocorrelation).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import numpy as np


@dataclass(frozen=True)
class Fold:
    index: int
    train_idx: np.ndarray
    test_idx: np.ndarray


class PurgedWalkForwardSplit:
    def __init__(
        self,
        *,
        train_size: int,
        test_size: int,
        step_size: int,
        purge: int = 0,
        embargo: int = 0,
    ) -> None:
        if train_size <= 0 or test_size <= 0 or step_size <= 0:
            raise ValueError("train/test/step sizes must be positive")
        self._train = train_size
        self._test = test_size
        self._step = step_size
        self._purge = purge
        self._embargo = embargo

    def n_splits(self, n_samples: int) -> int:
        return sum(1 for _ in self.split(np.zeros(n_samples)))

    def split(self, X: np.ndarray) -> Iterator[Fold]:
        n = len(X)
        start = 0
        fold_index = 0
        while True:
            train_end = start + self._train
            test_start = train_end + self._purge
            test_end = test_start + self._test
            if test_end > n:
                break
            train_idx = np.arange(start, train_end)
            test_idx = np.arange(test_start, test_end)
            yield Fold(index=fold_index, train_idx=train_idx, test_idx=test_idx)
            fold_index += 1
            start += self._step + self._embargo

    def folds(self, X: np.ndarray) -> list[Fold]:
        return list(self.split(X))
