"""Pure statistics helpers used by every judgecal analysis.

Everything in this module is standard-library only, deterministic, and free of
I/O. Each function is small enough to verify against a textbook example, and
the test suite does exactly that (Cohen 1960 worked example, exact binomial
tail sums, Wilson 1927 interval).
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

# 97.5th percentile of the standard normal distribution, i.e. z for a
# two-sided 95% confidence interval.
Z_95 = 1.959963984540054


def wilson_interval(successes: int, trials: int, z: float = Z_95) -> Tuple[float, float]:
    """Wilson score 95% confidence interval for a binomial proportion.

    Preferred over the normal (Wald) interval because it behaves sanely for
    small n and proportions near 0 or 1 — both common in sliced judge logs.
    Returns ``(0.0, 1.0)`` when there are no trials (total uncertainty).
    """
    if trials <= 0:
        return (0.0, 1.0)
    if successes < 0 or successes > trials:
        raise ValueError(f"successes={successes} out of range for trials={trials}")
    p = successes / trials
    z2 = z * z
    denom = 1.0 + z2 / trials
    center = (p + z2 / (2.0 * trials)) / denom
    half = (z / denom) * math.sqrt(p * (1.0 - p) / trials + z2 / (4.0 * trials * trials))
    low = max(0.0, center - half)
    high = min(1.0, center + half)
    # At the boundaries the exact Wilson limit is 0 or 1; snap the float noise.
    if successes == 0:
        low = 0.0
    if successes == trials:
        high = 1.0
    return (low, high)


def _log_binom_pmf(k: int, n: int, p: float) -> float:
    """Log of the binomial probability mass function, stable for large n."""
    log_comb = math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
    # p is always strictly inside (0, 1) at the call sites below.
    return log_comb + k * math.log(p) + (n - k) * math.log(1.0 - p)


def binom_two_sided(k: int, n: int, p: float = 0.5) -> float:
    """Exact two-sided binomial test p-value (method of small p-values).

    Sums the probability of every outcome at most as likely as the observed
    one — the same definition SciPy's ``binomtest`` uses — computed in log
    space so it stays exact-ish for logs with hundreds of thousands of rows.
    Returns 1.0 for an empty sample: no data is no evidence.
    """
    if n <= 0:
        return 1.0
    if k < 0 or k > n:
        raise ValueError(f"k={k} out of range for n={n}")
    if not 0.0 < p < 1.0:
        raise ValueError("p must be strictly between 0 and 1")
    observed = _log_binom_pmf(k, n, p)
    # Relative tolerance so ties in probability (e.g. symmetric p=0.5 cases)
    # are counted on both sides despite floating-point noise.
    threshold = observed + 1e-9
    total = 0.0
    for i in range(n + 1):
        lp = _log_binom_pmf(i, n, p)
        if lp <= threshold:
            total += math.exp(lp)
    return min(1.0, total)


def cohen_kappa(pairs: Sequence[Tuple[str, str]]) -> Optional[float]:
    """Cohen's kappa for two raters over the same items.

    ``pairs`` is a sequence of ``(rater1_label, rater2_label)``. Labels are
    treated as unordered categories (for judgecal: ``a``, ``b``, ``tie``).
    Returns ``None`` for an empty input. When expected agreement is 1.0 (both
    raters constant), kappa is undefined; we follow common practice and return
    1.0 if they agree perfectly, else 0.0.
    """
    n = len(pairs)
    if n == 0:
        return None
    labels = sorted({x for x, _ in pairs} | {y for _, y in pairs})
    row: Dict[str, int] = {lab: 0 for lab in labels}
    col: Dict[str, int] = {lab: 0 for lab in labels}
    agree = 0
    for x, y in pairs:
        row[x] += 1
        col[y] += 1
        if x == y:
            agree += 1
    po = agree / n
    pe = sum(row[lab] * col[lab] for lab in labels) / (n * n)
    if pe >= 1.0 - 1e-12:
        return 1.0 if po >= 1.0 - 1e-12 else 0.0
    return (po - pe) / (1.0 - pe)


def kappa_band(kappa: float) -> str:
    """Landis & Koch (1977) interpretation band for a kappa value."""
    if kappa < 0.0:
        return "worse than chance"
    if kappa < 0.20:
        return "slight"
    if kappa < 0.40:
        return "fair"
    if kappa < 0.60:
        return "moderate"
    if kappa < 0.80:
        return "substantial"
    return "almost perfect"


def pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    """Pearson correlation coefficient, or ``None`` when undefined.

    Undefined cases: fewer than two points, or zero variance on either axis
    (e.g. every compared pair has the same length ratio).
    """
    n = len(xs)
    if n != len(ys):
        raise ValueError("xs and ys must have the same length")
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0.0 or syy <= 0.0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    r = sxy / math.sqrt(sxx * syy)
    # Clamp floating-point drift so callers can rely on [-1, 1].
    return max(-1.0, min(1.0, r))


def confusion_matrix(
    pairs: Sequence[Tuple[str, str]], labels: Sequence[str]
) -> Dict[str, Dict[str, int]]:
    """Counts of (rater1 label, rater2 label) over a fixed label order."""
    matrix: Dict[str, Dict[str, int]] = {a: {b: 0 for b in labels} for a in labels}
    for x, y in pairs:
        matrix[x][y] += 1
    return matrix


def proportion(successes: int, trials: int) -> Optional[float]:
    """Safe ratio helper: ``None`` instead of ZeroDivisionError."""
    if trials <= 0:
        return None
    return successes / trials


def round_opt(value: Optional[float], digits: int = 4) -> Optional[float]:
    """Round a float that may be None (for stable JSON output)."""
    if value is None:
        return None
    return round(value, digits)


def mean(values: List[float]) -> Optional[float]:
    """Arithmetic mean, ``None`` for an empty list."""
    if not values:
        return None
    return sum(values) / len(values)
