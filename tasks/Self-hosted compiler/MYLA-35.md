---
id: MYLA-35
title: justfile recipes drop arguments and leave files behind
type: bug
status: backlog
priority: low
labels: [scripts, selfhost]
---
- [ ] `just run source *args` never passes `{{args}}` to the program
- [ ] `build/myla build` leaves `<out>.s` and `<out>.o` next to the binary
- [ ] `build/myla` defaults the stdlib root to the relative `src/myla`, so it only works from the repository root (see [[MYLA-31]])
- [ ] `just bootstrap` duplicates `scripts/bootstrap.sh` (and adds the stage-4 CLI build and timers); keep one of them as the source of truth
