---
description: Run the Owloop loop for a spec (Claude Code)
---

Use this command to run an autonomous Owloop loop for a spec:

```
/owloop:owloop "Implement spec {spec-name} from specs/{spec-name}/spec.md.
Complete ALL Completion Signal requirements.
Output <promise>DONE</promise> when complete." --completion-promise "DONE" --max-iterations 30
```
