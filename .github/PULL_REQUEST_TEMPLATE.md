## What this changes

<!-- A short description of the change and why. -->

## How I verified it

<!-- Cocoon's credibility comes from honesty. State exactly what you ran and observed. -->

- [ ] `python -m compileall src` passes
- [ ] `cocoon --help` loads
- [ ] Ran the affected command(s) and pasted real output below

```
# real output here
```

## Design invariants (check all that apply)

- [ ] Features remain point-in-time-safe (no future leakage) — describe how verified
- [ ] Layering preserved (imports go downward only)
- [ ] Backtest and live still share one code path
- [ ] Determinism preserved (byte-identical dataset/run IDs) if dataset/training touched
- [ ] Docs updated (`USECASE.md` for commands, `README.md` if user-facing)

## Anything untested?

<!-- Be honest. If part of this couldn't be validated (e.g. real MT5 terminal), say so. -->
