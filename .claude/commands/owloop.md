---
description: Run the Owloop autonomous loop (Claude Code)
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

The loop picks specs from `specs/` in order, implements each one, verifies acceptance criteria, and commits on success. Each iteration spawns a fresh `claude -p` with `--permission-mode auto`.

The agent outputs `<promise>DONE</promise>` when a spec is complete.
