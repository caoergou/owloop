# API / Framework / Dependency Migration Reference

Target: read this when a spec migrates APIs, frameworks, or dependencies.

## Sources & Confidence

Sources: general software-engineering practice; no dedicated empirical study was found for API migration with autonomous loops. Treat this document as a heuristic checklist rather than a verified playbook.

## Safe Migration Steps

1. Consider reading the official migration guide and changelog for the target version.
2. Pin current behavior with tests before changing any call sites.
3. Migrate one call site or module at a time.
4. Run the full test suite after each batch.
5. Keep the old API path working until the new path is fully verified, when feasible.

## Common Verification

After each batch:

- Build typically passes (install / compile / import).
- Existing tests pass.
- Deprecation warnings introduced by the migration are gone.
- New usage matches the target API contract.

## Anti-Patterns

- Consider not changing API shape and behavior at the same time. Migrate shape first, behavior second.
- Avoid bulk find-and-replace without tests covering the replaced call sites.
- Consider not bumping major dependencies in the same spec as business-logic changes.

If a migration is too large for one spec, split it: one spec per module or per API surface.
