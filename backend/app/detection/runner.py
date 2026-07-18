"""Deterministic K1-K7 Journal Entry Testing candidate generation.

The dossier shape is stable for the challenge, so these procedures use the
known normalized table contract. They never contain known vendor ids, dates,
amounts, users, or answer-key facts: all suspicious values come from the
uploaded batch. A RuleHit is an investigation lead, not a fraud conclusion.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Iterable

import duckdb

from ..models import Citation, DetectionSummary, GlobalContext, RuleHit


class DetectorSkipped(RuntimeError):
    pass


@dataclass
class DetectionRun:
    hits: list[RuleHit]
    summary: DetectionSummary


Detector = Callable[[duckdb.DuckDBPyConnection, GlobalContext], list[RuleHit]]


def _tables(con: duckdb.DuckDBPyConnection) -> set[str]:
    return {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}


def _columns(con: duckdb.DuckDBPyConnection, table: str) -> set[str]:
    return {
        r[0]
        for r in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?", [table]
        ).fetchall()
    }


def _require(con: duckdb.DuckDBPyConnection, table: str, columns: Iterable[str]) -> None:
    if table not in _tables(con):
        raise DetectorSkipped(f"missing table {table}")
    missing = set(columns) - _columns(con, table)
    if missing:
        raise DetectorSkipped(f"{table} missing columns: {', '.join(sorted(missing))}")


def _document_for_table(con: duckdb.DuckDBPyConnection, table: str) -> tuple[str, str, str] | None:
    return con.execute(
        "SELECT document_id, file, kind FROM documents WHERE table_name = ? LIMIT 1", [table]
    ).fetchone()


def _table_citation(
    con: duckdb.DuckDBPyConnection,
    table: str,
    rows: Iterable[int],
    excerpt: str | None = None,
) -> Citation:
    document = _document_for_table(con, table)
    if not document:
        raise DetectorSkipped(f"no document metadata for {table}")
    document_id, file, kind = document
    row_ids = sorted({int(r) for r in rows})
    if not row_ids:
        raise DetectorSkipped(f"no evidence rows for {table}")
    sheet = table.split("__", 1)[1] if kind == "xlsx_sheet" and "__" in table else None
    return Citation(
        document_id=document_id,
        file=file,
        table=table,
        rows=row_ids,
        sheet=sheet,
        excerpt=(excerpt or None),
    )


def _prose_citation(row: tuple[str, str, str, str], excerpt: str | None = None) -> Citation:
    document_id, file, ref, text = row
    page_match = re.fullmatch(r"page\s+(\d+)", ref, flags=re.IGNORECASE)
    return Citation(
        document_id=document_id,
        file=file,
        page=int(page_match.group(1)) if page_match else None,
        passage=None if page_match else ref,
        excerpt=(excerpt or text[:300]),
    )


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def _k1_new_vendor(con: duckdb.DuckDBPyConnection, _: GlobalContext) -> list[RuleHit]:
    changes = "stammdatenaenderungen_2025"
    bookings = "kreditoren__lieferantenbuchungen"
    receipts = "wareneingangsliste_2025"
    _require(
        con,
        changes,
        ["_row_id", "datum", "art", "konto", "name", "geaendert_von", "genehmigt_von"],
    )
    _require(
        con,
        bookings,
        ["_row_id", "lieferantenkontonummer", "buchungsdatum", "buchungsbetrag", "buchungstext"],
    )
    _require(con, receipts, ["_row_id", "kreditor"])

    candidates = con.execute(
        f"""
        WITH created AS (
            SELECT *, row_number() OVER (PARTITION BY konto ORDER BY datum, _row_id) AS rn
            FROM {changes}
            WHERE lower(art) LIKE '%kreditor%' OR lower(art) LIKE '%vendor%'
        ), booking_profile AS (
            SELECT lieferantenkontonummer AS konto,
                   min(buchungsdatum) AS first_booking,
                   count(*) AS booking_count,
                   sum(CASE WHEN buchungsbetrag > 0 THEN abs(buchungsbetrag) ELSE 0 END) AS paid_amount,
                   list(_row_id ORDER BY _row_id) AS booking_rows,
                   first(buchungstext ORDER BY buchungsdatum, _row_id) AS first_text
            FROM {bookings}
            GROUP BY lieferantenkontonummer
        ), receipt_profile AS (
            SELECT kreditor AS konto, count(*) AS receipt_count,
                   list(_row_id ORDER BY _row_id) AS receipt_rows
            FROM {receipts}
            GROUP BY kreditor
        )
        SELECT c._row_id, c.datum, c.konto, c.name, c.geaendert_von, c.genehmigt_von,
               b.first_booking, b.booking_count, b.paid_amount, b.booking_rows, b.first_text,
               coalesce(r.receipt_count, 0), r.receipt_rows
        FROM created c
        JOIN booking_profile b USING (konto)
        LEFT JOIN receipt_profile r USING (konto)
        WHERE c.rn = 1 AND b.first_booking >= c.datum
          AND datediff('day', c.datum, b.first_booking) <= 90
        ORDER BY b.paid_amount DESC
        """
    ).fetchall()

    permission_table = "berechtigungsauswertung_2025__berechtigungen"
    permission_available = permission_table in _tables(con)
    hits: list[RuleHit] = []
    for row in candidates:
        (
            change_row,
            created_on,
            vendor_id,
            vendor_name,
            changed_by,
            approved_by,
            first_booking,
            booking_count,
            paid_amount,
            booking_rows,
            first_text,
            receipt_count,
            receipt_rows,
        ) = row
        days = (first_booking - created_on).days
        signals = [f"first booking {days} days after vendor creation"]
        score = 40
        evidence = [
            _table_citation(con, changes, [change_row], str(vendor_name)),
            _table_citation(con, bookings, booking_rows[:12], str(first_text or vendor_id)),
        ]
        counter_evidence: list[Citation] = []
        missing: list[str] = []
        if changed_by and approved_by and changed_by == approved_by:
            score += 25
            signals.append("vendor creator and approver are the same user")
        if receipt_count == 0:
            score += 20
            signals.append("no goods-receipt rows found for vendor")
            missing.append("goods receipt or other delivery evidence")
        elif receipt_rows:
            counter_evidence.append(_table_citation(con, receipts, receipt_rows[:8]))

        if permission_available and changed_by:
            permission = con.execute(
                f"SELECT _row_id, * EXCLUDE (_row_id) FROM {permission_table} "
                "WHERE lower(trim(CAST(\"muster_verpackungen_gmbh_berechtigungsauswertung_d365_per_31_12_2025\" AS VARCHAR))) = lower(?)",
                [str(changed_by)],
            ).fetchone()
            if permission:
                values = {str(v).strip().lower() for v in permission[1:] if v is not None}
                # Three or more X flags indicate broad permissions; the agent receives the row to assess specifics.
                if sum(1 for v in permission[1:] if str(v).strip().lower() == "x") >= 3:
                    score += 15
                    signals.append("user has several accounting/payment/master-data permissions")
                    evidence.append(
                        _table_citation(con, permission_table, [permission[0]], str(changed_by))
                    )
                elif values:
                    counter_evidence.append(
                        _table_citation(con, permission_table, [permission[0]], str(changed_by))
                    )

        if score < 60:
            continue
        hits.append(
            RuleHit(
                rule_id="K1",
                subject_type="vendor",
                subject_id=str(vendor_id),
                title="New vendor with rapid financial activity",
                summary=(
                    f"Vendor {vendor_name} ({vendor_id}) was created on {created_on} and had its "
                    f"first booking {days} days later; {booking_count} vendor-ledger rows and "
                    f"EUR {float(paid_amount or 0):,.2f} of outgoing payments were observed."
                ),
                risk_score=min(score, 100),
                amount_eur=float(paid_amount or 0),
                signals=signals,
                evidence=evidence,
                counter_evidence=counter_evidence,
                missing_evidence=missing,
            )
        )
    return hits


def _k2_missing_support(con: duckdb.DuckDBPyConnection, _: GlobalContext) -> list[RuleHit]:
    bookings = "kreditoren__lieferantenbuchungen"
    vendors = "kreditoren__lieferanten"
    receipts = "wareneingangsliste_2025"
    changes = "stammdatenaenderungen_2025"
    _require(
        con,
        bookings,
        ["_row_id", "lieferantenkontonummer", "buchungsbetrag", "buchungstext"],
    )
    _require(con, vendors, ["lieferantenkontonummer", "lieferantenname"])
    _require(con, receipts, ["kreditor"])

    rows = con.execute(
        f"""
        WITH b AS (
            SELECT lieferantenkontonummer AS konto,
                   sum(CASE WHEN buchungsbetrag > 0 THEN abs(buchungsbetrag) ELSE 0 END) AS paid_amount,
                   count(*) AS booking_count,
                   list(_row_id ORDER BY _row_id) AS booking_rows,
                   first(buchungstext ORDER BY _row_id) AS sample_text
            FROM {bookings}
            GROUP BY lieferantenkontonummer
        ), r AS (
            SELECT kreditor AS konto, count(*) AS receipt_count FROM {receipts} GROUP BY kreditor
        )
        SELECT b.konto, v.lieferantenname, b.paid_amount, b.booking_count,
               b.booking_rows, b.sample_text, coalesce(r.receipt_count, 0)
        FROM b
        JOIN {vendors} v ON v.lieferantenkontonummer = b.konto
        LEFT JOIN r USING (konto)
        WHERE b.paid_amount > 0 AND coalesce(r.receipt_count, 0) = 0
        ORDER BY b.paid_amount DESC
        """
    ).fetchall()
    if not rows:
        return []
    materiality = _percentile([float(r[2] or 0) for r in rows], 0.90)
    hits: list[RuleHit] = []
    for vendor_id, vendor_name, paid_amount, booking_count, booking_rows, sample_text, _ in rows:
        change = None
        if changes in _tables(con):
            change = con.execute(
                f"SELECT _row_id, datum, geaendert_von, genehmigt_von FROM {changes} "
                "WHERE konto = ? AND (lower(art) LIKE '%kreditor%' OR lower(art) LIKE '%vendor%') "
                "ORDER BY datum LIMIT 1",
                [vendor_id],
            ).fetchone()
        if not change and float(paid_amount or 0) < materiality:
            continue

        supporting_docs = con.execute(
            "SELECT document_id, file, ref, text FROM document_texts "
            "WHERE text ILIKE '%' || ? || '%' OR text ILIKE '%' || ? || '%' LIMIT 3",
            [str(vendor_id), str(vendor_name)],
        ).fetchall()
        score = 50
        signals = ["outgoing payments exist but no vendor goods-receipt rows were found"]
        evidence = [_table_citation(con, bookings, booking_rows[:12], str(sample_text or vendor_name))]
        counter_evidence = [_prose_citation(r) for r in supporting_docs]
        missing = ["goods receipt"]
        if change:
            score += 15
            signals.append("vendor was created during the audit period")
            evidence.append(_table_citation(con, changes, [change[0]], str(vendor_name)))
            if change[2] and change[2] == change[3]:
                score += 15
                signals.append("vendor creator and approver are the same user")
        if float(paid_amount or 0) >= materiality:
            score += 10
            signals.append("payments are in the top decile among vendors lacking receipts")
        if supporting_docs:
            score -= 15
            signals.append("potential supporting prose was found and must be reviewed")
        else:
            score += 10
            missing.append("contract or other supporting document")
        if score < 65:
            continue
        hits.append(
            RuleHit(
                rule_id="K2",
                subject_type="vendor",
                subject_id=str(vendor_id),
                title="Payments without matching receipt evidence",
                summary=(
                    f"Vendor {vendor_name} ({vendor_id}) has {booking_count} vendor-ledger rows and "
                    f"EUR {float(paid_amount or 0):,.2f} of outgoing payments, but no matching vendor "
                    "rows occur in the goods-receipt population."
                ),
                risk_score=min(score, 100),
                amount_eur=float(paid_amount or 0),
                signals=signals,
                evidence=evidence,
                counter_evidence=counter_evidence,
                missing_evidence=missing,
            )
        )
    return hits[:20]


def _k3_capitalization(con: duckdb.DuckDBPyConnection, _: GlobalContext) -> list[RuleHit]:
    assets = "av__anlagen"
    entries = "av__anlagenbuchungen"
    _require(con, assets, ["_row_id", "anlagennummer", "anlagenbezeichnung"])
    _require(
        con,
        entries,
        ["_row_id", "anlagennummer", "buchungsbetrag", "buchungsart", "belegnummer"],
    )
    matches = con.execute(
        f"""
        SELECT a._row_id, a.anlagennummer, a.anlagenbezeichnung,
               b._row_id, b.belegnummer, b.buchungsbetrag
        FROM {assets} a
        JOIN {entries} b USING (anlagennummer)
        WHERE regexp_matches(
            lower(a.anlagenbezeichnung),
            'reparatur|instandsetz|wartung|austausch|generalüberhol|kälteanlage|repair|maintenance|service|replacement|overhaul'
        )
        AND (lower(b.buchungsart) LIKE '%acquisition%' OR lower(b.buchungsart) LIKE '%zugang%')
        ORDER BY a._row_id
        """
    ).fetchall()
    if not matches:
        return []
    asset_rows = [r[0] for r in matches]
    booking_rows = [r[3] for r in matches]
    names = [str(r[2]) for r in matches]
    amount = sum(abs(float(r[5] or 0)) for r in matches)
    return [
        RuleHit(
            rule_id="K3",
            subject_type="asset_population",
            subject_id="repair-like-capital-additions",
            title="Repair-like descriptions recorded as asset additions",
            summary=(
                f"{len(matches)} fixed-asset additions totalling EUR {amount:,.2f} use descriptions "
                "associated with repair, maintenance, replacement, or overhaul activity."
            ),
            risk_score=82,
            amount_eur=amount,
            signals=[
                "repair or maintenance vocabulary in asset master data",
                "matching asset-booking rows are classified as acquisitions",
            ],
            evidence=[
                _table_citation(con, assets, asset_rows, names[0]),
                _table_citation(con, entries, booking_rows, str(matches[0][4])),
            ],
            missing_evidence=["capital-investment approval or evidence of a separately usable new asset"],
        )
    ]


def _k4_cutoff(con: duckdb.DuckDBPyConnection, _: GlobalContext) -> list[RuleHit]:
    invoices = "fakturajournal_januar_2026_kreditoren"
    receipts = "wareneingangsliste_2025"
    ledger = "sachkonten__sachkontobuchungen"
    _require(
        con,
        invoices,
        ["_row_id", "rechnungsnummer", "fakturadatum", "leistungsdatum", "betrag_eur"],
    )
    _require(con, receipts, ["_row_id", "rechnungsnummer"])
    _require(con, ledger, ["_row_id", "belegnummer", "dokument", "buchungsdatum", "buchungstext"])
    candidates = con.execute(
        f"""
        SELECT _row_id, rechnungsnummer, fakturadatum, leistungsdatum, betrag_eur
        FROM {invoices}
        WHERE leistungsdatum IS NOT NULL AND fakturadatum IS NOT NULL
          AND year(leistungsdatum) < year(fakturadatum)
          AND month(fakturadatum) <= 2
        ORDER BY leistungsdatum, _row_id
        """
    ).fetchall()
    suspicious: list[tuple] = []
    receipt_rows: list[int] = []
    ledger_counter_rows: list[int] = []
    for row in candidates:
        invoice_no = str(row[1])
        receipts_for_invoice = con.execute(
            f"SELECT _row_id FROM {receipts} WHERE rechnungsnummer = ?", [invoice_no]
        ).fetchall()
        prior_year = row[3].year
        ledger_for_invoice = con.execute(
            f"SELECT _row_id FROM {ledger} WHERE year(buchungsdatum) = ? "
            "AND (belegnummer = ? OR dokument = ? OR buchungstext ILIKE '%' || ? || '%')",
            [prior_year, invoice_no, invoice_no, invoice_no],
        ).fetchall()
        if ledger_for_invoice:
            ledger_counter_rows.extend(r[0] for r in ledger_for_invoice)
            continue
        suspicious.append(row)
        receipt_rows.extend(r[0] for r in receipts_for_invoice)
    if not suspicious:
        return []
    amount = sum(abs(float(r[4] or 0)) for r in suspicious)
    evidence = [
        _table_citation(con, invoices, [r[0] for r in suspicious], str(suspicious[0][1]))
    ]
    if receipt_rows:
        evidence.append(_table_citation(con, receipts, receipt_rows))
    counter = []
    if ledger_counter_rows:
        counter.append(_table_citation(con, ledger, ledger_counter_rows[:20]))
    years = sorted({f"{r[3].year}→{r[2].year}" for r in suspicious})
    return [
        RuleHit(
            rule_id="K4",
            subject_type="period_cutoff",
            subject_id=",".join(years),
            title="Prior-period activity invoiced after year-end without invoice-linked posting",
            summary=(
                f"{len(suspicious)} following-period invoices totalling EUR {amount:,.2f} have service "
                "dates in the prior fiscal year, with no prior-year ledger posting referencing those invoices."
            ),
            risk_score=88 if receipt_rows else 78,
            amount_eur=amount,
            signals=[
                "invoice date and service date fall in different fiscal years",
                "no prior-year ledger row references the invoice",
                *( ["matching prior-year goods-receipt evidence exists"] if receipt_rows else [] ),
            ],
            evidence=evidence,
            counter_evidence=counter,
            missing_evidence=["matching year-end accrual or provision"],
        )
    ]


_EUR_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[.\s]\d{3})+|\d{4,})(?:,\d+)?\s*(?:EUR|€)", re.I)


def _approval_threshold(
    con: duckdb.DuckDBPyConnection, context: GlobalContext
) -> tuple[float, Citation]:
    for item in context.items:
        if item.kind != "policy" or not re.search(r"freigab|approv|threshold|limit", item.statement, re.I):
            continue
        match = _EUR_RE.search(item.statement)
        if match and item.citations:
            value = float(match.group(1).replace(".", "").replace(" ", "").replace(",", "."))
            return value, item.citations[0]
    rows = con.execute(
        "SELECT document_id, file, ref, text FROM document_texts "
        "WHERE regexp_matches(lower(text), 'freigab|approv|vier-augen') ORDER BY document_id, rowid"
    ).fetchall()
    for row in rows:
        match = _EUR_RE.search(row[3])
        if match:
            value = float(match.group(1).replace(".", "").replace(" ", "").replace(",", "."))
            return value, _prose_citation(row, match.group(0))
    raise DetectorSkipped("no cited payment-approval threshold found")


def _k5_threshold_split(con: duckdb.DuckDBPyConnection, context: GlobalContext) -> list[RuleHit]:
    ledger = "sachkonten__sachkontobuchungen"
    _require(
        con,
        ledger,
        [
            "_row_id",
            "sachkontonummer",
            "buchungstyp",
            "buchungsbetrag",
            "buchungsdatum",
            "gegenkonto",
        ],
    )
    threshold, policy_citation = _approval_threshold(con, context)
    lower = threshold * 0.80
    clusters = con.execute(
        f"""
        SELECT regexp_extract(sachkontonummer, '([0-9]{{5,}})$', 1) AS vendor_id,
               buchungsdatum,
               count(DISTINCT gegenkonto) AS payment_count,
               sum(abs(buchungsbetrag)) AS total,
               list(abs(buchungsbetrag) ORDER BY _row_id) AS amounts,
               list(_row_id ORDER BY _row_id) AS cited_rows
        FROM {ledger}
        WHERE lower(buchungstyp) LIKE '%zahlung%'
          AND buchungsbetrag > 0
          AND abs(buchungsbetrag) >= ? AND abs(buchungsbetrag) < ?
          AND regexp_extract(sachkontonummer, '([0-9]{{5,}})$', 1) <> ''
        GROUP BY vendor_id, buchungsdatum
        HAVING count(DISTINCT gegenkonto) >= 3 AND sum(abs(buchungsbetrag)) > ?
        ORDER BY total DESC
        """,
        [lower, threshold, threshold],
    ).fetchall()
    hits: list[RuleHit] = []
    for vendor_id, posting_date, count, total, amounts, rows in clusters:
        hits.append(
            RuleHit(
                rule_id="K5",
                subject_type="vendor",
                subject_id=str(vendor_id),
                title="Cluster of payments immediately below approval threshold",
                summary=(
                    f"{count} distinct payments to vendor {vendor_id} on {posting_date}, each between "
                    f"80% and 100% of the EUR {threshold:,.2f} approval threshold, total "
                    f"EUR {float(total):,.2f}."
                ),
                risk_score=92,
                amount_eur=float(total),
                signals=[
                    "multiple payments to the same vendor on one date",
                    "each payment is immediately below the cited approval threshold",
                    "combined value exceeds the approval threshold",
                ],
                evidence=[
                    _table_citation(con, ledger, rows, str(amounts[0])),
                    policy_citation,
                ],
                missing_evidence=["separate approvals or documented installment arrangement"],
            )
        )
    return hits


def _k6_amount_anomalies(con: duckdb.DuckDBPyConnection, _: GlobalContext) -> list[RuleHit]:
    ledger = "sachkonten__sachkontobuchungen"
    _require(
        con,
        ledger,
        ["_row_id", "buchungsbetrag", "buchungsdatum", "belegnummer", "sachkontonummer", "buchungstext"],
    )
    cutoff = con.execute(
        f"SELECT quantile_cont(abs(buchungsbetrag), 0.99) FROM {ledger} WHERE buchungsbetrag > 0"
    ).fetchone()[0]
    if not cutoff:
        return []
    rows = con.execute(
        f"""
        SELECT _row_id, sachkontonummer, buchungsdatum, belegnummer, buchungsbetrag, buchungstext
        FROM {ledger}
        WHERE buchungsbetrag > 0 AND abs(buchungsbetrag) >= ?
          AND mod(round(abs(buchungsbetrag)), 1000) = 0
        ORDER BY abs(buchungsbetrag) DESC
        LIMIT 20
        """,
        [cutoff],
    ).fetchall()
    hits: list[RuleHit] = []
    for row_id, account, posting_date, document, amount, text in rows:
        hits.append(
            RuleHit(
                rule_id="K6",
                subject_type="journal_entry",
                subject_id=str(document or row_id),
                title="Statistically large round-number posting",
                summary=(
                    f"Ledger row {row_id} posts EUR {float(amount):,.2f} to account {account}; the value "
                    "is both round and above the 99th percentile of positive ledger amounts."
                ),
                risk_score=45,
                amount_eur=float(amount),
                signals=["amount above account-population 99th percentile", "amount divisible by EUR 1,000"],
                evidence=[_table_citation(con, ledger, [row_id], str(text or amount))],
                missing_evidence=["business purpose and approval evidence"],
            )
        )
    return hits


def _privileged_users(con: duckdb.DuckDBPyConnection) -> set[str]:
    table = "berechtigungsauswertung_2025__berechtigungen"
    if table not in _tables(con):
        return {"admin"}
    first_col = "muster_verpackungen_gmbh_berechtigungsauswertung_d365_per_31_12_2025"
    if first_col not in _columns(con, table):
        return {"admin"}
    rows = con.execute(
        f"SELECT {first_col}, unnamed_7, unnamed_8 FROM {table} WHERE _row_id > 3"
    ).fetchall()
    privileged = {"admin"}
    for user, system_admin, management in rows:
        if str(system_admin).strip().lower() in {"x", "ja", "yes"} or str(management).strip().lower() in {
            "x",
            "ja",
            "yes",
        }:
            privileged.add(str(user).strip().lower())
    return privileged


def _k7_user_timing(con: duckdb.DuckDBPyConnection, _: GlobalContext) -> list[RuleHit]:
    approvals = "freigabe_log_journale_2025"
    ledger = "sachkonten__sachkontobuchungen"
    _require(
        con,
        approvals,
        [
            "_row_id",
            "erfassungsnummer",
            "journalname",
            "ersteller",
            "erfasst_am",
            "erfasst_um",
            "freigeber",
            "freigabestatus",
        ],
    )
    _require(con, ledger, ["_row_id", "erfassungsnummer", "buchungsbetrag"])
    privileged = _privileged_users(con)
    rows = con.execute(
        f"""
        WITH journal_values AS (
            SELECT try_cast(erfassungsnummer AS BIGINT) AS entry_no,
                   sum(CASE WHEN buchungsbetrag > 0 THEN buchungsbetrag ELSE 0 END) AS amount,
                   list(_row_id ORDER BY _row_id) AS ledger_rows
            FROM {ledger}
            WHERE try_cast(erfassungsnummer AS BIGINT) IS NOT NULL
            GROUP BY entry_no
        )
        SELECT a._row_id, a.erfassungsnummer, a.journalname, a.ersteller,
               a.erfasst_am, a.erfasst_um, a.freigeber, a.freigabestatus,
               j.amount, j.ledger_rows
        FROM {approvals} a
        LEFT JOIN journal_values j ON j.entry_no = a.erfassungsnummer
        ORDER BY coalesce(j.amount, 0) DESC
        """
    ).fetchall()
    hits: list[RuleHit] = []
    for row in rows:
        approval_row, entry_no, journal_name, preparer, created_on, created_at, approver, status, amount, ledger_rows = row
        signals: list[str] = []
        score = 0
        if preparer and approver and str(preparer).strip().lower() == str(approver).strip().lower():
            score += 70
            signals.append("preparer and approver are the same user")
        if not str(approver or "").strip() and str(status or "").strip().lower() in {
            "posted",
            "gebucht",
            "freigegeben",
            "approved",
        }:
            score += 70
            signals.append("entry is posted/approved without an approver id")
        try:
            hour = int(str(created_at).split(":", 1)[0])
        except (TypeError, ValueError):
            hour = -1
        if hour >= 20 or 0 <= hour < 6:
            score += 25
            signals.append("entry was created outside 06:00-20:00")
        if isinstance(created_on, date) and created_on.weekday() >= 5:
            score += 15
            signals.append("entry was created on a weekend")
        if str(preparer or "").strip().lower() in privileged:
            score += 20
            signals.append("entry was created by an administrative or management user")
        if score < 40:
            continue
        evidence = [_table_citation(con, approvals, [approval_row], str(journal_name or entry_no))]
        if ledger_rows:
            evidence.append(_table_citation(con, ledger, ledger_rows[:12]))
        hits.append(
            RuleHit(
                rule_id="K7",
                subject_type="journal",
                subject_id=str(entry_no),
                title="Suspicious journal authorization or timing",
                summary=(
                    f"Journal {journal_name or entry_no}, prepared by {preparer}, triggered "
                    f"{len(signals)} authorization/timing signals."
                ),
                risk_score=min(score, 100),
                amount_eur=float(amount) if amount is not None else None,
                signals=signals,
                evidence=evidence,
                missing_evidence=["documented exception or business justification"],
            )
        )
    return sorted(hits, key=lambda h: (h.risk_score, h.amount_eur or 0), reverse=True)[:30]


DETECTORS: list[tuple[str, Detector]] = [
    ("K1", _k1_new_vendor),
    ("K2", _k2_missing_support),
    ("K3", _k3_capitalization),
    ("K4", _k4_cutoff),
    ("K5", _k5_threshold_split),
    ("K6", _k6_amount_anomalies),
    ("K7", _k7_user_timing),
]


def run_detection(db_path: Path, context: GlobalContext) -> DetectionRun:
    con = duckdb.connect(str(db_path), read_only=True)
    hits: list[RuleHit] = []
    executed: list[str] = []
    skipped: dict[str, str] = {}
    try:
        for rule_id, detector in DETECTORS:
            try:
                rule_hits = detector(con, context)
                hits.extend(rule_hits)
                executed.append(rule_id)
            except DetectorSkipped as exc:
                skipped[rule_id] = str(exc)
            except duckdb.Error as exc:
                skipped[rule_id] = f"query failed: {exc}"
            except Exception as exc:  # noqa: BLE001 - one detector must not suppress all other checks
                skipped[rule_id] = f"detector failed: {exc}"
    finally:
        con.close()

    # Stable ordering and ids make candidates traceable across the agent and UI.
    hits.sort(key=lambda h: (h.risk_score, h.amount_eur or 0), reverse=True)
    hits = [hit.model_copy(update={"id": f"RH-{i:03d}"}) for i, hit in enumerate(hits, start=1)]
    hit_counts = {rule: sum(1 for h in hits if h.rule_id == rule) for rule, _ in DETECTORS}
    summary = DetectionSummary(executed=executed, skipped=skipped, hit_counts=hit_counts)
    return DetectionRun(hits=hits, summary=summary)


def save_detection(path: Path, run: DetectionRun) -> None:
    path.write_text(
        json.dumps(
            {
                "summary": run.summary.model_dump(mode="json"),
                "hits": [h.model_dump(mode="json") for h in run.hits],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
