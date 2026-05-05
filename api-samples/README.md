# Electrolux API samples

This directory contains Electrolux API samples grouped by appliance PNC.

Each mapped appliance uses this structure:

```text
api-samples/<PNC>/capabilities.json
api-samples/<PNC>/state.json
```

- `capabilities.json` contains the sanitized raw response from `GET /api/v1/appliances/{applianceId}/info`.
- `state.json` contains the sanitized raw response from `GET /api/v1/appliances/{applianceId}/state`.
- PNC values are intentionally kept as directory names.
- Per-device identifiers and sensitive values must be removed or replaced before committing samples.
- When a real capture is not available, the mapped appliance can use a reference sample based on the integration's known capability mapping.

## Mapped appliances

| PNC | Brand | Model | Variant | Color | Device type | Source | Samples |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `950011559` | Electrolux | Well A7 | CADR300 | Light Grey | Air purifier | Sanitized API capture | [`capabilities.json`](950011559/capabilities.json), [`state.json`](950011559/state.json) |
| `950011605` | Electrolux | Comfort 600 | EXP34U339HW | White | Portable air conditioner | Reference mapping | [`capabilities.json`](950011605/capabilities.json), [`state.json`](950011605/state.json) |
