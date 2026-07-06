# Architecture Checklist

The goal is to turn the machine-checkable parts of architecture review into verification gates. Not every architectural concern can be checked by a shell command, but many can be detected with static analysis or targeted tests.

## SOLID Smells — Machine-Checkable Signals

### Single Responsibility Principle (SRP)

| Signal | Check |
|---|---|
| File grows too large | `wc -l src/owloop/module.py` → threshold |
| Many unrelated imports | `git diff -- src/owloop/module.py` spans multiple domains |
| Cyclomatic complexity high | `radon cc -nc src/owloop/` or ruff complexity rules |

**Command template:**

```bash
uv run radon cc -nc src/owloop/module.py
```

Expected: no block with complexity above project threshold.

### Open/Closed Principle (OCP)

| Signal | Check |
|---|---|
| Adding a variant requires editing a long `if/elif` chain | Review diff for new branches in central dispatch |
| No extension point exists | grep for `NotImplementedError`, abstract base classes, or protocols |

**Command template:**

```bash
git diff -- src/owloop/ | grep -E '^\+.*(elif|else:|case)' | wc -l
```

Expected: count does not grow significantly without a matching abstraction.

### Liskov Substitution Principle (LSP)

| Signal | Check |
|---|---|
| Subclass narrows behavior | Search for `raise NotImplementedError` in overrides |
| Type checks against concrete subclasses | `grep -R "isinstance.*ConcreteClass" src/` |

### Interface Segregation Principle (ISP)

| Signal | Check |
|---|---|
| Broad interface with unused methods | `grep -c "def "` in protocol vs implementers |

### Dependency Inversion Principle (DIP)

| Signal | Check |
|---|---|
| Business logic imports infrastructure directly | `grep -R "import requests\|import boto3" src/domain/` |

## Common Code Smells — Shell-Detectable

| Smell | Detection command | Threshold |
|---|---|---|
| Long method | `radon cc -nc src/owloop/` | complexity ≤ threshold |
| Long file | `wc -l src/owloop/*.py` | ≤ 400 lines (project-specific) |
| Dead code | `vulture src/owloop/` or `ruff check src/owloop/` | 0 unused |
| Magic numbers/strings | `git diff --diff-filter=AM -U0 \| grep -E '^\+[0-9]{3,}'` | review manually |
| Too many function arguments | `radon mi -s src/owloop/` | no extremely low maintainability |

## Spec-Level Criterion Template

```bash
# Complexity guard
uv run radon cc -nc src/owloop/module.py
```

Expected: no complexity block above project threshold.

```bash
# Dead code guard
uv run vulture src/owloop/module.py --min-confidence 80 2>&1 | grep -v "test_" || true
```

Expected: empty output.

## What NOT to gate automatically

- Whether an abstraction is "right" — needs human judgment.
- Whether a module boundary matches the domain — needs design review.
- Whether inheritance is appropriate — use composition heuristic but not a hard gate.

For these, add a [Human Review Trigger](../human-review-triggers.md) instead of a shell command.
