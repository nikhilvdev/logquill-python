## Summary

<!-- What does this change, and why? -->

## Checklist

- [ ] `ruff check .` passes
- [ ] `mypy logquill` passes (`--strict` on the public API)
- [ ] `pytest` passes, and new surface area has test coverage
- [ ] Public API additions are documented in `README.md` with a runnable example
- [ ] `CHANGELOG.md` has an entry under `Unreleased`
- [ ] If this touches the cross-language contract (levels, logger methods,
      record shape, transport/plugin contracts, config shape) shared with
      `logquill-js`, a matching tracking issue/PR is opened there

## Scope

<!-- One concern per PR where possible. Call out here if this
     intentionally spans more than one. -->
