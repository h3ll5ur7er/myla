---
id: MYLA-58
title: "Test tooling: pytest vs unittest, and a slow burn suite"
type: chore
status: backlog
priority: low
labels: [tests]
---
- [ ] `pyproject.toml` says the suite is unittest-only, but `uv run pytest` is what people (and agents) run; it works only through a globally installed pytest. Either add pytest as a dev dependency or document `python3 -m unittest discover -s tests -t .` as the way ([[Development/Testing]])
- [ ] The burn suite takes about 135 s (native builds of every example and of the self-hosted tools); split a fast tier from the slow one
- [ ] Runtime errors in the error corpus are only checked in the interpreter; module errors (`module error`) have no corpus stage
