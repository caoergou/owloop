# Agent Instructions

## Quick Start

**To start the owloop loop:**
```bash
owloop run
```

This works directly from specs — no planning step needed.

---

## How owloop Works

1. Agent reads `specs/` folder
2. Picks the **highest priority incomplete spec** (lowest number first)
3. Implements it completely
4. Marks spec as `COMPLETE`
5. Outputs `<promise>DONE</promise>`
6. Loop restarts with fresh context
7. Repeat until all specs are done

---

## Spec Priority

Specs are numbered: `001-xxx`, `002-xxx`, etc.
- Lower number = higher priority
- Work on incomplete specs in order

---

Specs are the plan. No separate planning step is needed.
