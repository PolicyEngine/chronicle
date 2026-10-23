"""Publisher-cell fidelity for FPD's January 2025 amount-band distributions."""

from __future__ import annotations

import csv
import hashlib
import re
import runpy
from collections import defaultdict
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import pytest
import yaml
from pypdf import PdfReader

from chronicle.source_package import (
    SOURCE_PACKAGE_ALIASES,
    load_source_package,
    validate_source_package,
)

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "db/data/sfpd/pension_amount_bands_2025"
PACKAGE = REPO / "packages/sfpd/pension_amount_bands_2025"
ALIAS = "sfpd-pension-amount-bands-2025"
PDF = "nl_statistiek_2025.pdf"
CSV = "pension_amount_bands_2025.csv"
SHA256 = "198baf61f9277755059367c811664a71917aab6fe5d2b7e2c7e2c96e9baa8c64"
SOURCE_URL = "https://www.sfpd.fgov.be/media/Stat/Jaarlijks/" + PDF


@lru_cache
def _document():
    return PdfReader(DATA / PDF)


@lru_cache
def _rows():
    with (DATA / CSV).open(newline="", encoding="utf-8") as stream:
        return tuple(csv.DictReader(stream))


@lru_cache
def _raw_numbers(page_number):
    """Read literal PDF operators without the generator's ContentStream parser.

    These tables use one positioned TJ array per printed number. Joining literal
    array fragments ignores kerning operands while preserving the publisher's
    decimal comma and thousands stops. Coordinates are native Form coordinates.
    """
    result = {}
    page = _document().pages[page_number - 1]
    for form in page["/Resources"].get("/XObject", {}).values():
        form = form.get_object()
        if form.get("/Subtype") != "/Form":
            continue
        for block in re.findall(rb"BT\s(.*?)\sET", form.get_data(), re.S):
            matrix = re.search(rb"1 0 0 1 ([\d.-]+) ([\d.-]+) Tm", block)
            array = re.search(rb"\[(.*?)\] TJ", block, re.S)
            if matrix is None or array is None:
                continue
            text = (
                b"".join(re.findall(rb"\(([^()]*)\)", array[1]))
                .decode("latin1")
                .strip()
            )
            if re.fullmatch(r"[0-9][0-9.,]*", text):
                xy = tuple(Decimal(value.decode()) for value in matrix.groups())
                assert xy not in result, (page_number, xy)
                result[xy] = text
    return result


def _published_number(text):
    return Decimal(text.replace(".", "").replace(",", "."))


def test_sfpd_pdf_capture_is_unchanged():
    raw = DATA / PDF
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == SHA256
    assert raw.stat().st_size == 5_546_459
    assert len(_document().pages) == 244


def test_sfpd_manifest_preserves_capture_and_declares_r2_locations():
    manifest = yaml.safe_load((DATA / "manifest.yaml").read_text())
    assert manifest["source_id"] == "belgium"
    assert manifest["package_id"] == ALIAS
    assert manifest["publisher"] == "Federale Pensioendienst (FPD/SFPD)"
    capture = manifest["files"]["source_capture"]
    assert capture["filename"] == PDF
    assert capture["sha256"] == SHA256
    assert capture["size_bytes"] == 5_546_459
    for key, entry in manifest["files"].items():
        path = DATA / entry["filename"]
        assert entry["source_url"] == SOURCE_URL
        assert entry["retrieved_at"] == "2026-10-23"
        assert entry["size_bytes"] == path.stat().st_size
        assert entry["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        storage_key = f"raw/belgium/{ALIAS}/{key}/{entry['sha256']}/{entry['filename']}"
        assert entry["storage"]["r2"] == {
            "provider": "r2",
            "bucket": "ledger-raw",
            "key": storage_key,
            "uri": f"r2://ledger-raw/{storage_key}",
        }


@pytest.mark.parametrize(
    "page,x,y,raw",
    [
        (58, "87.9", "611.19", "2.449.233"),
        (58, "136.73", "611.19", "3.648.568.632,67"),
        (58, "110.43", "3.0357", "601"),
        (58, "152.5", "3.0357", "2.145.711,51"),
        (60, "87.9", "611.19", "1.266.981"),
        (227, "87.9", "637.41", "118.262"),
        (227, "128.45", "637.41", "85.039.735,46"),
        (227, "92.4", "3.0357", "10.284"),
        (240, "106.7", "671.95", "2.489.512"),
        (240, "167.58", "671.95", "283.233"),
        (242, "97.675", "671.2", "1.296.286"),
    ],
)
def test_sfpd_independent_raw_form_samples(page, x, y, raw):
    assert _raw_numbers(page)[Decimal(x), Decimal(y)] == raw
    found = []
    for row in _rows():
        if row["pdf_page"] != str(page):
            continue
        for metric, raw_key, position_key in (
            ("recipients", "recipients_raw", "recipients_position"),
            ("monthly_expenditure_eur", "expenditure_raw", "expenditure_position"),
        ):
            position = row[position_key]
            if position and tuple(map(Decimal, position.split(","))) == (
                Decimal(x),
                Decimal(y),
            ):
                assert row[raw_key] == raw
                assert Decimal(row[metric]) == _published_number(raw)
                found.append((row, metric))
    assert len(found) == 1
    row, _ = found[0]
    assert row["sfpd.sex"] == ("Vrouwen" if page in (60, 242) else "Mannen en vrouwen")
    if page in (58, 60):
        assert row["section"] == "1.2"
        assert row["table"] == "1.2.1"
        assert row["sfpd.career"] == "Alle loopbanen"
        if y == "3.0357":
            assert row["sfpd.monthly_amount_band"] == "3.125,00 en >"
            assert row["sfpd.pension_category"] == (
                "Niet gehuwd: Rust bedrag alleenstaande"
            )
        else:
            assert row["sfpd.monthly_amount_band"] == "Totaal"
            assert row["sfpd.pension_category"] == "Totaal"
    elif page == 227:
        assert row["section"] == "6.2"
        assert row["sfpd.igo_eligibility"] == "Totaal"
        assert row["sfpd.monthly_amount_band"] == (
            "1.500,00 en meer" if y == "3.0357" else "Totaal"
        )
    else:
        assert row["section"] == "9"
        assert row["sfpd.age_group"] == "Totaal"
        assert row["sfpd.monthly_amount_band"] == (
            "minder dan 125,00" if raw == "283.233" else "Totaal"
        )


def test_sfpd_every_normalized_value_is_one_exact_printed_pdf_cell():
    selected = set()
    count = defaultdict(int)
    for row in _rows():
        page = int(row["pdf_page"])
        assert int(row["printed_page"]) == page - 10
        assert row["pdf_form"].startswith("/Meta")
        assert int(row["pdf_panel"]) in (1, 2, 3)
        assert int(row["pdf_row"]) > 0
        for metric, raw_key, position_key, column_key in (
            (
                "recipients",
                "recipients_raw",
                "recipients_position",
                "recipients_column",
            ),
            (
                "monthly_expenditure_eur",
                "expenditure_raw",
                "expenditure_position",
                "expenditure_column",
            ),
        ):
            if not row[metric]:
                assert row[raw_key] == row[position_key] == row[column_key] == ""
                continue
            position = tuple(map(Decimal, row[position_key].split(",")))
            assert _raw_numbers(page)[position] == row[raw_key]
            assert Decimal(row[metric]) == _published_number(row[raw_key])
            assert int(row[column_key]) >= 2
            cell = (page, position)
            assert cell not in selected, cell
            selected.add(cell)
            count[row["section"]] += 1
    assert count["1.2"] == 7_980
    assert set(count) == {"1.2", "6.2", "9"}
    assert sum(count.values()) == 10_239
    # Every numeric token in these amount-band tables is a count or expense.
    # Section 9 also has numerical column-header fragments, checked via samples.
    for page in (*range(58, 61), *range(62, 86), *range(227, 230)):
        source = {
            (page, position) for position in _raw_numbers(page) if position[0] >= 77
        }
        assert source == {cell for cell in selected if cell[0] == page}


def test_sfpd_published_column_totals_reconcile_without_creating_facts():
    groups = defaultdict(list)
    for row in _rows():
        axis = "sfpd.age_group" if row["section"] == "9" else "sfpd.monthly_amount_band"
        key = (
            row["pdf_page"],
            row["sfpd.pension_category"],
            row["sfpd.igo_eligibility"],
            row["sfpd.monthly_amount_band"] if row["section"] == "9" else "",
        )
        groups[axis, key].append(row)
    for (axis, key), members in groups.items():
        totals = [row for row in members if row[axis] == "Totaal"]
        assert len(totals) == 1, key
        for metric in ("recipients", "monthly_expenditure_eur"):
            if not totals[0][metric]:
                continue
            printed_total = Decimal(totals[0][metric])
            details = [
                Decimal(row[metric])
                for row in members
                if row[axis] != "Totaal" and row[metric]
            ]
            assert sum(details, Decimal(0)) == printed_total, (key, metric)


def test_sfpd_coverage_keeps_populations_separate_and_open_bands_exact():
    rows = _rows()
    pages = {int(row["pdf_page"]) for row in rows}
    assert pages == {*range(58, 61), *range(62, 86), *range(227, 230), *range(240, 243)}
    assert len(pages) == 33
    populations = {
        "1.2": "Pensioengerechtigden (werknemers en zelfstandigen)",
        "6.2": "Inkomensgarantie voor ouderen (IGO)",
        "9": "FPD-uitkeringsgerechtigden (werknemers en zelfstandigen)",
    }
    for section, population in populations.items():
        assert {
            row["sfpd.population"] for row in rows if row["section"] == section
        } == {population}
    pension_bands = {
        row["sfpd.monthly_amount_band"] for row in rows if row["section"] == "1.2"
    }
    assert len(pension_bands) == 27
    assert {"0,01 - 124,99", "3.125,00 en >", "Totaal"} <= pension_bands
    # Preserve the publisher's overlapping boundary typo on every sex page.
    typo = "1.225,00 tot 1.449,99"
    for page in (227, 228, 229):
        assert typo in _document().pages[page - 1].extract_text()
        printed_rows = [
            row
            for row in rows
            if row["pdf_page"] == str(page) and row["sfpd.monthly_amount_band"] == typo
        ]
        assert printed_rows
        assert {row["sfpd.monthly_amount_upper_bound"] for row in printed_rows} == {
            "1449.99"
        }
    for row in rows:
        band = row["sfpd.monthly_amount_band"]
        if band == "3.125,00 en >":
            assert row["sfpd.monthly_amount_lower_bound"] == "3125.00"
            assert row["sfpd.monthly_amount_upper_bound"] == ""
        elif band == "minder dan 125,00":
            assert row["sfpd.monthly_amount_lower_bound"] == ""
            assert row["sfpd.monthly_amount_upper_bound"] == "125.00"
        elif band == "2.000 en meer":
            assert row["sfpd.monthly_amount_lower_bound"] == "2000"
            assert row["sfpd.monthly_amount_upper_bound"] == ""


def test_sfpd_unpaired_printed_cells_keep_their_own_band_and_blank():
    # PDF p66 prints the expense on the preceding band to its lone count.
    # Reassigning either value to make the row look paired changes the source.
    assert _raw_numbers(66)[Decimal("407.95"), Decimal("22.536")] == "2.879,23"
    assert _raw_numbers(66)[Decimal("357.63"), Decimal("12.786")] == "1"
    survivors = {
        row["sfpd.monthly_amount_band"]: row
        for row in _rows()
        if row["pdf_page"] == "66"
        and row["sfpd.pension_category"]
        == "Niet gehuwd: Overleving en overgangsuitkering"
    }
    expense_only = survivors["2.875,00 - 2.999,99"]
    assert expense_only["recipients"] == expense_only["recipients_raw"] == ""
    assert expense_only["monthly_expenditure_eur"] == "2879.23"
    assert expense_only["expenditure_position"] == "407.95,22.536"
    count_only = survivors["3.000,00 - 3.124,99"]
    assert count_only["recipients"] == "1"
    assert count_only["recipients_position"] == "357.63,12.786"
    assert count_only["monthly_expenditure_eur"] == count_only["expenditure_raw"] == ""


def test_sfpd_package_has_publisher_period_single_cell_selectors_and_provenance():
    assert SOURCE_PACKAGE_ALIASES[ALIAS] == Path("sfpd/pension_amount_bands_2025")
    report = validate_source_package(PACKAGE, year=2025)
    assert report.valid, report.to_dict()
    assert not report.warnings
    text = (PACKAGE / "source_package.yaml").read_text()
    # Scalar declarations must remain textual on every set, without YAML merges.
    assert not re.search(r"(?:^|\s)[&*][A-Za-z_]", text)
    assert "<<:" not in text
    spec = yaml.safe_load(text)
    assert text.count("provenance_class: administrative") == len(spec["record_sets"])
    for record_set in spec["record_sets"]:
        assert record_set["provenance_class"] == "administrative"
        assert record_set["assertion"] == "observation"
        assert (record_set["period_type"], record_set["period"]) == ("month", "2025-01")
        assert record_set["period_coverage"]["source_period_label"] == "januari 2025"
        assert record_set["period_coverage"]["start_date"] == "2025-01-01"
        assert record_set["period_coverage"]["end_date"] == "2025-01-31"
        assert record_set["period_coverage"]["basis"] == "calendar"
        for row in record_set["rows"]:
            assert "row_end_number" not in row
            assert row["guard_cells"]
        for measure in record_set["measures"]:
            assert measure.get("value_scale", 1) == 1
            assert "divisor_column" not in measure
            assert measure["aggregation"] == "sum"
    assert load_source_package(PACKAGE).package_id == ALIAS


def test_sfpd_generator_reproduces_committed_capture_transcription(tmp_path):
    data = tmp_path / "data"
    package = tmp_path / "package"
    data.mkdir()
    (data / PDF).symlink_to(DATA / PDF)
    generator = runpy.run_path(str(PACKAGE / "build_package.py"))
    generator["generate"](data_dir=data, package_dir=package)
    assert (data / CSV).read_bytes() == (DATA / CSV).read_bytes()
    assert (data / "manifest.yaml").read_bytes() == (
        DATA / "manifest.yaml"
    ).read_bytes()
    assert (package / "source_package.yaml").read_bytes() == (
        PACKAGE / "source_package.yaml"
    ).read_bytes()


def test_sfpd_scope_and_gross_reference_month_are_publisher_evidence():
    intro = _document().pages[10].extract_text()
    assert "gegevens van januari 2025" in intro
    assert "gedeelte werknemers en zelfstandigen" in intro
    assert "(ex-RVP)" in intro
    assert "steeds maandelijkse brutobedragen" in (_document().pages[13].extract_text())
    scope9 = _document().pages[238].extract_text()
    assert "Toestand op 1 januari 2025" in scope9
    assert "2.489.512" in scope9
    assert "maar met het betaalde bedrag wordt geen rekening gehouden" in scope9
