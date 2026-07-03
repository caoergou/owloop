# API / Framework / Dependency Migration Reference

Target: read this when a spec migrates APIs, frameworks, or dependencies.

## Safe Migration Steps

1. Read the official migration guide and changelog for the target version.
2. Pin current behavior with tests before changing any call sites.
3. Migrate one call site or module at a time.
4. Run the full test suite after each batch.
5. Keep the old API path working until the new path is fully verified, when feasible.

## Common Verification

After each batch:

- Build passes (install / compile / import).
- Existing tests pass.
- Deprecation warnings introduced by the migration are gone.
- New usage matches the target API contract.

## Anti-Patterns

- Do not change API shape and behavior at the same time. Migrate shape first, behavior second.
- Do not perform bulk find-and-replace without tests covering the replaced call sites.
- Do not bump major dependencies in the same spec as business-logic changes.

If a migration is too large for one spec, split it: one spec per module or per API surface.
