---
description: Run the Owloop autonomous loop
---

Use this command to run an autonomous Owloop loop:

```bash
owloop run
```

For a limited run:
```bash
owloop run -n 20              # max 20 iterations
owloop run --max-duration 120 # stop after 2 hours
```

To use a different coding agent:
```bash
owloop run --agent claude     # default
owloop run --agent kimi       # Kimi Code CLI
```

The loop picks specs from `.owloop/specs/` in order, implements each one, verifies acceptance criteria, and commits on success. Each iteration spawns a fresh agent process in auto permission mode.

The agent outputs `<promise>DONE</promise>` when a spec is complete.
