SHELL := /bin/sh

COMPOSE_FILE ?= docker-compose.dev.yml
ENV_FILE ?= $(if $(wildcard .env),.env,.env.example)
HA_URL ?= http://localhost:8123
UV_CACHE_DIR ?= .cache/uv

COMPOSE := docker compose --env-file $(ENV_FILE) -f $(COMPOSE_FILE)

.PHONY: dev dev-up dev-down logs restart reload-entry lint check

dev:
	$(COMPOSE) up

dev-up:
	$(COMPOSE) up -d

dev-down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f homeassistant

restart:
	$(COMPOSE) restart homeassistant

reload-entry:
	@test -n "$(ENTRY_ID)" || (echo "ENTRY_ID is required, for example: make reload-entry ENTRY_ID=abc123 HA_TOKEN=token" >&2; exit 1)
	@test -n "$(HA_TOKEN)" || (echo "HA_TOKEN is required. Create a long-lived access token in Home Assistant and pass it as HA_TOKEN." >&2; exit 1)
	@curl -fsS -X POST \
		--connect-timeout 5 \
		--max-time 15 \
		-H "Authorization: Bearer $(HA_TOKEN)" \
		-H "Content-Type: application/json" \
		-d '{"entry_id":"$(ENTRY_ID)"}' \
		"$(HA_URL)/api/services/homeassistant/reload_config_entry"

lint:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uvx ruff check custom_components/electrolux

check:
	@test -d custom_components/electrolux
	@test -f custom_components/electrolux/manifest.json
	@test "$$(find custom_components -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')" = "1" || (echo "Expected exactly one integration under custom_components/" >&2; exit 1)
	python3 -c 'from pathlib import Path; import tokenize; [compile(tokenize.open(path).read(), str(path), "exec") for path in Path("custom_components/electrolux").rglob("*.py")]'
