"""The deterministic check library — generalizable JET-style probes.

Each check is a plain function over the batch DuckDB that emits *candidates*
with real `_row_id` evidence and computed context. No check decides fraud;
ruling out innocent explanations is the agent/verifier's job. Table and column
names are resolved fuzzily (see resolver.py) so the same checks run on the
unseen final dossier.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable

import duckdb

from .models import CheckHit, CheckResult
from .resolver import ResolvedTable, Resolver

logger = logging.getLogger(__name__)

MAX_HITS = 25
MAX_ROW_IDS = 30

DEFAULT_PARAMS: dict[str, Any] = {
    "approval_limit_eur": 10_000.0,   # overridden by policy from global context when known
    "near_threshold_band": 0.90,      # cluster window: [band*limit, limit)
    "new_vendor_grace_days": 90,      # "mid-year" = first activity this long after FY start
    "new_vendor_min_volume": 25_000.0,
    "round_amount_min": 20_000.0,
    "off_hours_start": 22,
    "off_hours_end": 6,
}

REPAIR_VOCAB = (
    "reparatur|instandsetzung|instandhaltung|austausch|general(ü|ue)berholung|"
    "(ü|ue)berholung|wartung|repair|maintenance|replacement"
)
ACCRUAL_VOCAB = "r(ü|ue)ckstellung|abgrenzung|accrual"
CREATION_VOCAB = "neuanlage|neu[- ]?anlage|angelegt|created"

Check = Callable[[duckdb.DuckDBPyConnection, Resolver, dict[str, Any]], CheckResult]


def _q(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _no_data(check_id: str, title: str, description: str, missing: str) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        title=title,
        description=description,
        status="no_data",
        notes=[f"could not resolve required source: {missing}"],
    )


def _cap_hits(result: CheckResult) -> CheckResult:
    if len(result.hits) > MAX_HITS:
        result.notes.append(f"truncated to top {MAX_HITS} of {len(result.hits)} hits")
        result.hits = result.hits[:MAX_HITS]
    for hit in result.hits:
        if len(hit.row_ids) > MAX_ROW_IDS:
            hit.attributes["row_ids_truncated_from"] = len(hit.row_ids)
            hit.row_ids = hit.row_ids[:MAX_ROW_IDS]
    return result


def _fiscal_year(con: duckdb.DuckDBPyConnection, table: ResolvedTable, date_col: str) -> int:
    row = con.execute(
        f"SELECT year({_q(date_col)}) y, count(*) FROM {_q(table.name)} "
        f"WHERE {_q(date_col)} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 1"
    ).fetchone()
    return int(row[0])


def _ap_columns(ap: ResolvedTable) -> dict[str, str | None]:
    return {
        "vendor": ap.col(
            r"(lieferant|kreditor|vendor).*(konto|nummer|nr)", r"^(lieferant|kreditor|vendor)$"
        ),
        "amount": ap.col(r"buchungswert", r"buchungsbetrag", r"betrag|amount"),
        "date": ap.col(r"buchungsdatum", r"belegdatum", r"datum|date"),
        "text": ap.col(r"buchungstext", r"text"),
    }


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_sod_creator_equals_approver(
    con: duckdb.DuckDBPyConnection, resolver: Resolver, params: dict[str, Any]
) -> CheckResult:
    title = "Creator equals approver (broken four-eyes principle)"
    description = (
        "Master-data changes and journal approvals where the same user both made and "
        "approved the change. Violates segregation of duties regardless of content."
    )
    result = CheckResult(check_id="sod_creator_equals_approver", title=title, description=description)
    found_any_source = False
    for role in ("masterdata_changes", "approval_log"):
        table = resolver.resolve(role)
        if table is None:
            continue
        creator = table.col(r"(geaendert|ge.ndert|angelegt|erfasst)_?von", r"^ersteller$", r"created_by")
        approver = table.col(r"(genehmigt|freigegeben|approved)_?von", r"^freigeber$", r"approved_by")
        if not creator or not approver:
            continue
        found_any_source = True
        result.notes.append(f"{role}: {table.name} ({creator} vs {approver})")
        extra = [
            c
            for c in (
                table.col(r"^datum$", r"datum|date"),
                table.col(r"^art$"),
                table.col(r"konto|account"),
                table.col(r"^name$"),
                table.col(r"^feld$|field"),
                table.col(r"wert_neu|new_value"),
            )
            if c
        ]
        select_extra = (", " + ", ".join(_q(c) for c in extra)) if extra else ""
        rows = con.execute(
            f"SELECT _row_id, {_q(creator)}, {_q(approver)}{select_extra} FROM {_q(table.name)} "
            f"WHERE trim({_q(creator)}) <> '' AND {_q(creator)} = {_q(approver)}"
        ).fetchall()
        for row in rows:
            attributes = {creator: row[1], approver: row[2]}
            attributes.update({col: str(val) for col, val in zip(extra, row[3:])})
            result.hits.append(
                CheckHit(
                    entity=str(row[1]),
                    summary=f"{table.name}: created and approved by the same user {row[1]}",
                    table=table.name,
                    row_ids=[int(row[0])],
                    attributes=attributes,
                )
            )
    if not found_any_source:
        return _no_data(result.check_id, title, description, "masterdata_changes / approval_log")
    return result


def check_permission_concentration(
    con: duckdb.DuckDBPyConnection, resolver: Resolver, params: dict[str, Any]
) -> CheckResult:
    title = "Permission concentration (post + pay + create vendors)"
    description = (
        "Users in the permission matrix who can post, run payments AND create vendor "
        "master data — one person can invent a vendor and pay it end-to-end."
    )
    table = resolver.resolve("permissions")
    if table is None:
        return _no_data("permission_concentration", title, description, "permissions matrix")
    result = CheckResult(check_id="permission_concentration", title=title, description=description)
    result.notes.append(f"permissions: {table.name} (matrix parsed from raw rows)")

    data_cols = [c for c in table.columns if c != "_row_id"]
    rows = con.execute(
        f"SELECT _row_id, {', '.join(_q(c) for c in data_cols)} FROM {_q(table.name)} ORDER BY _row_id"
    ).fetchall()

    right_patterns = {
        "post": r"buchen|posting|^post",
        "approve": r"freigeb|genehmig|approve",
        "pay": r"zahlungslauf|zahlung|payment",
        "create_vendor": r"(kreditor|lieferant|vendor|stammdaten).*(anleg|create)|anleg.*(kreditor|lieferant|vendor)",
        "admin": r"admin",
    }
    header_idx: int | None = None
    user_col: int | None = None
    right_cols: dict[str, int] = {}
    for i, row in enumerate(rows):
        cells = ["" if v is None else str(v).strip() for v in row[1:]]
        lowered = [c.lower() for c in cells]
        if any(re.search(r"benutzer|user", c) for c in lowered) and sum(
            1 for c in lowered for p in right_patterns.values() if c and re.search(p, c)
        ) >= 2:
            header_idx = i
            for j, cell in enumerate(lowered):
                if re.search(r"benutzer|user", cell):
                    user_col = j
                for right, pattern in right_patterns.items():
                    if cell and right not in right_cols and re.search(pattern, cell):
                        right_cols[right] = j
            break
    if header_idx is None or user_col is None:
        result.status = "no_data"
        result.notes.append("could not locate a header row (Benutzer/User + rights) in the matrix")
        return result

    truthy = re.compile(r"^(x+|ja|yes|1|true)$", re.IGNORECASE)
    for row in rows[header_idx + 1 :]:
        cells = ["" if v is None else str(v).strip() for v in row[1:]]
        user = cells[user_col] if user_col < len(cells) else ""
        if not user:
            continue
        rights = sorted(
            right
            for right, j in right_cols.items()
            if j < len(cells) and truthy.match(cells[j])
        )
        if {"post", "pay", "create_vendor"} <= set(rights):
            result.hits.append(
                CheckHit(
                    entity=user,
                    summary=f"user {user} holds posting + payment run + vendor creation rights",
                    table=table.name,
                    row_ids=[int(row[0])],
                    attributes={"rights": rights, "raw_row": [c for c in cells if c]},
                )
            )
    return result


def check_new_vendor_profile(
    con: duckdb.DuckDBPyConnection, resolver: Resolver, params: dict[str, Any]
) -> CheckResult:
    title = "New / mid-year vendor risk profile"
    description = (
        "Vendors newly created during the fiscal year or first active well after year "
        "start: creation record (creator/approver), speed to first invoice, posting "
        "volume, and whether any goods receipts exist."
    )
    ap = resolver.resolve("ap_postings")
    if ap is None:
        return _no_data("new_vendor_profile", title, description, "ap_postings")
    cols = _ap_columns(ap)
    if not cols["vendor"] or not cols["amount"] or not cols["date"]:
        return _no_data("new_vendor_profile", title, description, f"columns on {ap.name}")

    result = CheckResult(check_id="new_vendor_profile", title=title, description=description)
    fiscal_year = _fiscal_year(con, ap, cols["date"])
    grace_days = int(params["new_vendor_grace_days"])
    min_volume = float(params["new_vendor_min_volume"])
    result.notes.append(
        f"ap_postings: {ap.name}; fiscal year {fiscal_year}; candidates = vendors with a "
        f"creation log entry, or first activity > {grace_days} days into the year with "
        f"invoice volume >= {min_volume:,.0f}"
    )

    vendor, amount, date, text = cols["vendor"], cols["amount"], cols["date"], cols["text"]
    profile_rows = con.execute(
        f"""
        SELECT {_q(vendor)} v, min({_q(date)}) first_d, max({_q(date)}) last_d, count(*) n,
               sum(CASE WHEN {_q(amount)} < 0 THEN -{_q(amount)} ELSE 0 END) invoice_total,
               list(_row_id ORDER BY _row_id) rids,
               any_value({_q(text) if text else vendor}) sample_text
        FROM {_q(ap.name)} GROUP BY 1
        """
    ).fetchall()
    profiles = {
        row[0]: {
            "first_posting": str(row[1]),
            "last_posting": str(row[2]),
            "posting_count": int(row[3]),
            "invoice_total_eur": round(float(row[4]), 2),
            "row_ids": [int(r) for r in row[5]],
            "sample_text": str(row[6]),
        }
        for row in profile_rows
    }

    creations: dict[Any, dict[str, Any]] = {}
    changes = resolver.resolve("masterdata_changes")
    if changes is not None:
        field_col = changes.col(r"^feld$|field") or changes.col(r"^art$")
        account_col = changes.col(r"konto|account")
        creator_col = changes.col(r"(geaendert|ge.ndert|angelegt|erfasst)_?von", r"created_by")
        approver_col = changes.col(r"(genehmigt|freigegeben|approved)_?von", r"approved_by")
        date_col = changes.col(r"^datum$", r"datum|date")
        if field_col and account_col:
            select_cols = [c for c in (account_col, date_col, creator_col, approver_col) if c]
            rows = con.execute(
                f"SELECT _row_id, {', '.join(_q(c) for c in select_cols)} FROM {_q(changes.name)} "
                f"WHERE regexp_matches(lower({_q(field_col)}), '{CREATION_VOCAB}')"
            ).fetchall()
            for row in rows:
                record = dict(zip(select_cols, row[1:]))
                creations[record[account_col]] = {
                    "creation_row_id": int(row[0]),
                    "creation_date": str(record.get(date_col, "")),
                    "created_by": str(record.get(creator_col, "")),
                    "approved_by": str(record.get(approver_col, "")),
                }
            result.notes.append(f"creation records from {changes.name}: {len(creations)}")

    receipt_counts: dict[Any, int] = {}
    goods = resolver.resolve("goods_receipts")
    if goods is not None:
        goods_vendor = goods.col(r"^(kreditor|lieferant|vendor)$", r"(kreditor|lieferant|vendor)(?!name)")
        if goods_vendor:
            receipt_counts = dict(
                con.execute(
                    f"SELECT {_q(goods_vendor)}, count(*) FROM {_q(goods.name)} GROUP BY 1"
                ).fetchall()
            )

    names: dict[Any, str] = {}
    master = resolver.resolve("vendor_master")
    if master is not None:
        num_col = master.col(r"(lieferant|kreditor|vendor).*(konto|nummer|nr)")
        name_col = master.col(r"(lieferant|kreditor|vendor).*name", r"^name$")
        if num_col and name_col:
            names = dict(con.execute(f"SELECT {_q(num_col)}, {_q(name_col)} FROM {_q(master.name)}").fetchall())

    year_start = f"{fiscal_year}-01-01"
    candidates = []
    for v, profile in profiles.items():
        creation = creations.get(v)
        days_into_year = con.execute(
            f"SELECT datediff('day', DATE '{year_start}', DATE '{profile['first_posting']}')"
        ).fetchone()[0]
        is_late_starter = days_into_year > grace_days and profile["invoice_total_eur"] >= min_volume
        if not creation and not is_late_starter:
            continue
        attributes: dict[str, Any] = {
            **profile,
            "vendor_name": str(names.get(v, "")),
            "days_into_fiscal_year": int(days_into_year),
            "goods_receipt_count": int(receipt_counts.get(v, 0)),
        }
        if creation:
            attributes.update(creation)
            attributes["creator_equals_approver"] = (
                bool(creation["created_by"]) and creation["created_by"] == creation["approved_by"]
            )
            first = con.execute(
                f"SELECT try_cast('{creation['creation_date']}' AS DATE)"
            ).fetchone()[0]
            if first is not None:
                attributes["days_creation_to_first_posting"] = con.execute(
                    f"SELECT datediff('day', DATE '{first}', DATE '{profile['first_posting']}')"
                ).fetchone()[0]
        row_ids = attributes.pop("row_ids")
        candidates.append(
            CheckHit(
                entity=str(v),
                summary=(
                    f"vendor {v} {attributes['vendor_name']}: "
                    f"{'created in-year, ' if creation else ''}first posting {profile['first_posting']}, "
                    f"invoices {profile['invoice_total_eur']:,.0f} EUR, "
                    f"{attributes['goods_receipt_count']} goods receipts"
                ),
                table=ap.name,
                row_ids=row_ids,
                attributes=attributes,
            )
        )
    candidates.sort(key=lambda h: h.attributes["invoice_total_eur"], reverse=True)
    result.hits = candidates
    return result


def check_missing_goods_receipt(
    con: duckdb.DuckDBPyConnection, resolver: Resolver, params: dict[str, Any]
) -> CheckResult:
    title = "Vendor invoices without any goods receipt"
    description = (
        "Vendors with invoice postings but zero entries in the goods-receipt list "
        "(three-way-match failure). Pure service vendors can be legitimate — check "
        "for contracts and plausible service descriptions."
    )
    ap = resolver.resolve("ap_postings")
    goods = resolver.resolve("goods_receipts")
    if ap is None or goods is None:
        return _no_data("missing_goods_receipt", title, description, "ap_postings / goods_receipts")
    cols = _ap_columns(ap)
    goods_vendor = goods.col(r"^(kreditor|lieferant|vendor)$", r"(kreditor|lieferant|vendor)(?!name)")
    if not cols["vendor"] or not cols["amount"] or not goods_vendor:
        return _no_data("missing_goods_receipt", title, description, "vendor/amount columns")

    result = CheckResult(check_id="missing_goods_receipt", title=title, description=description)
    result.notes.append(f"ap_postings: {ap.name}; goods_receipts: {goods.name}")
    vendor, amount, text = cols["vendor"], cols["amount"], cols["text"]
    rows = con.execute(
        f"""
        SELECT a.{_q(vendor)} v,
               sum(CASE WHEN a.{_q(amount)} < 0 THEN -a.{_q(amount)} ELSE 0 END) invoice_total,
               count(*) n,
               list(DISTINCT {('a.' + _q(text)) if text else "''"}) texts,
               list(a._row_id ORDER BY a._row_id) rids
        FROM {_q(ap.name)} a
        LEFT JOIN {_q(goods.name)} w ON w.{_q(goods_vendor)} = a.{_q(vendor)}
        GROUP BY 1
        HAVING count(w.{_q(goods_vendor)}) = 0
        ORDER BY invoice_total DESC
        """
    ).fetchall()
    for v, invoice_total, n, texts, rids in rows:
        result.hits.append(
            CheckHit(
                entity=str(v),
                summary=(
                    f"vendor {v}: {int(n)} postings, {float(invoice_total):,.0f} EUR invoiced, "
                    f"no goods receipt at all"
                ),
                table=ap.name,
                row_ids=[int(r) for r in rids],
                attributes={
                    "invoice_total_eur": round(float(invoice_total), 2),
                    "posting_count": int(n),
                    "posting_texts": [str(t) for t in texts][:10],
                },
            )
        )
    return result


def check_repair_vocab_in_assets(
    con: duckdb.DuckDBPyConnection, resolver: Resolver, params: dict[str, Any]
) -> CheckResult:
    title = "Repair vocabulary in capitalized assets"
    description = (
        "Asset register entries whose names read like repairs/maintenance "
        "(Reparatur, Instandsetzung, Austausch, Überholung, ...) — repairs belong in "
        "expenses, not assets. Wording vs. account is the signal, not size."
    )
    assets = resolver.resolve("assets")
    if assets is None:
        return _no_data("repair_vocab_in_assets", title, description, "assets register")
    number_col = assets.col(r"anlage.*(nummer|nr)", r"asset.*(number|nr|id)")
    name_col = assets.col(r"bezeichnung", r"name|description")
    if not number_col or not name_col:
        return _no_data("repair_vocab_in_assets", title, description, f"columns on {assets.name}")

    result = CheckResult(check_id="repair_vocab_in_assets", title=title, description=description)
    result.notes.append(f"assets: {assets.name}; vocabulary: {REPAIR_VOCAB}")

    gl_accounts = resolver.resolve("gl_accounts")
    if gl_accounts is not None:
        acc_num, acc_name = gl_accounts.col(r"nummer|nr"), gl_accounts.col(r"name|bezeichnung")
        if acc_num and acc_name:
            expense_accounts = con.execute(
                f"SELECT {_q(acc_num)}, {_q(acc_name)} FROM {_q(gl_accounts.name)} "
                f"WHERE regexp_matches(lower({_q(acc_name)}), '{REPAIR_VOCAB}')"
            ).fetchall()
            if expense_accounts:
                result.notes.append(
                    "dedicated repair expense account(s) exist: "
                    + ", ".join(f"{n} {name}" for n, name in expense_accounts)
                )

    postings = resolver.resolve("asset_postings")
    posting_info: dict[str, dict[str, Any]] = {}
    if postings is not None:
        p_number = postings.col(r"anlage.*(nummer|nr)", r"asset.*(number|nr|id)")
        p_amount = postings.col(r"buchungswert", r"buchungsbetrag", r"betrag|amount")
        p_kind = postings.col(r"buchungs(art|typ)", r"bewegungsart")
        p_date = postings.col(r"wertstellung", r"datum|date")
        p_doc = postings.col(r"beleg")
        if p_number and p_amount:
            kind_filter = (
                f"regexp_matches(lower({_q(p_kind)}), 'acquisition|zugang') AND " if p_kind else ""
            )
            rows = con.execute(
                f"""
                SELECT {_q(p_number)}, sum({_q(p_amount)}),
                       list(DISTINCT {(_q(p_doc)) if p_doc else "''"}),
                       min({_q(p_date) if p_date else p_number}), list(_row_id)
                FROM {_q(postings.name)}
                WHERE {kind_filter}{_q(p_amount)} > 0
                GROUP BY 1
                """
            ).fetchall()
            for asset_no, total, docs, first_date, rids in rows:
                posting_info[str(asset_no)] = {
                    "acquisition_value_eur": round(float(total), 2),
                    "documents": [str(d) for d in docs if str(d)],
                    "acquisition_date": str(first_date),
                    "posting_table": postings.name,
                    "posting_row_ids": [int(r) for r in rids],
                }

    rows = con.execute(
        f"SELECT _row_id, {_q(number_col)}, {_q(name_col)} FROM {_q(assets.name)} "
        f"WHERE regexp_matches(lower({_q(name_col)}), '{REPAIR_VOCAB}')"
    ).fetchall()
    for row_id, asset_no, asset_name in rows:
        attributes: dict[str, Any] = {"asset_name": str(asset_name)}
        attributes.update(posting_info.get(str(asset_no), {}))
        value = attributes.get("acquisition_value_eur")
        result.hits.append(
            CheckHit(
                entity=str(asset_no),
                summary=(
                    f"asset {asset_no} '{asset_name}' has repair-type wording"
                    + (f", capitalized {value:,.0f} EUR" if value else "")
                ),
                table=assets.name,
                row_ids=[int(row_id)],
                attributes=attributes,
            )
        )
    return result


def check_cutoff_unaccrued(
    con: duckdb.DuckDBPyConnection, resolver: Resolver, params: dict[str, Any]
) -> CheckResult:
    title = "Cut-off: next-period invoices for prior-year services"
    description = (
        "Invoices dated in the new year whose service/delivery date lies in the old "
        "year. Each needs a year-end accrual; the check lists the year-end accruals "
        "actually booked so missing ones stand out."
    )
    journal = resolver.resolve("next_period_ap_invoices")
    if journal is None:
        return _no_data("cutoff_unaccrued", title, description, "next-period invoice journal")
    invoice_date = journal.col(r"faktura.*datum", r"rechnungsdatum", r"invoice_?date")
    service_date = journal.col(r"leistungsdatum", r"service_?date", r"lieferdatum")
    vendor = journal.col(r"^(kreditor|lieferant|vendor)$", r"(kreditor|lieferant|vendor)(?!name)")
    vendor_name = journal.col(r"(kreditor|lieferant|vendor).*name")
    amount = journal.col(r"betrag|amount|buchungswert")
    invoice_no = journal.col(r"rechnungs?nummer|invoice")
    if not invoice_date or not service_date:
        return _no_data("cutoff_unaccrued", title, description, f"date columns on {journal.name}")

    result = CheckResult(check_id="cutoff_unaccrued", title=title, description=description)
    result.notes.append(f"next_period_ap_invoices: {journal.name}")

    select_cols = [c for c in (invoice_date, service_date, vendor, vendor_name, amount, invoice_no) if c]
    rows = con.execute(
        f"SELECT _row_id, {', '.join(_q(c) for c in select_cols)} FROM {_q(journal.name)} "
        f"WHERE year({_q(service_date)}) < year({_q(invoice_date)})"
    ).fetchall()

    # Goods receipts corroborate "delivered in the old year": match by invoice
    # number where present, else by vendor + receipt date in the service month.
    goods = resolver.resolve("goods_receipts")
    goods_by_invoice: dict[str, list[Any]] = {}
    goods_by_vendor_month: dict[tuple[str, str], list[Any]] = {}
    if goods is not None:
        goods_invoice = goods.col(r"rechnungs?nummer|invoice")
        goods_note = goods.col(r"bemerkung|note|status")
        goods_vendor = goods.col(r"^(kreditor|lieferant|vendor)$", r"(kreditor|lieferant|vendor)(?!name)")
        goods_date = goods.col(r"(wareneingang|liefer).*datum", r"datum|date")
        select = [
            goods_invoice or "''",
            _q(goods_vendor) if goods_vendor else "''",
            _q(goods_date) if goods_date else "NULL",
            _q(goods_note) if goods_note else "''",
        ]
        if goods_invoice:
            select[0] = _q(goods_invoice)
        for g_inv, g_vendor, g_date, g_note, g_row in con.execute(
            f"SELECT {', '.join(select)}, _row_id FROM {_q(goods.name)}"
        ).fetchall():
            entry = (int(g_row), str(g_note))
            if str(g_inv).strip():
                goods_by_invoice.setdefault(str(g_inv), []).append(entry)
            if g_vendor is not None and g_date is not None:
                goods_by_vendor_month.setdefault((str(g_vendor), str(g_date)[:7]), []).append(entry)
        result.notes.append(
            f"goods receipts from {goods.name}, matched by invoice number or vendor + service month"
        )

    prior_years = {row[dict(zip(select_cols, range(1, len(select_cols) + 1)))[service_date]].year for row in rows}
    gl = resolver.resolve("gl_postings")
    if gl is not None and prior_years:
        gl_text = gl.col(r"buchungstext|text")
        gl_amount = gl.col(r"buchungswert", r"betrag|amount")
        gl_date = gl.col(r"buchungsdatum", r"datum|date")
        if gl_text and gl_amount and gl_date:
            year = max(prior_years)
            accruals = con.execute(
                f"SELECT DISTINCT {_q(gl_text)}, abs({_q(gl_amount)}) FROM {_q(gl.name)} "
                f"WHERE year({_q(gl_date)}) = {year} AND month({_q(gl_date)}) = 12 "
                f"AND regexp_matches(lower({_q(gl_text)}), '{ACCRUAL_VOCAB}')"
            ).fetchall()
            if accruals:
                result.notes.append(
                    f"year-end accruals booked in Dec {year}: "
                    + "; ".join(f"'{t}' {a:,.0f} EUR" for t, a in accruals)
                )
            else:
                result.notes.append(f"no year-end accrual postings found in Dec {year}")

    col_index = {c: i + 1 for i, c in enumerate(select_cols)}
    for row in rows:
        inv_no = str(row[col_index[invoice_no]]) if invoice_no else ""
        receipts = goods_by_invoice.get(inv_no, [])
        if not receipts and vendor:
            service_month = str(row[col_index[service_date]])[:7]
            receipts = goods_by_vendor_month.get((str(row[col_index[vendor]]), service_month), [])
        attributes = {c: str(row[col_index[c]]) for c in select_cols}
        attributes["goods_receipt_rows"] = [r for r, _ in receipts]
        attributes["goods_receipt_notes"] = sorted({n for _, n in receipts if n})
        result.hits.append(
            CheckHit(
                entity=str(row[col_index[vendor]]) if vendor else inv_no,
                summary=(
                    f"invoice {inv_no or '?'} dated {row[col_index[invoice_date]]} but service date "
                    f"{row[col_index[service_date]]} (prior year)"
                    + (f", {float(row[col_index[amount]]):,.0f} EUR" if amount else "")
                    + (", goods received in prior year" if receipts else "")
                ),
                table=journal.name,
                row_ids=[int(row[0])],
                attributes=attributes,
            )
        )
    return result


def check_threshold_split_cluster(
    con: duckdb.DuckDBPyConnection, resolver: Resolver, params: dict[str, Any]
) -> CheckResult:
    limit = float(params["approval_limit_eur"])
    band = float(params["near_threshold_band"])
    lo = limit * band
    title = f"Same-day clusters just under the {limit:,.0f} EUR approval limit"
    description = (
        "Two or more postings to the same vendor on the same day, each within "
        f"[{lo:,.0f}, {limit:,.0f}) EUR and together above the limit — the classic "
        "threshold-splitting pattern to dodge a second signature."
    )
    ap = resolver.resolve("ap_postings")
    if ap is None:
        return _no_data("threshold_split_cluster", title, description, "ap_postings")
    cols = _ap_columns(ap)
    if not cols["vendor"] or not cols["amount"] or not cols["date"]:
        return _no_data("threshold_split_cluster", title, description, f"columns on {ap.name}")

    result = CheckResult(check_id="threshold_split_cluster", title=title, description=description)
    result.notes.append(
        f"ap_postings: {ap.name}; approval limit {limit:,.0f} EUR "
        "(default policy value — confirm against the company's own documents)"
    )
    vendor, amount, date, text = cols["vendor"], cols["amount"], cols["date"], cols["text"]
    # Grouping per amount sign keeps an invoice and its own same-day payment
    # (opposite signs, same value) from being mistaken for a split cluster.
    rows = con.execute(
        f"""
        SELECT {_q(vendor)} v, {_q(date)} d, count(*) n, sum(abs({_q(amount)})) total,
               list(abs({_q(amount)})) amounts, list(_row_id) rids,
               list(DISTINCT {(_q(text)) if text else "''"}) texts
        FROM {_q(ap.name)}
        WHERE abs({_q(amount)}) >= {lo} AND abs({_q(amount)}) < {limit}
        GROUP BY 1, 2, sign({_q(amount)})
        HAVING count(*) >= 2 AND sum(abs({_q(amount)})) >= {limit}
        ORDER BY total DESC
        """
    ).fetchall()
    for v, d, n, total, amounts, rids, texts in rows:
        result.hits.append(
            CheckHit(
                entity=str(v),
                summary=(
                    f"vendor {v} on {d}: {int(n)} postings of "
                    f"{', '.join(f'{a:,.0f}' for a in amounts)} EUR — each under the limit, "
                    f"{float(total):,.0f} EUR combined"
                ),
                table=ap.name,
                row_ids=[int(r) for r in rids],
                attributes={
                    "date": str(d),
                    "amounts_eur": [float(a) for a in amounts],
                    "combined_eur": round(float(total), 2),
                    "posting_texts": [str(t) for t in texts][:10],
                },
            )
        )
    return result


def check_round_amount_stats(
    con: duckdb.DuckDBPyConnection, resolver: Resolver, params: dict[str, Any]
) -> CheckResult:
    floor = float(params["round_amount_min"])
    title = "Large round-amount postings"
    description = (
        f"Ledger postings of at least {floor:,.0f} EUR in exact thousands. Round amounts "
        "are only statistical color — corroborate before reading anything into them."
    )
    gl = resolver.resolve("gl_postings")
    if gl is None:
        return _no_data("round_amount_stats", title, description, "gl_postings")
    amount = gl.col(r"buchungswert", r"buchungsbetrag", r"betrag|amount")
    text = gl.col(r"buchungstext|text")
    date = gl.col(r"buchungsdatum", r"datum|date")
    kind = gl.col(r"buchungs(typ|art)")
    doc = gl.col(r"belegnummer|beleg")
    if not amount:
        return _no_data("round_amount_stats", title, description, f"amount column on {gl.name}")

    result = CheckResult(check_id="round_amount_stats", title=title, description=description)
    kind_filter = (
        f"AND NOT regexp_matches(lower({_q(kind)}), 'vortrag|afa|abschreib|depreciation') " if kind else ""
    )
    rows = con.execute(
        f"""
        SELECT {(_q(doc)) if doc else "''"} doc, any_value({_q(text) if text else amount}),
               any_value({_q(date) if date else amount}), max(abs({_q(amount)})) a, list(_row_id)
        FROM {_q(gl.name)}
        WHERE abs({_q(amount)}) >= {floor} AND abs({_q(amount)}) % 1000 = 0 {kind_filter}
        GROUP BY 1
        ORDER BY a DESC
        """
    ).fetchall()
    result.notes.append(f"gl_postings: {gl.name}; grouped by document number")
    for doc_no, sample_text, sample_date, amount_value, rids in rows:
        result.hits.append(
            CheckHit(
                entity=str(doc_no),
                summary=f"{float(amount_value):,.0f} EUR round posting '{sample_text}' on {sample_date}",
                table=gl.name,
                row_ids=[int(r) for r in rids],
                attributes={"amount_eur": float(amount_value), "text": str(sample_text), "date": str(sample_date)},
            )
        )
    return result


def check_off_hours_user_stats(
    con: duckdb.DuckDBPyConnection, resolver: Resolver, params: dict[str, Any]
) -> CheckResult:
    start, end = int(params["off_hours_start"]), int(params["off_hours_end"])
    title = "Off-hours and weekend postings by user"
    description = (
        f"Postings entered on weekends or between {start}:00 and {end}:00, aggregated per "
        "user. Unusual entry times by non-finance users can indicate manual override."
    )
    gl = resolver.resolve("gl_postings")
    if gl is None:
        return _no_data("off_hours_user_stats", title, description, "gl_postings")
    user = gl.col(r"benutzer|user")
    time_col = gl.col(r"(erfassungs)?zeit|time")
    entry_date = gl.col(r"erfassungsdatum", r"buchungsdatum", r"datum|date")
    amount = gl.col(r"buchungswert", r"betrag|amount")
    if not user or not entry_date:
        return _no_data("off_hours_user_stats", title, description, f"user/date columns on {gl.name}")

    result = CheckResult(check_id="off_hours_user_stats", title=title, description=description)
    hour_expr = f"try_cast(substr({_q(time_col)}, 1, 2) AS INTEGER)" if time_col else "NULL"
    rows = con.execute(
        f"""
        SELECT {_q(user)} u,
               count(*) FILTER (WHERE isodow({_q(entry_date)}) >= 6) weekend_n,
               count(*) FILTER (WHERE {hour_expr} >= {start} OR {hour_expr} < {end}) offhours_n,
               count(*) total_n,
               sum(abs({_q(amount)})) FILTER (
                   WHERE isodow({_q(entry_date)}) >= 6 OR {hour_expr} >= {start} OR {hour_expr} < {end}
               ) flagged_volume,
               list(_row_id) FILTER (
                   WHERE isodow({_q(entry_date)}) >= 6 OR {hour_expr} >= {start} OR {hour_expr} < {end}
               ) rids
        FROM {_q(gl.name)}
        GROUP BY 1
        HAVING weekend_n > 0 OR offhours_n > 0
        ORDER BY (weekend_n + offhours_n) DESC
        """
    ).fetchall()
    result.notes.append(f"gl_postings: {gl.name}; user column {user}, entry date {entry_date}")
    for u, weekend_n, offhours_n, total_n, volume, rids in rows:
        result.hits.append(
            CheckHit(
                entity=str(u),
                summary=(
                    f"user {u}: {int(weekend_n)} weekend / {int(offhours_n)} off-hours entries "
                    f"of {int(total_n)} total"
                ),
                table=gl.name,
                row_ids=[int(r) for r in rids],
                attributes={
                    "weekend_postings": int(weekend_n),
                    "off_hours_postings": int(offhours_n),
                    "total_postings": int(total_n),
                    "flagged_volume_eur": round(float(volume or 0), 2),
                },
            )
        )
    return result


ALL_CHECKS: list[Check] = [
    check_new_vendor_profile,
    check_missing_goods_receipt,
    check_sod_creator_equals_approver,
    check_permission_concentration,
    check_repair_vocab_in_assets,
    check_cutoff_unaccrued,
    check_threshold_split_cluster,
    check_round_amount_stats,
    check_off_hours_user_stats,
]


CHECKS_BY_ID: dict[str, Check] = {c.__name__.removeprefix("check_"): c for c in ALL_CHECKS}


def run_one_check(
    con: duckdb.DuckDBPyConnection, check_id: str, params: dict[str, Any] | None = None
) -> CheckResult:
    """Re-run a single check by id (for the agent's run_check tool)."""
    check = CHECKS_BY_ID.get(check_id)
    if check is None:
        raise KeyError(check_id)
    merged = {**DEFAULT_PARAMS, **(params or {})}
    return _cap_hits(check(con, Resolver(con), merged))


def run_checks(
    con: duckdb.DuckDBPyConnection, params: dict[str, Any] | None = None
) -> list[CheckResult]:
    merged = {**DEFAULT_PARAMS, **(params or {})}
    resolver = Resolver(con)
    results: list[CheckResult] = []
    for check in ALL_CHECKS:
        check_id = check.__name__.removeprefix("check_")
        try:
            result = check(con, resolver, merged)
        except Exception as exc:  # a single broken check must not sink the run on an unseen dossier
            logger.exception("check %s failed", check_id)
            result = CheckResult(
                check_id=check_id,
                title=check_id,
                description="",
                status="error",
                notes=[f"check crashed: {exc}"],
            )
        results.append(_cap_hits(result))
        logger.info(
            "check %s: %s, %d hits", result.check_id, result.status, len(result.hits)
        )
    return results
