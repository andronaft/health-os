"""Fill in missing canonical values (#11). Dry-run by default.

    uv run python -m scripts.recompute_canonical            # report only
    uv run python -m scripts.recompute_canonical --apply    # write

Run it after adding synonyms/conversions, or after an import that wrote observations directly.
"""
from __future__ import annotations

import sys

from core.db import engine
from core.recompute import recompute_canonical
from safety.alerts import send_critical_alert


def main() -> None:
    apply = "--apply" in sys.argv
    with engine.begin() as conn:
        rep = recompute_canonical(conn, apply=apply, alerter=send_critical_alert)
    print(f"Rows without a canonical value: {rep.scanned}")
    print(f"{'Updated' if apply else 'Would update'}: {rep.n_fixed}")
    for (code, unit), n in rep.fixed.most_common(15):
        print(f"  {n:6}  {code} [{unit}]")
    if rep.n_unconvertible:
        print(f"Still unconvertible (fix the unit or add a conversion): {rep.n_unconvertible}")
        for (code, unit, cu), n in rep.unconvertible.most_common(15):
            print(f"  {n:6}  {code}: {unit!r} → {cu!r}")
    if rep.critical:
        # the filled values went through the critical check: these are critical
        print(f"\n!!! CRITICAL values among them: {len(rep.critical)} "
              f"({'flagged and alerted' if apply else 'would be flagged'})")
        for c in rep.critical:
            back = (" — was APPROVED, " + ("returned to pending review" if apply
                                          else "would return to pending review")
                    if c["was_approved"] else "")
            print(f"  {c['value']} → {c['canonical']:g} {c['canonical_unit']}: {c['message']}{back}")
    if rep.limit_unverified:
        print(f"\nOnly a limit on the form, critical check impossible: {len(rep.limit_unverified)}")
        for c in rep.limit_unverified:
            print(f"  {c['value']}")
    if not apply and rep.n_fixed:
        print("Dry run — re-run with --apply to write.")


if __name__ == "__main__":
    main()
