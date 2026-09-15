import copy
import tempfile
import unittest
from pathlib import Path

from scripts.validate_catalog import CatalogValidationError, validate_document, validate_file


class CatalogValidatorTests(unittest.TestCase):
    def setUp(self):
        self.document = {
            "schemaVersion": 2,
            "catalogVersion": "test-1",
            "entries": [{
                "id": "homey.vendor.switch.power",
                "match": {
                    "provider": "homey",
                    "driverID": "homey:app:vendor:switch",
                    "nativeIdentifier": "switch.1",
                },
                "resolution": {
                    "kind": "power", "component": "primary",
                    "displayName": "Switch 1", "readable": True, "writable": True,
                },
            }],
        }

    def assert_invalid(self, mutate):
        document = copy.deepcopy(self.document)
        mutate(document)
        with self.assertRaises(CatalogValidationError):
            validate_document(document)

    def test_accepts_schema_2_catalog(self):
        validate_document(self.document)

    def test_accepts_home_assistant_raw_read_only_classification(self):
        validate_document(self._ha_raw_document())

    def test_accepts_empty_bootstrap(self):
        validate_document({"schemaVersion": 2, "catalogVersion": "bootstrap-1", "entries": []})

    def test_rejects_schema_1_and_3(self):
        for version in (1, 3):
            with self.subTest(version=version):
                self.assert_invalid(lambda d, v=version: d.update(schemaVersion=v))

    def test_rejects_unknown_fields_at_every_level(self):
        mutations = [
            lambda d: d.update(unexpected=True),
            lambda d: d["entries"][0].update(unexpected=True),
            lambda d: d["entries"][0]["match"].update(unexpected=True),
            lambda d: d["entries"][0]["resolution"].update(unexpected=True),
            lambda d: d["entries"][0]["resolution"].update(
                constraints={"minimum": 0, "unexpected": True}
            ),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.assert_invalid(mutation)

    def test_rejects_unknown_enums_and_kinds(self):
        mutations = [
            lambda d: d["entries"][0]["match"].update(provider="futureProvider"),
            lambda d: d["entries"][0]["match"].update(capabilityKind="futureKind"),
            lambda d: d["entries"][0]["resolution"].update(kind="futureKind"),
            lambda d: d["entries"][0]["resolution"].update(component="futureComponent"),
            lambda d: d["entries"][0]["resolution"].update(role="futureRole"),
            lambda d: d["entries"][0]["resolution"].update(runtimeModeOverride="futureMode"),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.assert_invalid(mutation)

    def test_rejects_unknown_device_kind_hint(self):
        self.assert_invalid(
            lambda d: d["entries"][0]["resolution"].update(deviceKindHint="unknown")
        )

    def test_rejects_duplicate_ids(self):
        self.assert_invalid(lambda d: d["entries"].append(copy.deepcopy(d["entries"][0])))

    def test_rejects_invalid_home_assistant_raw_data(self):
        forbidden = {
            "writable": True, "attributeKey": "other", "serviceDomain": "sensor",
            "serviceName": "turn_on", "commandMapping": {"on": "turn_on"},
            "runtimeModeOverride": "realtime",
        }
        for field, value in forbidden.items():
            with self.subTest(field=field):
                document = self._ha_raw_document()
                document["entries"][0]["resolution"][field] = value
                with self.assertRaises(CatalogValidationError):
                    validate_document(document)

    def test_rejects_raw_vocabulary_for_non_home_assistant(self):
        document = self._ha_raw_document()
        document["entries"][0]["match"]["provider"] = "homey"
        with self.assertRaises(CatalogValidationError):
            validate_document(document)

    def test_rejects_classification_without_unknown_source_kind(self):
        document = self._ha_raw_document()
        document["entries"][0]["match"]["capabilityKind"] = "humidity"
        with self.assertRaises(CatalogValidationError):
            validate_document(document)

    def test_rejects_empty_command_mapping_and_values(self):
        for mapping in ({}, {"": "on"}, {"on": "  "}):
            with self.subTest(mapping=mapping):
                self.assert_invalid(
                    lambda d, m=mapping: d["entries"][0]["resolution"].update(commandMapping=m)
                )

    def test_rejects_empty_allowed_value(self):
        self.assert_invalid(
            lambda d: d["entries"][0]["resolution"].update(
                constraints={"allowedValues": ["on", " "]}
            )
        )

    def test_rejects_invalid_types(self):
        mutations = [
            lambda d: d.update(schemaVersion=True),
            lambda d: d.update(entries={}),
            lambda d: d["entries"][0]["resolution"].update(readable="true"),
            lambda d: d["entries"][0]["resolution"].update(constraints={"minimum": "zero"}),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.assert_invalid(mutation)

    def test_rejects_oversized_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(" " * 1_048_577, encoding="utf-8")
            with self.assertRaises(CatalogValidationError):
                validate_file(path)

    def test_rejects_too_many_entries(self):
        self.assert_invalid(
            lambda d: d.update(entries=[copy.deepcopy(d["entries"][0])] * 10_001)
        )

    def test_rejects_invalid_json_duplicate_keys_and_non_finite_numbers(self):
        documents = (
            "not json",
            '{"schemaVersion":2,"schemaVersion":2,"catalogVersion":"x","entries":[]}',
            '{"schemaVersion":2,"catalogVersion":"x","entries":[],"number":NaN}',
        )
        for content in documents:
            with self.subTest(content=content):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "catalog.json"
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaises(CatalogValidationError):
                        validate_file(path)

    def test_rejects_lone_high_surrogate(self):
        self.assert_json_invalid(
            r'{"schemaVersion":2,"catalogVersion":"\ud800","entries":[]}'
        )

    def test_rejects_lone_low_surrogate(self):
        self.assert_json_invalid(
            r'{"schemaVersion":2,"catalogVersion":"\udc00","entries":[]}'
        )

    def test_rejects_surrogate_in_nested_string(self):
        document = copy.deepcopy(self.document)
        document["entries"][0]["resolution"]["displayName"] = "\ud800"
        with self.assertRaises(CatalogValidationError):
            validate_document(document)

    def test_rejects_surrogate_in_object_key(self):
        document = copy.deepcopy(self.document)
        document["entries"][0]["resolution"]["commandMapping"] = {"\udc00": "on"}
        with self.assertRaises(CatalogValidationError):
            validate_document(document)

    def test_accepts_normal_unicode(self):
        document = copy.deepcopy(self.document)
        document["catalogVersion"] = "Grüße-日本語"
        document["entries"][0]["resolution"]["displayName"] = "Licht 💡"
        validate_document(document)

    def test_accepts_valid_supplementary_unicode_and_surrogate_pair(self):
        self.assert_json_valid(
            r'{"schemaVersion":2,"catalogVersion":"rocket-\ud83d\ude80","entries":[]}'
        )

    @staticmethod
    def _ha_raw_document():
        return {
            "schemaVersion": 2,
            "catalogVersion": "ha-test-1",
            "entries": [{
                "id": "ha.sensor.power-w",
                "match": {
                    "provider": "homeAssistant", "domain": "sensor",
                    "sourceIdentifier": "state", "capabilityKind": "unknown",
                    "unitOfMeasurement": "W",
                },
                "resolution": {
                    "kind": "powerMeasurement", "component": "energy", "readable": True,
                },
            }],
        }

    def assert_json_invalid(self, content):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(content, encoding="utf-8")
            with self.assertRaises(CatalogValidationError):
                validate_file(path)

    def assert_json_valid(self, content):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(content, encoding="utf-8")
            validate_file(path)


if __name__ == "__main__":
    unittest.main()
