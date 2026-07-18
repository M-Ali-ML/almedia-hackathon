"""Light, deterministic normalization helpers for German-formatted data."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

import pandas as pd

_GERMAN_NUMBER_RE = re.compile(r"^-?\d{1,3}(\.\d{3})*(,\d+)?$|^-?\d+(,\d+)?$")
_GERMAN_DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
_LEADING_ZERO_RE = re.compile(r"^0\d")


def sanitize_identifier(name: str) -> str:
    """Turn an arbitrary name into a safe lowercase SQL identifier."""
    # Transliterate umlauts etc. (PERIODENZUGEHÖRIGKEIT -> periodenzugehorigkeit)
    ascii_name = (
        unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    )
    ident = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_name).strip("_").lower()
    if not ident:
        ident = "col"
    if ident[0].isdigit():
        ident = f"c_{ident}"
    return ident


def dedupe_identifiers(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for n in names:
        if n in seen:
            seen[n] += 1
            out.append(f"{n}_{seen[n]}")
        else:
            seen[n] = 0
            out.append(n)
    return out


def parse_german_number(value: str) -> float:
    return float(value.replace(".", "").replace(",", "."))


def parse_german_date(value: str) -> date:
    return datetime.strptime(value, "%d.%m.%Y").date()


def coerce_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Convert string columns to numbers/dates when *every* non-empty value parses.

    Identifier-like columns with leading zeros (e.g. account '020000') are left
    as strings so joins and citations stay exact.
    """
    for col in df.columns:
        if col == "_row_id":
            continue
        series = df[col]
        if not pd.api.types.is_string_dtype(series) and series.dtype != object:
            continue
        non_empty = series[series.astype(str).str.strip() != ""]
        if non_empty.empty:
            continue
        values = non_empty.astype(str).str.strip()

        if values.str.match(_GERMAN_DATE_RE).all():
            df[col] = series.map(
                lambda v: parse_german_date(v.strip()) if str(v).strip() else None
            )
            continue

        if (
            values.str.match(_GERMAN_NUMBER_RE).all()
            and not values.str.match(_LEADING_ZERO_RE).any()
        ):
            parsed = series.map(
                lambda v: parse_german_number(str(v).strip()) if str(v).strip() else None
            )
            numeric = pd.to_numeric(parsed)
            if numeric.dropna().map(float.is_integer).all():
                numeric = numeric.astype("Int64")
            df[col] = numeric
    return df


def decode_bytes(raw: bytes) -> str:
    """UTF-8 first (with BOM handling), then cp1252/Latin-1 fallback."""
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")
