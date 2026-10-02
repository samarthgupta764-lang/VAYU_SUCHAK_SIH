"""
Back-test the APIx against MoSPI CPI Air Fare — scripts/backtest.py

    python -m scripts.backtest
"""

from __future__ import annotations

from pipeline.backtest import historical, live


def _show(r) -> None:
    print(f"\n  === {r.mode.upper()} ===")
    print(f"  {r.note}")
    if not r.months:
        return
    print(f"\n  {'month':<10} {'APIx':>8} {'CPI air fare':>14}")
    for m, a, c in zip(r.months, r.apix, r.cpi_air_fare):
        print(f"  {m:<10} {a:>8.2f} {c:>14.2f}")
    if r.mom_correlation is not None:
        print(f"\n  month-over-month correlation : {r.mom_correlation}")
    if r.direction_agreement is not None:
        print(f"  same-direction months        : {r.direction_agreement:.0%}")


def main() -> None:
    print("VAYU-SUCHAK · APIx back-test vs MoSPI CPI 'Air Fare (Economy, adult)'")
    _show(live())
    _show(historical())
    print()


if __name__ == "__main__":
    main()
