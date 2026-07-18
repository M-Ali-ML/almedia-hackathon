"""Fuzzy table/column resolution for the check library.

The final judging dossier will have the same *shape* as the sample (GDPdU
export of a German mid-size company) but possibly different file and table
names. Checks therefore never hardcode table names; they ask the resolver for
a logical role ("the AP postings table", "the goods receipt list") which is
matched by column signature first and table-name hints second.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import duckdb

INTERNAL_TABLES = {"documents", "document_texts"}


@dataclass
class ResolvedTable:
    name: str
    columns: list[str]

    def col(self, *patterns: str) -> str | None:
        """First column matching any pattern, tried in pattern order."""
        for pattern in patterns:
            rx = re.compile(pattern, re.IGNORECASE)
            for column in self.columns:
                if column != "_row_id" and rx.search(column):
                    return column
        return None


@dataclass
class RoleSpec:
    """A logical table role.

    ``signature`` is a list of concept groups; a table qualifies only if every
    group is matched by at least one of its columns (any regex in the group).
    ``hints`` are regexes on the table name used for ranking among qualifying
    tables. ``name_required`` marks roles that can only be found by name
    (e.g. spreadsheet matrices whose columns are unnamed).
    """

    signature: list[list[str]] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)
    name_required: bool = False


ROLES: dict[str, RoleSpec] = {
    "vendor_master": RoleSpec(
        signature=[
            [r"lieferant|kreditor|vendor"],
            [r"ustid|ust_id|vat|strasse|street|plz|zip"],
            [r"name"],
        ],
        hints=[r"lieferant", r"kreditor", r"vendor"],
    ),
    "ap_postings": RoleSpec(
        signature=[
            [r"(lieferant|kreditor|vendor).*(konto|nummer|nr)", r"^(lieferant|kreditor|vendor)$"],
            [r"buchungs(wert|betrag)", r"betrag|amount"],
            [r"(buchungs|beleg)datum", r"datum|date"],
            [r"buchungstext|text"],
        ],
        hints=[r"lieferant|kreditor|vendor", r"buchung"],
    ),
    "goods_receipts": RoleSpec(
        signature=[
            [r"wareneingang|goods_?receipt"],
            [r"kreditor|lieferant|vendor"],
        ],
        hints=[r"wareneingang|goods_?receipt"],
    ),
    "masterdata_changes": RoleSpec(
        signature=[
            [r"(geaendert|ge.ndert|angelegt|erfasst)_?von", r"^ersteller$", r"created_by"],
            [r"(genehmigt|freigegeben|approved)_?von", r"^freigeber$", r"approved_by"],
        ],
        hints=[r"stammdaten|aenderung|.nderung|change"],
    ),
    "approval_log": RoleSpec(
        signature=[
            [r"^ersteller$", r"(erfasst|angelegt)_?von", r"created_by"],
            [r"^freigeber$", r"(genehmigt|freigegeben)_?von", r"approved_by"],
        ],
        hints=[r"freigabe|journal|log"],
    ),
    "permissions": RoleSpec(
        # xlsx matrix with decorative header rows: columns are unnamed, so the
        # role is resolvable by table name only; parsing happens in the check.
        signature=[],
        hints=[r"berechtigung|permission|rollen|access"],
        name_required=True,
    ),
    "assets": RoleSpec(
        signature=[
            [r"anlage.*(nummer|nr)", r"asset.*(number|nr|id)"],
            [r"bezeichnung|name|description"],
        ],
        hints=[r"anlagen|asset"],
    ),
    "asset_postings": RoleSpec(
        signature=[
            [r"anlage.*(nummer|nr)", r"asset.*(number|nr|id)"],
            [r"buchungs(wert|betrag)", r"betrag|amount"],
            [r"buchungs(art|typ)", r"bewegungsart"],
        ],
        hints=[r"buchung|posting|bewegung"],
    ),
    "gl_accounts": RoleSpec(
        signature=[
            [r"sachkonto.*(nummer|nr)", r"^konto(nummer|nr)?$"],
            [r"name|bezeichnung"],
        ],
        hints=[r"sachkonten|kontenplan|chart"],
    ),
    "gl_postings": RoleSpec(
        signature=[
            [r"sachkonto", r"hauptbuch", r"^konto(nummer|nr)?$"],
            [r"buchungs(typ|art)"],
            [r"buchungs(wert|betrag)", r"betrag|amount"],
            [r"buchungsdatum"],
        ],
        hints=[r"sachkonto|hauptbuch|journal|ledger"],
    ),
    "next_period_ap_invoices": RoleSpec(
        signature=[
            [r"faktura.*datum|rechnungsdatum|invoice_?date"],
            [r"leistungsdatum|service_?date|lieferdatum"],
            [r"kreditor|lieferant|vendor"],
        ],
        hints=[r"folgeperiode|januar|jan_|next"],
    ),
}


class Resolver:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        rows = con.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "ORDER BY table_name, ordinal_position"
        ).fetchall()
        self.tables: dict[str, list[str]] = {}
        for table, column in rows:
            if table in INTERNAL_TABLES:
                continue
            self.tables.setdefault(table, []).append(column)
        self._cache: dict[str, ResolvedTable | None] = {}

    def resolve(self, role: str) -> ResolvedTable | None:
        if role in self._cache:
            return self._cache[role]
        spec = ROLES[role]
        best: ResolvedTable | None = None
        best_score = 0
        for table, columns in self.tables.items():
            lowered = [c.lower() for c in columns]
            groups_ok = all(
                any(re.search(p, c) for p in group for c in lowered)
                for group in spec.signature
            )
            if not groups_ok:
                continue
            hint_score = sum(1 for h in spec.hints if re.search(h, table, re.IGNORECASE))
            if spec.name_required and hint_score == 0:
                continue
            score = 1 + hint_score
            if score > best_score:
                best, best_score = ResolvedTable(table, columns), score
        self._cache[role] = best
        return best

    def describe(self, roles: list[str]) -> list[str]:
        lines = []
        for role in roles:
            resolved = self.resolve(role)
            lines.append(f"{role} -> {resolved.name if resolved else '(not found)'}")
        return lines
