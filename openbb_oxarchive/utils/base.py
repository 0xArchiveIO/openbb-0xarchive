"""Base data model shared by every 0xArchive dataset."""

from typing import Any

from openbb_core.provider.abstract.data import Data
from pydantic import model_validator


class OxarchiveData(Data):
    """Rows keep every field the API returns; declared fields are typed."""

    @model_validator(mode="before")
    @classmethod
    def _blank_is_none(cls, values: Any) -> Any:
        """Read empty strings as missing, and drop numbers the API sent as text that do not parse."""
        if not isinstance(values, dict):
            return values
        fields = cls.model_fields
        clean = {}
        for name, value in values.items():
            if value == "":
                value = None
            field = fields.get(name)
            if field is not None and isinstance(value, str) and "float" in str(field.annotation):
                try:
                    value = float(value)
                except ValueError:
                    value = None
            clean[name] = value
        return clean
