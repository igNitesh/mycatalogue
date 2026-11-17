import pytest

from apps.products.exceptions import InvalidProductAttributeError
from apps.products.validators import validate_attributes


class TestProductAttributeValidation:
    """Verifies custom product attribute dictionary rules and XSS/malformation protections."""

    def test_valid_custom_attributes(self):
        valid_data = {
            "Brand": "FabIndia",
            "Fabric": "100% Khadi Cotton",
            "Fit": "Regular",
            "Sizes Available": "S, M, L, XL",
            "Warranty (Years)": 2,
            "Discount %": 15.5,
            "Is Handmade": True,
            "रंग": "नीला",  # Multilingual support
            "Weight (kg)": 0.45,
        }
        cleaned = validate_attributes(valid_data)
        assert cleaned["Brand"] == "FabIndia"
        assert cleaned["Warranty (Years)"] == 2
        assert cleaned["Is Handmade"] is True
        assert cleaned["रंग"] == "नीला"

    def test_empty_or_none_attributes_valid(self):
        assert validate_attributes(None) == {}
        assert validate_attributes({}) == {}

    def test_non_dict_attributes_rejected(self):
        with pytest.raises(InvalidProductAttributeError, match="must be provided as a dictionary"):
            validate_attributes(["Brand", "Size"])

        with pytest.raises(InvalidProductAttributeError, match="must be provided as a dictionary"):
            validate_attributes("Brand: Nike")

    def test_exceeding_max_20_attributes_rejected(self):
        oversized_dict = {f"Key_{i}": f"Value_{i}" for i in range(21)}
        with pytest.raises(InvalidProductAttributeError, match="more than 20 custom attributes"):
            validate_attributes(oversized_dict)

    def test_empty_or_oversized_key_rejected(self):
        # Empty key
        with pytest.raises(InvalidProductAttributeError, match="between 1 and 50 characters"):
            validate_attributes({"": "Value"})

        with pytest.raises(InvalidProductAttributeError, match="between 1 and 50 characters"):
            validate_attributes({"   ": "Value"})

        # Key > 50 characters
        long_key = "a" * 51
        with pytest.raises(InvalidProductAttributeError, match="between 1 and 50 characters"):
            validate_attributes({long_key: "Value"})

    def test_control_character_in_key_rejected(self):
        with pytest.raises(InvalidProductAttributeError, match="forbidden control characters"):
            validate_attributes({"Brand\x00Name": "Value"})

        with pytest.raises(InvalidProductAttributeError, match="forbidden control characters"):
            validate_attributes({"Fabric\x1f": "Cotton"})

    def test_nested_collections_and_nulls_rejected(self):
        # Nested dict
        with pytest.raises(InvalidProductAttributeError, match="must be a scalar"):
            validate_attributes({"Specs": {"RAM": "8GB"}})

        # Nested list
        with pytest.raises(InvalidProductAttributeError, match="must be a scalar"):
            validate_attributes({"Colors": ["Red", "Blue"]})

        # Null value
        with pytest.raises(InvalidProductAttributeError, match="must be a scalar"):
            validate_attributes({"Brand": None})

    def test_oversized_string_value_rejected(self):
        long_val = "x" * 256
        with pytest.raises(InvalidProductAttributeError, match="maximum length of 255"):
            validate_attributes({"Description": long_val})

    def test_control_character_in_value_rejected(self):
        with pytest.raises(InvalidProductAttributeError, match="forbidden control characters"):
            validate_attributes({"Color": "Red\x00Bad"})

    def test_oversized_total_payload_rejected(self):
        # Create 20 keys with long allowed string values whose total JSON exceeds 10 KB
        # 20 keys * (50 + 255) = ~6.1 KB normally, but let's test a payload constructed to exceed 10 KB
        # E.g. with unicode or if individual entries push total length beyond 10240 bytes

        # 20 * 250 is ~5 KB. Let's make sure our validator checks MAX_ATTRIBUTE_SERIALIZED_BYTES
        # We can test by directly providing a dict where serialized bytes > 10240
        # Wait, 20 * 250 is 5000 bytes. With 4-byte unicode characters (e.g. 250 emojis per value):
        # 20 * 250 * 4 bytes = 20,000 bytes > 10 KB!
        unicode_payload = {f"Key_{i:02d}": "🎉" * 200 for i in range(20)}
        with pytest.raises(InvalidProductAttributeError, match="exceeds the 10 KB limit"):
            validate_attributes(unicode_payload)

    def test_legacy_key_collision_rejected(self):
        with pytest.raises(
            InvalidProductAttributeError, match="Duplicate attribute key after normalization"
        ):
            validate_attributes({"Fabric": "Silk", "fabric": "Cotton"})

    def test_valid_structured_specifications(self):
        payload = {
            "specifications": [
                {
                    "key": "fabric",
                    "label": "Fabric Material",
                    "type": "single_select",
                    "options": ["Pure Silk", "Organic Linen", "Cotton"],
                    "value": "Pure Silk",
                },
                {
                    "key": "sizes",
                    "label": "Available Sizes",
                    "type": "multi_select",
                    "options": ["S", "M", "L", "XL"],
                    "values": ["S", "M"],
                },
                {
                    "key": "colors",
                    "label": "Color Palette",
                    "type": "color",
                    "values": [
                        {"name": "Midnight Blue", "hex": "#191970"},
                        {"name": "Olive", "hex": "#556b2f"},
                    ],
                },
                {
                    "key": "thread_count",
                    "label": "Thread Count",
                    "type": "number",
                    "value": 400,
                    "unit": "TC",
                },
                {
                    "key": "care_instructions",
                    "label": "Care Instructions",
                    "type": "text",
                    "value": "Dry clean only.",
                },
            ]
        }
        cleaned = validate_attributes(payload)
        assert len(cleaned["specifications"]) == 5
        assert cleaned["specifications"][0]["key"] == "fabric"
        assert cleaned["specifications"][0]["value"] == "Pure Silk"
        assert cleaned["specifications"][1]["values"] == ["S", "M"]
        assert cleaned["specifications"][2]["values"][0]["hex"] == "#191970"
        assert cleaned["specifications"][3]["value"] == 400
        assert cleaned["specifications"][3]["unit"] == "TC"

    def test_structured_specifications_exceeding_15_rejected(self):
        specs = [
            {"key": f"spec_{i:02d}", "label": f"Spec {i}", "type": "text", "value": "Val"}
            for i in range(16)
        ]
        with pytest.raises(
            InvalidProductAttributeError, match="more than 15 custom specifications"
        ):
            validate_attributes({"specifications": specs})

    def test_structured_duplicate_keys_rejected(self):
        payload = {
            "specifications": [
                {"key": "fabric", "label": "Fabric", "type": "text", "value": "Silk"},
                {"key": "fabric", "label": "Fabric Second", "type": "text", "value": "Cotton"},
            ]
        }
        with pytest.raises(
            InvalidProductAttributeError, match="Duplicate specification key 'fabric'"
        ):
            validate_attributes(payload)

    def test_structured_unknown_type_rejected(self):
        payload = {
            "specifications": [
                {"key": "custom", "label": "Custom", "type": "invalid_type", "value": "foo"}
            ]
        }
        with pytest.raises(InvalidProductAttributeError, match="invalid type 'invalid_type'"):
            validate_attributes(payload)

    def test_structured_unauthorized_fields_rejected(self):
        payload = {
            "specifications": [
                {
                    "key": "fabric",
                    "label": "Fabric",
                    "type": "text",
                    "value": "Silk",
                    "extra_field": "disallowed",
                }
            ]
        }
        with pytest.raises(
            InvalidProductAttributeError, match="unauthorized fields for type 'text'"
        ):
            validate_attributes(payload)

    def test_single_select_membership_validation(self):
        payload = {
            "specifications": [
                {
                    "key": "fabric",
                    "label": "Fabric",
                    "type": "single_select",
                    "options": ["Silk", "Cotton"],
                    "value": "Polyester",  # Not in options
                }
            ]
        }
        with pytest.raises(InvalidProductAttributeError, match="is not in allowed options"):
            validate_attributes(payload)

    def test_multi_select_membership_and_duplicate_validation(self):
        # Value not in options
        payload_invalid_val = {
            "specifications": [
                {
                    "key": "sizes",
                    "label": "Sizes",
                    "type": "multi_select",
                    "options": ["S", "M", "L"],
                    "values": ["S", "XXL"],
                }
            ]
        }
        with pytest.raises(InvalidProductAttributeError, match="is not in allowed options"):
            validate_attributes(payload_invalid_val)

        # Duplicate values in selected list
        payload_dup_val = {
            "specifications": [
                {
                    "key": "sizes",
                    "label": "Sizes",
                    "type": "multi_select",
                    "options": ["S", "M", "L"],
                    "values": ["S", "S"],
                }
            ]
        }
        with pytest.raises(InvalidProductAttributeError, match="Duplicate selected value 'S'"):
            validate_attributes(payload_dup_val)

    def test_number_boolean_and_finite_rejection(self):
        # In Python, bool is subclass of int. Reject bool!
        payload_bool = {
            "specifications": [
                {"key": "weight", "label": "Weight", "type": "number", "value": True}
            ]
        }
        with pytest.raises(InvalidProductAttributeError, match="not boolean or string"):
            validate_attributes(payload_bool)

        # Non-numeric string
        payload_str = {
            "specifications": [
                {"key": "weight", "label": "Weight", "type": "number", "value": "100"}
            ]
        }
        with pytest.raises(InvalidProductAttributeError, match="not boolean or string"):
            validate_attributes(payload_str)

    def test_color_validation(self):
        # Invalid hex
        payload_bad_hex = {
            "specifications": [
                {
                    "key": "colors",
                    "label": "Colors",
                    "type": "color",
                    "values": [{"name": "Blue", "hex": "blue"}],
                }
            ]
        }
        with pytest.raises(InvalidProductAttributeError, match="valid 6-character hex code"):
            validate_attributes(payload_bad_hex)

        # Duplicate color hex
        payload_dup_hex = {
            "specifications": [
                {
                    "key": "colors",
                    "label": "Colors",
                    "type": "color",
                    "values": [
                        {"name": "Blue 1", "hex": "#191970"},
                        {"name": "Blue 2", "hex": "#191970"},
                    ],
                }
            ]
        }
        with pytest.raises(InvalidProductAttributeError, match="Duplicate color hex"):
            validate_attributes(payload_dup_hex)
