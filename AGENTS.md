# Agents Guide

## Purpose

This repository contains the Electrolux Home custom integration for Home Assistant, published as a HACS integration.

## Project Layout

- Runtime integration code lives in `custom_components/electrolux/`.
- HACS metadata lives in `hacs.json`.
- Local Home Assistant development config lives in `dev/config/`.
- Do not move integration runtime files out of `custom_components/electrolux/`; HACS expects this layout.

## Electrolux API

- Electrolux API documentation is available at https://developer.electrolux.one/documentation.
- Treat the official documentation as the source of truth for endpoints and payloads.
- The current account email is available from `GET /api/v1/users/current/email` and should be used as the config entry title.

## Development Commands

- Start Home Assistant in the foreground:
  - `make dev`
- Start Home Assistant in the background:
  - `make dev-up`
- Follow Home Assistant logs:
  - `make logs`
- Restart Home Assistant after Python code changes:
  - `make restart`
- Stop the dev environment:
  - `make dev-down`
- Reload an existing config entry without restarting HA:
  - `make reload-entry ENTRY_ID=<entry_id> HA_TOKEN=<token>`
- Run the linter:
  - `make lint`
- Run structural and syntax checks:
  - `make check`

## Required Workflow

- After every code change, run `make lint`.
- After every code change that affects the running integration, reload the dev environment:
  - Prefer `make restart` for Python code changes, because Home Assistant does not reliably re-import custom integration modules during config-entry reload.
  - Use `make reload-entry ENTRY_ID=<entry_id> HA_TOKEN=<token>` only for runtime/config-entry behavior that is already loaded in memory.
- If Home Assistant is not running locally, start it with `make dev-up` before verifying reload behavior.

## Linting

- Ruff is the project linter and is configured in `pyproject.toml`.
- `make lint` runs Ruff through `uvx` and stores its cache under `.cache/uv`.
- Keep lint fixes focused. Do not perform unrelated style rewrites while implementing behavior changes.

## Git Hygiene

- Do not commit generated Home Assistant runtime state from `dev/config/`.
- Do not commit Python bytecode, `__pycache__`, `.DS_Store`, or local `.env` files.
- Preserve user changes in the working tree. Do not revert unrelated edits.
