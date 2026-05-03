from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any


class DeviceType(str, Enum):
    PORTABLE_AIR_CONDITIONER = "PORTABLE_AIR_CONDITIONER"
    AIR_PURIFIER = "AIR_PURIFIER"


class Access(str, Enum):
    READ = "read"
    WRITE = "write"
    READ_WRITE = "readwrite"
    CONSTANT = "constant"

    @classmethod
    def from_string(cls, value: str | None) -> "Access":
        normalized = (value or "read").replace("_", "").replace("-", "").lower()
        if normalized in {"readwrite", "read/write"}:
            return Access.READ_WRITE
        if normalized == "write":
            return Access.WRITE
        if normalized == "constant":
            return Access.CONSTANT
        return Access.READ

    @property
    def can_read(self) -> bool:
        return self in (Access.READ, Access.READ_WRITE, Access.CONSTANT)

    @property
    def can_write(self) -> bool:
        return self in (Access.WRITE, Access.READ_WRITE)


@dataclass(frozen=True)
class Capability:
    path: str
    name: str
    type: str
    access: Access
    min: int | float | None = None
    max: int | float | None = None
    step: int | float | None = None
    disabled: bool = False
    values: tuple[str, ...] = ()
    default: Any = None
    triggers: tuple[dict[str, Any], ...] = ()
    schedulable: bool = False
    raw: dict[str, Any] | None = None

    @property
    def parent_path(self) -> str | None:
        if "." not in self.path:
            return None
        return self.path.rsplit(".", 1)[0]

    @property
    def can_read(self) -> bool:
        return not self.disabled and self.access.can_read

    @property
    def can_write(self) -> bool:
        return not self.disabled and self.access.can_write

    @property
    def is_numeric(self) -> bool:
        return self.type in {"int", "number", "temperature"}


Capabilities = dict[str, Capability]


@dataclass
class ApplianceInfoValue:
    serial_number: str | None
    pnc: str | None
    brand: str | None
    device_type: str
    model: str | None
    variant: str | None
    color: str | None


@dataclass
class ApplianceInfo:
    appliance_info: ApplianceInfoValue
    capabilities: Capabilities
    data_model_version: str | None = None
    raw: dict[str, Any] | None = None

    def capability(self, path: str) -> Capability | None:
        return self.capabilities.get(path)

    def find_capability(
        self,
        *names: str,
        runtime_capabilities: Capabilities | None = None,
    ) -> Capability | None:
        capabilities = runtime_capabilities or self.capabilities
        wanted = {_normalize_name(name) for name in names}
        for capability in capabilities.values():
            if _normalize_name(capability.path) in wanted or _normalize_name(capability.name) in wanted:
                return capability
        return None

    def runtime_capabilities(self, reported_state: dict[str, Any]) -> Capabilities:
        capabilities = {path: replace(capability) for path, capability in self.capabilities.items()}
        for capability in list(capabilities.values()):
            _apply_triggers(capabilities, capability, reported_state)
        return capabilities


def capabilities_from_json(json: dict[str, Any]) -> ApplianceInfo:
    appliance_info_json = json.get("applianceInfo", {})
    capabilities = normalize_capabilities(json.get("capabilities", {}))

    return ApplianceInfo(
        appliance_info=ApplianceInfoValue(
            serial_number=appliance_info_json.get("serialNumber"),
            pnc=appliance_info_json.get("pnc"),
            brand=appliance_info_json.get("brand"),
            device_type=appliance_info_json.get("deviceType") or appliance_info_json.get("applianceType") or "UNKNOWN",
            model=appliance_info_json.get("model"),
            variant=appliance_info_json.get("variant"),
            color=appliance_info_json.get("colour") or appliance_info_json.get("color"),
        ),
        capabilities=capabilities,
        data_model_version=json.get("dataModelVersion"),
        raw=json,
    )


def normalize_capabilities(raw_capabilities: dict[str, Any], parent_path: str | None = None) -> Capabilities:
    capabilities: Capabilities = {}
    for name, raw_capability in raw_capabilities.items():
        if name == "networkInterface" or not isinstance(raw_capability, dict):
            continue

        path = f"{parent_path}.{name}" if parent_path else name
        capability_type = raw_capability.get("type")
        if capability_type in {"object", "complex"} or _looks_like_capability_group(raw_capability):
            nested = {
                child_name: child
                for child_name, child in raw_capability.items()
                if isinstance(child, dict) and child_name not in _CAPABILITY_ATTRIBUTE_NAMES
            }
            capabilities.update(normalize_capabilities(nested, path))
            continue

        capability = _capability_from_json(path, name, raw_capability)
        capabilities[path] = capability

    return capabilities


def command_body_for_capability(
    capability: Capability,
    value: Any,
    *,
    is_dam: bool,
) -> dict[str, Any]:
    if not is_dam:
        return {capability.path: value}

    return {"commands": [_nested_command(capability.path.split("."), value)]}


def resolve_action_path(source: Capability, target_name: str, capabilities: Capabilities) -> str | None:
    if target_name == "self":
        return source.path
    if target_name in capabilities:
        return target_name

    parent_path = source.parent_path
    if parent_path:
        sibling_path = f"{parent_path}.{target_name}"
        if sibling_path in capabilities:
            return sibling_path

    normalized_target = _normalize_name(target_name)
    for path, capability in capabilities.items():
        if _normalize_name(path) == normalized_target or _normalize_name(capability.name) == normalized_target:
            return path
    return None


def _capability_from_json(path: str, name: str, raw_capability: dict[str, Any]) -> Capability:
    raw_values = raw_capability.get("values")
    values: tuple[str, ...]
    if isinstance(raw_values, dict):
        values = tuple(str(value) for value in raw_values)
    elif isinstance(raw_values, list):
        values = tuple(str(value) for value in raw_values)
    else:
        values = ()

    return Capability(
        path=path,
        name=name,
        type=str(raw_capability.get("type", "unknown")).lower(),
        access=Access.from_string(raw_capability.get("access")),
        min=raw_capability.get("min"),
        max=raw_capability.get("max"),
        step=raw_capability.get("step"),
        disabled=bool(raw_capability.get("disabled", False)),
        values=values,
        default=raw_capability.get("default"),
        triggers=tuple(_copy_trigger(trigger) for trigger in raw_capability.get("triggers", []) if isinstance(trigger, dict)),
        schedulable=bool(raw_capability.get("schedulable", False)),
        raw=deepcopy(raw_capability),
    )


def _copy_trigger(trigger: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(trigger)


def _looks_like_capability_group(value: dict[str, Any]) -> bool:
    if "access" in value or "values" in value or "min" in value or "max" in value:
        return False
    return any(isinstance(child, dict) for child in value.values())


def _apply_triggers(capabilities: Capabilities, capability: Capability, reported_state: dict[str, Any]) -> None:
    triggers = list(capability.triggers)
    current_value = get_state_value(reported_state, capability.path)
    raw_values = (capability.raw or {}).get("values")
    if isinstance(raw_values, dict):
        value_config = raw_values.get(str(current_value)) or raw_values.get(_normalize_value(current_value))
        if isinstance(value_config, dict):
            triggers.extend(trigger for trigger in value_config.get("triggers", []) if isinstance(trigger, dict))

    for trigger in triggers:
        condition = trigger.get("condition")
        if condition is not None and not _evaluate_condition(condition, capability, reported_state):
            continue

        action = trigger.get("action")
        if not isinstance(action, dict):
            continue

        for target_name, attrs in action.items():
            if not isinstance(attrs, dict):
                continue
            target_path = resolve_action_path(capability, target_name, capabilities)
            if target_path is None:
                continue
            capabilities[target_path] = _apply_action_attrs(capabilities[target_path], attrs)


def _apply_action_attrs(capability: Capability, attrs: dict[str, Any]) -> Capability:
    changes: dict[str, Any] = {}
    if "disabled" in attrs:
        changes["disabled"] = bool(attrs["disabled"])
    if "access" in attrs:
        changes["access"] = Access.from_string(attrs["access"])
    if "type" in attrs:
        changes["type"] = str(attrs["type"]).lower()
    if "min" in attrs:
        changes["min"] = attrs["min"]
    if "max" in attrs:
        changes["max"] = attrs["max"]
    if "step" in attrs:
        changes["step"] = attrs["step"]
    if "values" in attrs:
        raw_values = attrs["values"]
        if isinstance(raw_values, dict):
            changes["values"] = tuple(str(value) for value in raw_values)
        elif isinstance(raw_values, list):
            changes["values"] = tuple(str(value) for value in raw_values)
    return replace(capability, **changes) if changes else capability


def _evaluate_condition(condition: Any, capability: Capability, reported_state: dict[str, Any]) -> bool:
    if not isinstance(condition, dict):
        return False

    operator = str(condition.get("operator", "eq")).lower()
    if operator in {"and", "or"}:
        left = _evaluate_condition(condition.get("operand_1"), capability, reported_state)
        right = _evaluate_condition(condition.get("operand_2"), capability, reported_state)
        return left and right if operator == "and" else left or right

    left = _condition_operand_value(condition.get("operand_1"), capability, reported_state)
    right = _condition_operand_value(condition.get("operand_2"), capability, reported_state)
    if operator == "ne":
        return _normalize_value(left) != _normalize_value(right)
    return _normalize_value(left) == _normalize_value(right)


def _condition_operand_value(operand: Any, capability: Capability, reported_state: dict[str, Any]) -> Any:
    if isinstance(operand, dict):
        return _evaluate_condition(operand, capability, reported_state)
    if operand == "value":
        return get_state_value(reported_state, capability.path)
    if isinstance(operand, str):
        target_path = operand
        if capability.parent_path and "." not in operand:
            target_path = f"{capability.parent_path}.{operand}"
        value = get_state_value(reported_state, target_path)
        if value is not None:
            return value
    return operand


def get_state_value(reported_state: dict[str, Any], path: str) -> Any:
    current: Any = reported_state
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def set_state_value(reported_state: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = reported_state
    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    current[parts[-1]] = value


def _nested_command(parts: list[str], value: Any) -> dict[str, Any]:
    if len(parts) == 1:
        return {parts[0]: value}
    return {parts[0]: _nested_command(parts[1:], value)}


def _normalize_name(value: str) -> str:
    return value.replace("_", "").replace(".", "").replace("-", "").lower()


def _normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().replace("_", "").replace(" ", "").upper()
    return value


_CAPABILITY_ATTRIBUTE_NAMES = {
    "access",
    "default",
    "disabled",
    "max",
    "min",
    "raw",
    "schedulable",
    "step",
    "triggers",
    "type",
    "values",
}
