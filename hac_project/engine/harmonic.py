"""
engine/harmonic.py

Pure functions for sizing SVG (Static Var Generator / Active Harmonic Filter).
No streamlit imports here — this module must stay UI-agnostic per project convention.

Design-phase estimation flow (no measured power-quality data available):
    1. IL, Isc  -> isc_il_ratio()
    2. ratio    -> lookup_tdd_limit()          [IEEE-519-2014 Table 2]
    3. IL, THDi_load, tdd_target -> required_filter_current()
    4. required current + margin -> select_svg_size()

References:
    - IEEE Std 519-2014, Table 2 "Current Distortion Limits for Systems
      Rated 120 V through 69 kV" (odd-harmonic limits + TDD column).
    - Field practice for AHF sizing typically recommends a continuous
      design margin (commonly ~20%) above the calculated harmonic
      compensation current, since the filter current-limits rather than
      auto-extends its rating if the harmonic load grows post-commissioning.
"""

from dataclasses import dataclass


# IEEE-519-2014 Table 2 — TDD limit (%) by Isc/IL ratio.
# Each entry: (upper_bound_exclusive, tdd_limit_percent)
# The last band (>1000) uses float('inf') as the upper bound.
IEEE519_TDD_TABLE = [
    (20, 5.0),
    (50, 8.0),
    (100, 12.0),
    (1000, 15.0),
    (float("inf"), 20.0),
]


@dataclass
class SvgSizingResult:
    isc_il_ratio: float
    tdd_limit_percent: float          # from IEEE-519 table (not-to-exceed)
    i_harmonic_before: float          # A, at THDi_load
    i_harmonic_target: float          # A, at tdd_limit (or user target)
    i_filter_required_raw: float      # A, before margin
    margin_percent: float
    i_filter_required_with_margin: float  # A, after margin
    selected_svg_size: float | None   # A, smallest standard size >= required
    warning: str | None = None


def isc_il_ratio(isc: float, il: float) -> float:
    """Isc/IL ratio per IEEE-519. Raises if IL <= 0."""
    if il <= 0:
        raise ValueError("IL (load current) must be > 0")
    if isc < 0:
        raise ValueError("Isc (short-circuit current) must be >= 0")
    return isc / il


def lookup_tdd_limit(ratio: float) -> float:
    """Return IEEE-519-2014 TDD limit (%) for a given Isc/IL ratio."""
    for upper_bound, tdd_limit in IEEE519_TDD_TABLE:
        if ratio < upper_bound:
            return tdd_limit
    # Should be unreachable because of the float('inf') band, kept for safety.
    return IEEE519_TDD_TABLE[-1][1]


def required_filter_current(
    il: float,
    thdi_load_percent: float,
    tdd_target_percent: float,
) -> tuple[float, float, float]:
    """
    Compute the harmonic current that must be removed to bring THDi_load
    down to tdd_target_percent.

    Uses the RMS relationship: I_harmonic = I_fundamental * (THDi / 100)
    as a simplified approximation (consistent with common field-practice
    sizing formulas that treat IL as the RMS fundamental/load current).

    Returns: (i_harmonic_before, i_harmonic_target, i_filter_required_raw)
    """
    if thdi_load_percent < 0 or tdd_target_percent < 0:
        raise ValueError("THDi values must be >= 0")

    i_harmonic_before = il * (thdi_load_percent / 100.0)
    i_harmonic_target = il * (tdd_target_percent / 100.0)
    i_filter_required_raw = max(0.0, i_harmonic_before - i_harmonic_target)

    return i_harmonic_before, i_harmonic_target, i_filter_required_raw


def select_svg_size(
    required_current: float,
    standard_sizes: list[float],
) -> float | None:
    """
    Return the smallest standard SVG size >= required_current.
    Returns None if required_current exceeds every available size
    (caller should suggest paralleling modules — see constants.py notes
    on the 300/400/500/600A "Large Capacity" tier).
    """
    candidates = sorted(s for s in standard_sizes if s >= required_current)
    return candidates[0] if candidates else None


def size_svg(
    il: float,
    isc: float,
    thdi_load_percent: float,
    standard_sizes: list[float],
    tdd_target_percent: float | None = None,
    margin_percent: float = 20.0,
) -> SvgSizingResult:
    """
    Full sizing flow, orchestrating the steps above.

    tdd_target_percent: if None, the IEEE-519 table limit (based on Isc/IL)
        is used directly as the target. Pass an explicit value to override
        with a stricter design target.
    margin_percent: design margin applied on top of the raw required
        filter current before selecting a standard size. Default 20
        (adjustable in the UI).
    """
    ratio = isc_il_ratio(isc, il)
    tdd_limit = lookup_tdd_limit(ratio)
    target = tdd_target_percent if tdd_target_percent is not None else tdd_limit

    warning = None
    if tdd_target_percent is not None and tdd_target_percent > tdd_limit:
        warning = (
            f"Target THDi ({tdd_target_percent:.1f}%) is looser than the "
            f"IEEE-519 TDD limit ({tdd_limit:.1f}%) for this Isc/IL ratio. "
            f"Result will not be IEEE-519 compliant."
        )

    i_before, i_target, i_raw = required_filter_current(il, thdi_load_percent, target)
    i_with_margin = i_raw * (1 + margin_percent / 100.0)
    selected = select_svg_size(i_with_margin, standard_sizes)

    if selected is None and warning is None:
        warning = (
            f"Required filter current ({i_with_margin:.1f} A) exceeds the "
            f"largest single standard size. Consider paralleling modules."
        )

    return SvgSizingResult(
        isc_il_ratio=ratio,
        tdd_limit_percent=tdd_limit,
        i_harmonic_before=i_before,
        i_harmonic_target=i_target,
        i_filter_required_raw=i_raw,
        margin_percent=margin_percent,
        i_filter_required_with_margin=i_with_margin,
        selected_svg_size=selected,
        warning=warning,
    )
