# Shortcuts for tasks.py on macOS/Linux: `make dev` runs `uv run tasks.py dev`.
# On Windows, run `uv run tasks.py <task>`. Settings pass through:
#   make dev API_PORT=9000 · make check PM=pnpm · make revision m="add widgets"
export PM API_PORT WEB_PORT DB_RUNTIME DB_CONTAINER DB_IMAGE DB_PORT DB_ROOT_PASSWORD

TASKS := help setup db-up db-down migrate revision seed key prices api web worker dev test lint check build
.PHONY: $(TASKS)
.DEFAULT_GOAL := help

$(TASKS):
	@uv run --quiet tasks.py $@ $(if $(m),"$(m)")
