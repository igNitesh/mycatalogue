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
