#!/usr/bin/env python3
"""Fail-closed validator for Mikonus Schema-2 capability catalogs."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, NoReturn

SCHEMA_VERSION = 2
MAX_FILE_SIZE = 1_048_576
MAX_ENTRY_COUNT = 10_000

ROOT_FIELDS = {"schemaVersion", "catalogVersion", "entries"}
ENTRY_FIELDS = {"id", "match", "resolution"}
MATCH_FIELDS = {
    "provider", "providerDeviceID", "driverID", "integration", "entityID",
    "domain", "deviceClass", "nativeIdentifier", "sourceIdentifier",
    "capabilityKind", "attributeKey", "unitOfMeasurement",
}
RESOLUTION_FIELDS = {
    "deviceHint", "deviceKindHint", "kind", "component", "componentName",
    "role", "displayName", "readable", "writable", "attributeKey",
    "serviceDomain", "serviceName", "commandMapping", "constraints",
    "runtimeModeOverride",
}
CONSTRAINT_FIELDS = {
    "minimum", "maximum", "step", "allowedValues", "unitOfMeasurement",
}
PROVIDERS = {"homeAssistant", "homey", "hue", "homeKit", "matter", "mqtt", "demo"}
DEVICE_HINTS = {
    "light", "blind", "vacuum", "switchDevice", "sensor", "temperature",
    "climate", "camera", "mediaPlayer", "door", "lock", "unknown",
}
DEVICE_KIND_HINTS = {
    "light", "ceilingFan", "standingFan", "airConditioner", "heatPump",
    "radiatorThermostat", "floorHeating", "ventilationSystem", "airPurifier",
    "humidifier", "dehumidifier", "waterHeater", "extractorHood", "poolPump",
    "poolHeater", "sprinkler", "irrigationZone", "gardenPump", "pondFilter",
    "lawnMower", "solarPanel", "inverter", "batteryStorage", "wallbox",
    "blind", "shutter", "awning", "garageDoor", "gate", "window", "door",
    "lock", "thermostat", "oven", "dishwasher", "washingMachine", "dryer",
    "refrigerator", "freezer", "vacuum", "coffeeMachine", "mediaPlayer",
    "camera", "motionSensor", "occupancySensor", "smokeDetector",
    "waterLeakSensor", "alarmSystem", "doorbell", "mailbox",
    "temperatureSensor", "humiditySensor", "powerMeter", "genericSwitch", "unknown",
}
CAPABILITY_KINDS = {
    "availability", "fault", "power", "brightness", "colorTemperature", "color",
    "effect", "fanSpeed", "fanDirection", "oscillation", "targetTemperature",
    "targetHumidity", "currentTemperature", "hvacMode", "hvacAction", "fanMode",
    "presetMode", "swingMode", "position", "tiltPosition", "coverMovement",
    "openState", "lockState", "startStop", "returnToBase", "cleaningState",
    "cleaningMode", "chargingState", "progress", "consumableLevel",
    "powerMeasurement", "energyMeasurement", "storedEnergy", "waterConsumption",
    "gasConsumption", "coefficientOfPerformance", "batteryLevel", "humidity",
    "illuminance", "airQuality", "co2", "pressure", "voltage", "current",
    "signalStrength", "waterFlow", "waterTemperature", "alarm", "securityMode",
    "waterLeak", "smokeAlarm", "motion", "occupancy", "mediaPlaybackState",
    "mediaTransport", "volume", "mute", "mediaSource", "mediaTitle",
    "mediaArtist", "mediaContent", "cameraSnapshot", "cameraStream", "unknown",
}
COMPONENTS = {
    "primary", "light", "fan", "heating", "cooling", "ventilation", "battery",
    "energy", "custom",
}
ROLES = {
    "room", "outdoor", "flow", "returnFlow", "target", "water", "consumption",
    "production", "gridImport", "gridExport", "battery", "grid", "solar",
    "vehicle", "charging", "discharging", "input", "output", "filter",
    "dustBag", "waterTank", "detergent", "brush", "primary", "secondary",
    "diagnostic", "unknown",
}
RUNTIME_MODES = {"realtime", "interactive", "onDemand", "historical", "ignored"}


class CatalogValidationError(ValueError):
    pass


def fail(path: str, message: str) -> NoReturn:
    raise CatalogValidationError(f"{path}: {message}")


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            fail("$", f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def reject_non_finite_number(value: str) -> NoReturn:
    fail("$", f"non-finite JSON number {value!r} is not allowed")


def require_object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(path, "must be an object")
    return value


def require_only_fields(value: dict[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        fail(f"{path}.{unknown[0]}", "unsupported field")


def require_fields(value: dict[str, Any], required: set[str], path: str) -> None:
    missing = sorted(required - set(value))
    if missing:
        fail(f"{path}.{missing[0]}", "missing required field")


def non_empty_string(value: Any, path: str) -> str:
    if not isinstance(value, str):
        fail(path, "must be a string")
    if not value.strip():
        fail(path, "must not be empty")
    return value


def optional_string(value: dict[str, Any], field: str, path: str) -> str | None:
    raw = value.get(field)
    if raw is None:
        return None
    return non_empty_string(raw, f"{path}.{field}")


def optional_enum(value: dict[str, Any], field: str, allowed: set[str], path: str) -> str | None:
    raw = optional_string(value, field, path)
    if raw is not None and raw not in allowed:
        fail(f"{path}.{field}", f"unsupported value {raw!r}")
    return raw


def optional_bool(value: dict[str, Any], field: str, path: str) -> None:
    raw = value.get(field)
    if raw is not None and type(raw) is not bool:
        fail(f"{path}.{field}", "must be a boolean")


def validate_constraints(raw: Any, path: str) -> None:
    constraints = require_object(raw, path)
    require_only_fields(constraints, CONSTRAINT_FIELDS, path)
    for field in ("minimum", "maximum", "step"):
        value = constraints.get(field)
        if value is not None and (
            type(value) not in (int, float) or not math.isfinite(value)
        ):
            fail(f"{path}.{field}", "must be a finite number")
    optional_string(constraints, "unitOfMeasurement", path)
    allowed_values = constraints.get("allowedValues")
    if allowed_values is not None:
        if not isinstance(allowed_values, list):
            fail(f"{path}.allowedValues", "must be an array")
        for index, value in enumerate(allowed_values):
            non_empty_string(value, f"{path}.allowedValues[{index}]")


def validate_match(raw: Any, path: str) -> dict[str, Any]:
    match = require_object(raw, path)
    require_only_fields(match, MATCH_FIELDS, path)
    provider = optional_enum(match, "provider", PROVIDERS, path)
    if provider is None:
        fail(f"{path}.provider", "missing required field")
    for field in MATCH_FIELDS - {"provider", "capabilityKind"}:
        optional_string(match, field, path)
    optional_enum(match, "capabilityKind", CAPABILITY_KINDS, path)
    if not any(match.get(field) is not None for field in MATCH_FIELDS - {"provider"}):
        fail(path, "match must contain at least one selector")
    return match


def validate_resolution(raw: Any, match: dict[str, Any], path: str) -> None:
    resolution = require_object(raw, path)
    require_only_fields(resolution, RESOLUTION_FIELDS, path)
    for field in ("componentName", "displayName", "attributeKey", "serviceDomain", "serviceName"):
        optional_string(resolution, field, path)
    optional_enum(resolution, "deviceHint", DEVICE_HINTS, path)
    device_kind = optional_enum(resolution, "deviceKindHint", DEVICE_KIND_HINTS, path)
    if device_kind == "unknown":
        fail(f"{path}.deviceKindHint", "must not resolve to unknown")
    kind = optional_enum(resolution, "kind", CAPABILITY_KINDS, path)
    if kind == "unknown":
        fail(f"{path}.kind", "must not resolve to unknown")
    if kind is not None and match.get("capabilityKind") not in (None, "unknown"):
        fail(f"{path}.kind", "classification requires capabilityKind 'unknown'")
    optional_enum(resolution, "component", COMPONENTS, path)
    optional_enum(resolution, "role", ROLES, path)
    optional_enum(resolution, "runtimeModeOverride", RUNTIME_MODES, path)
    optional_bool(resolution, "readable", path)
    optional_bool(resolution, "writable", path)

    if resolution.get("commandMapping") is not None:
        mapping = require_object(resolution["commandMapping"], f"{path}.commandMapping")
        if not mapping:
            fail(f"{path}.commandMapping", "must not be empty")
        for key, value in mapping.items():
            non_empty_string(key, f"{path}.commandMapping key")
            non_empty_string(value, f"{path}.commandMapping.{key}")
    if resolution.get("constraints") is not None:
        validate_constraints(resolution["constraints"], f"{path}.constraints")

    raw_fields = {"sourceIdentifier", "capabilityKind", "attributeKey", "unitOfMeasurement"}
    uses_raw_classification = (
        any(match.get(field) is not None for field in raw_fields)
        or resolution.get("deviceKindHint") is not None
    )
    if uses_raw_classification:
        if match["provider"] != "homeAssistant":
            fail(path, "raw classification fields are Home Assistant-only")
        forbidden = (
            "deviceHint", "writable", "attributeKey", "serviceDomain", "serviceName",
            "commandMapping", "runtimeModeOverride",
        )
        for field in forbidden:
            if resolution.get(field) is not None:
                fail(f"{path}.{field}", "not allowed for Home Assistant raw classification")
        if kind is not None and match.get("capabilityKind") != "unknown":
            fail(f"{path}.kind", "classification requires capabilityKind 'unknown'")
    if not any(value is not None for value in resolution.values()):
        fail(path, "resolution must not be empty")


def validate_document(document: Any) -> None:
    root = require_object(document, "$")
    require_only_fields(root, ROOT_FIELDS, "$")
    require_fields(root, ROOT_FIELDS, "$")
    if type(root["schemaVersion"]) is not int:
        fail("$.schemaVersion", "must be an integer")
    if root["schemaVersion"] != SCHEMA_VERSION:
        fail("$.schemaVersion", f"must be exactly {SCHEMA_VERSION}")
    non_empty_string(root["catalogVersion"], "$.catalogVersion")
    entries = root["entries"]
    if not isinstance(entries, list):
        fail("$.entries", "must be an array")
    if len(entries) > MAX_ENTRY_COUNT:
        fail("$.entries", f"must contain at most {MAX_ENTRY_COUNT} entries")
    rule_ids: set[str] = set()
    for index, raw_entry in enumerate(entries):
        path = f"$.entries[{index}]"
        entry = require_object(raw_entry, path)
        require_only_fields(entry, ENTRY_FIELDS, path)
        require_fields(entry, ENTRY_FIELDS, path)
        rule_id = non_empty_string(entry["id"], f"{path}.id")
        if rule_id in rule_ids:
            fail(f"{path}.id", f"duplicate rule ID {rule_id!r}")
        rule_ids.add(rule_id)
        match = validate_match(entry["match"], f"{path}.match")
        validate_resolution(entry["resolution"], match, f"{path}.resolution")


def validate_file(path: Path) -> None:
    try:
        size = path.stat().st_size
    except OSError as error:
        raise CatalogValidationError(f"{path}: {error}") from error
    if size > MAX_FILE_SIZE:
        raise CatalogValidationError(f"{path}: exceeds maximum size of {MAX_FILE_SIZE} bytes")
    try:
        with path.open("r", encoding="utf-8") as source:
            document = json.load(
                source,
                object_pairs_hook=reject_duplicate_keys,
                parse_constant=reject_non_finite_number,
            )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CatalogValidationError(f"{path}: invalid JSON: {error}") from error
    validate_document(document)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalogs", nargs="+", type=Path)
    args = parser.parse_args()
    failed = False
    for path in args.catalogs:
        try:
            validate_file(path)
            print(f"VALID: {path}")
        except CatalogValidationError as error:
            failed = True
            print(f"INVALID: {error}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
