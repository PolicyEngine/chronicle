"""Raw publisher inputs for Microcosm's geography-first UK spine (chronicle#412).

Issue #412 asks for the deprivation indices that the FRS 2024-25 deciles may refer to,
with crosswalks to the 2021 and 2022 small areas; the 2024-25 Band D council tax of
every billing authority in England and Wales; and, for a later LCFS change, the 2011
Output Area Classification. Each file is registered raw-only: pinned, archived in R2
and never parsed into facts. The content checks read the committed bytes and pin what
docs/data-sources/uk-geography-first-area-inputs.md says they hold, as fetched on
2026-11-04.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import subprocess
import zipfile
from collections import Counter
from pathlib import Path

import openpyxl
import pandas as pd
import pytest
import xlrd
import yaml
from pypdf import PdfReader

from chronicle.artifacts import (
    build_r2_key,
    inventory_source_artifacts,
    publish_source_artifacts,
)
from chronicle.bundle import UK_BUNDLE_SOURCES
from chronicle.source_package import SOURCE_PACKAGE_ALIASES

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPOSITORY_ROOT / "db" / "data"

# directory, package id, year, filename, sha256, bytes.
RAW_SOURCES = (
    (
        "mhclg/english_indices_of_deprivation_2019_file_1",
        "mhclg-english-indices-of-deprivation-2019-file-1",
        2019,
        "File_1_-_IMD2019_Index_of_Multiple_Deprivation.xlsx",
        "b95ca12952c3a8ebdb2e5c3bb03d5b0e56b76ede3fcf45205db26f280b912d9d",
        1_433_347,
    ),
    (
        "mhclg/english_indices_of_deprivation_2025_file_1",
        "mhclg-english-indices-of-deprivation-2025-file-1",
        2025,
        "File_1_IoD2025_Index_of_Multiple_Deprivation.xlsx",
        "e2b10ed1b4d00c02cba12770a0d854b53f7ba7a103df8125744bedad4779866b",
        1_469_027,
    ),
    (
        "welshgov/wimd_2019_ranks_by_small_area",
        "welshgov-wimd-2019-ranks-by-small-area",
        2019,
        "welsh-index-multiple-deprivation-2019-index-and-domain-ranks-by-small-area.ods",
        "2e7b65a3a276e31a10d4bf24a7d26e5cd9d2d95a796ab65e894fcd4e4b159430",
        232_940,
    ),
    (
        "welshgov/wimd_2025_ranks_by_small_area",
        "welshgov-wimd-2025-ranks-by-small-area",
        2025,
        "wimd-2025-index-and-domain-ranks-by-small-area.ods",
        "755870f8a82f463c2d6cbd079ace00620f299714dc830aef67583145396613dc",
        242_742,
    ),
    (
        "scotgov/simd_2020v2_ranks",
        "scotgov-simd-2020v2-ranks",
        2020,
        "SIMD_2020v2_ranks.xlsx",
        "9904aa957a8177853564415e848e08553c17491d1578ff631a5074cacc9fb296",
        513_811,
    ),
    (
        "scotgov/simd_2020v2_data_zone_lookup",
        "scotgov-simd-2020v2-data-zone-lookup",
        2020,
        "SIMD_2020v2_datazone_lookup_updated_2025.xlsx",
        "0a64937af60fb339a1be85cd2f65b6a3d410a38dc5b6c7f25a72ba2d7060a03e",
        1_339_239,
    ),
    (
        "nisra/nimdm_2017_soa_results",
        "nisra-nimdm-2017-soa-results",
        2017,
        "NIMDM17_SOAresults.xls",
        "3738edf2d264491301b41cc7b64967373d49b09a6f5719225a0e4f7d789af9d3",
        1_772_032,
    ),
    (
        "nisra/nimdm_2017_sa_results",
        "nisra-nimdm-2017-sa-results",
        2017,
        "NIMDM17_SA_for_publication.xls",
        "1499da7859f0f4921152fe249524a71e3358641c64e57024074c9615c28e9cd2",
        1_797_632,
    ),
    (
        "ons/lsoa11_lsoa21_lad22_exact_fit_lookup_v3",
        "ons-lsoa11-lsoa21-lad22-exact-fit-lookup-v3",
        2021,
        "ew_lsoa11_lsoa21_lad22_exact_fit_v3.csv",
        "7cac152d20679fe18aade0dc2d4292b4624f23ba45a43fca7cafce716429e500",
        3_030_656,
    ),
    (
        "ons/nspl_may_2026",
        "ons-nspl-may-2026",
        2026,
        "NSPL_MAY_2026.zip",
        "e0ccd5b3d90fdb537c29afc85b33c6c7ff8647e89e390f2e9ae48530f85f42c1",
        187_209_017,
    ),
    (
        "mhclg/council_tax_levels_england_2024_25_table_1",
        "mhclg-council-tax-levels-england-2024-25-table-1",
        2024,
        "Table_1_24-25__revised_.ods",
        "65361501013d80c112881e4eee235159bfd620781bd7a860c1829ba25f09ec51",
        6_424,
    ),
    (
        "mhclg/council_tax_levels_england_2024_25_table_2",
        "mhclg-council-tax-levels-england-2024-25-table-2",
        2024,
        "Table_2_24-25.ods",
        "c2a5e43199d1e5633b681ccec8ecd3ecff34e919284a48cfeffa8efe83441ec7",
        6_873,
    ),
    (
        "mhclg/council_tax_levels_england_2024_25_table_3",
        "mhclg-council-tax-levels-england-2024-25-table-3",
        2024,
        "Table_3_24-25.ods",
        "cbbaeb226800075bd2e591d3b94bf74f170bc60d2ceabe9e165c17b18be56a17",
        5_788,
    ),
    (
        "mhclg/council_tax_levels_england_2024_25_table_4",
        "mhclg-council-tax-levels-england-2024-25-table-4",
        2024,
        "Table_4_24-25.ods",
        "35dd9635bfb47bb8ab73aa2a2b803daeed8940e9967c2f87c87b422477e4e09e",
        6_801,
    ),
    (
        "mhclg/council_tax_levels_england_2024_25_table_5",
        "mhclg-council-tax-levels-england-2024-25-table-5",
        2024,
        "Table_5_24-25__revised_.ods",
        "20dea0025b5340fd64cbad77e9d485690a9605e0c765f10a3fa4d0f5519443c1",
        6_557,
    ),
    (
        "mhclg/council_tax_levels_england_2024_25_table_6",
        "mhclg-council-tax-levels-england-2024-25-table-6",
        2024,
        "Table_6_24-25.ods",
        "7b33f962f920712d24d9a0acb3520872ac024e02578285d1d2b539066124612e",
        5_920,
    ),
    (
        "mhclg/council_tax_levels_england_2024_25_table_7",
        "mhclg-council-tax-levels-england-2024-25-table-7",
        2024,
        "Table_7_24-25__revised_.ods",
        "f92887cfc83bc05930b31aed6057a375ef1a9d49847e831235ce80120fe1529b",
        53_238,
    ),
    (
        "mhclg/council_tax_levels_england_2024_25_table_8",
        "mhclg-council-tax-levels-england-2024-25-table-8",
        2024,
        "Table_8_24-25.ods",
        "249127ae1bff3f37bb335896f801524562de0dd9668c6c9cd64eacd8a8880245",
        53_280,
    ),
    (
        "mhclg/council_tax_levels_england_2024_25_table_9",
        "mhclg-council-tax-levels-england-2024-25-table-9",
        2024,
        "Table_9_24-25__revised_.ods",
        "ade111fc09ad25d5219cc2c16efa7170255099b2f1d2d884b2f652d0c1e244e6",
        387_852,
    ),
    (
        "welshgov/council_tax_levels_2024_25",
        "welshgov-council-tax-levels-2024-25",
        2024,
        "council-tax-levels-april-2024-march-2025-482.pdf",
        "1caccce6df75758929d48c06855c4adaf9db9d75e190f62d999b9dc3d3c253a6",
        417_849,
    ),
    (
        "welshgov/band_d_council_tax_composition_1993_94_to_2026_27",
        "welshgov-band-d-council-tax-composition-1993-94-to-2026-27",
        2026,
        "statswales_band_d_council_tax_composition_by_billing_authority.csv",
        "b6ea9848bd0fdf4a6310b62a62d614fd4c325b8f8d2e83a4d89eb85886ce552e",
        590_478,
    ),
    (
        "ons/oac2011_clusters_and_names_v3",
        "ons-oac2011-clusters-and-names-v3",
        2011,
        "2011oacclustersandnamescsvv3.zip",
        "2364b044b991cd8c93be13dc6bc006e4a1032a7c95cca0bb6c2c1e6f401fc2de",
        1_527_645,
    ),
    (
        "ons/oa11_oa21_lad22_exact_fit_lookup_v3",
        "ons-oa11-oa21-lad22-exact-fit-lookup-v3",
        2021,
        "ew_oa11_oa21_lad22_exact_fit_v3.csv",
        "afbd894c79af9fa4c866227204d61704b59a74efc043225562796c1d148c1cc1",
        9_835_499,
    ),
)
# As in chronicle#356, the raw-only files above 9 MB stay in R2 and out of Git.
R2_ONLY_ABOVE_BYTES = 9_000_000


def _manifest(directory: str) -> dict:
    return yaml.safe_load((DATA_ROOT / directory / "manifest.yaml").read_text())


def _path(directory: str) -> Path:
    (filename,) = (source[3] for source in RAW_SOURCES if source[0] == directory)
    return DATA_ROOT / directory / filename


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=REPOSITORY_ROOT, capture_output=True, text=True
    )


def _ods_rows(directory: str, sheet: str) -> list[list]:
    frame = pd.read_excel(_path(directory), sheet_name=sheet, header=None, engine="odf")
    return [
        [None if pd.isna(value) else value for value in row]
        for row in frame.itertuples(index=False)
    ]


def _xlsx_rows(directory: str, sheet: str) -> list[tuple]:
    workbook = openpyxl.load_workbook(_path(directory), read_only=True, data_only=True)
    try:
        return list(workbook[sheet].iter_rows(values_only=True))
    finally:
        workbook.close()


def _after_header(rows: list, first_header: str) -> list:
    (start,) = (index for index, row in enumerate(rows) if row[0] == first_header)
    return rows[start + 1 :]


def _tied_ranks(ranks: list[int]) -> int:
    """Count ties in a ranking of 1..n where tied areas share a rank and skip the next."""
    ordered = sorted(ranks)
    assert ordered[0] == 1 and ordered[-1] <= len(ordered)
    ties = 0
    for position, rank in enumerate(ordered[1:], start=1):
        if rank == ordered[position - 1]:
            ties += 1
        else:
            assert rank == position + 1
    return ties


@pytest.mark.parametrize(
    ("directory", "package_id", "year", "filename", "sha256", "size_bytes"),
    RAW_SOURCES,
)
def test_raw_only_registration(
    directory, package_id, year, filename, sha256, size_bytes
):
    """Each artifact is pinned, archived in R2 and kept out of every fact registry."""
    manifest = _manifest(directory)
    source_id = directory.split("/")[0]
    assert manifest["source_id"] == source_id
    assert manifest["package_id"] == package_id
    assert manifest["registration_kind"] == "raw_only"
    assert "chronicle#412" in manifest["provenance_notes"]
    assert list(manifest["files"]) == [year]
    entry = manifest["files"][year]
    assert entry["filename"] == filename
    assert entry["source_url"].startswith("https://")
    assert entry["sha256"] == sha256
    assert entry["size_bytes"] == size_bytes

    key = build_r2_key(
        source_id=source_id,
        package_id=package_id,
        year=year,
        sha256=sha256,
        filename=filename,
        package_path=DATA_ROOT / directory,
    )
    assert key == f"raw/uk/{source_id}/{package_id}/{year}/{sha256}/{filename}"
    assert entry["storage"]["r2"] == {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": key,
        "uri": f"r2://ledger-raw/{key}",
    }

    path = DATA_ROOT / directory / filename
    r2_only = size_bytes > R2_ONLY_ABOVE_BYTES
    assert (entry["storage"].get("local") is False) == r2_only
    if r2_only:
        assert _git("check-ignore", "--quiet", str(path)).returncode == 0
    else:
        payload = path.read_bytes()
        assert len(payload) == size_bytes
        assert hashlib.sha256(payload).hexdigest() == sha256

    assert package_id not in SOURCE_PACKAGE_ALIASES
    assert package_id not in UK_BUNDLE_SOURCES
    assert not (
        REPOSITORY_ROOT / "packages" / directory / "source_package.yaml"
    ).exists()


def test_r2_only_registrations_stay_valid_without_their_bytes(tmp_path):
    """A fresh clone lacks the two R2-only files; inventory and publish-raw accept that."""
    r2_only = [source[0] for source in RAW_SOURCES if source[5] > R2_ONLY_ABOVE_BYTES]
    assert r2_only == ["ons/nspl_may_2026", "ons/oa11_oa21_lad22_exact_fit_lookup_v3"]
    for directory in r2_only:
        target = tmp_path / "db" / "data" / directory
        target.mkdir(parents=True)
        (target / "manifest.yaml").write_bytes(
            (DATA_ROOT / directory / "manifest.yaml").read_bytes()
        )

    inventory = inventory_source_artifacts(tmp_path / "db" / "data")
    published = publish_source_artifacts(
        tmp_path / "db" / "data", wrangler_command="false"
    )

    assert inventory.valid
    assert inventory.counts["missing_count"] == 0
    assert inventory.counts["r2_only_count"] == 2
    assert published.valid
    assert published.counts["skipped_count"] == 2
    assert published.counts["uploaded_count"] == 0


def test_english_indices_rank_every_lsoa_of_their_vintage():
    """IoD 2019 ranks the 32,844 LSOAs of 2011 and IoD 2025 the 33,755 of 2021.

    IoD 2019 File 1 prints 26 pairs of LSOAs that share a rank; IoD 2025 has no ties.
    """
    for directory, sheet, code_header, lsoas, ties in (
        (
            "mhclg/english_indices_of_deprivation_2019_file_1",
            "IMD2019",
            "LSOA code (2011)",
            32_844,
            26,
        ),
        (
            "mhclg/english_indices_of_deprivation_2025_file_1",
            "IMD25",
            "LSOA code (2021)",
            33_755,
            0,
        ),
    ):
        rows = _after_header(_xlsx_rows(directory, sheet), code_header)
        assert len(rows) == len({row[0] for row in rows}) == lsoas
        assert _tied_ranks([row[4] for row in rows]) == ties
        assert Counter(row[5] for row in rows).keys() == set(range(1, 11))
    # The November 2025 re-issue moved this LSOA from Cherwell to West Northamptonshire.
    (row,) = [
        row
        for row in _xlsx_rows(
            "mhclg/english_indices_of_deprivation_2025_file_1", "IMD25"
        )
        if row[0] == "E01027305"
    ]
    assert row[2] == "E06000062"


def test_welsh_indices_rank_every_lsoa_with_deciles():
    for directory, year, lsoas in (
        ("welshgov/wimd_2019_ranks_by_small_area", 2019, 1_909),
        ("welshgov/wimd_2025_ranks_by_small_area", 2025, 1_917),
    ):
        ranks = _after_header(_ods_rows(directory, f"WIMD_{year}_ranks"), "LSOA code")
        ranks = [row for row in ranks if str(row[0]).startswith("W01")]
        assert len(ranks) == lsoas
        assert sorted(int(row[3]) for row in ranks) == list(range(1, lsoas + 1))
        deciles = _after_header(
            _ods_rows(directory, "Deciles_quintiles_quartiles"), "LSOA code"
        )
        deciles = {
            row[0]: (int(row[3]), int(row[4]))
            for row in deciles
            if str(row[0]).startswith("W01")
        }
        assert {row[0]: int(row[3]) for row in ranks} == {
            code: rank for code, (rank, _) in deciles.items()
        }
        assert {decile for _, decile in deciles.values()} == set(range(1, 11))


def test_simd_lookup_carries_the_ranks_with_deciles():
    ranks = _after_header(
        _xlsx_rows("scotgov/simd_2020v2_ranks", "SIMD 2020v2 ranks"), "Data_Zone"
    )
    lookup = _after_header(
        _xlsx_rows(
            "scotgov/simd_2020v2_data_zone_lookup", "SIMD 2020v2 DZ lookup data"
        ),
        "DZ",
    )
    rank_by_zone = {row[0]: int(row[5]) for row in ranks if row[0]}
    assert len(rank_by_zone) == 6_976
    assert sorted(rank_by_zone.values()) == list(range(1, 6_977))
    assert {row[0]: int(row[2]) for row in lookup if row[0]} == rank_by_zone
    assert {int(row[4]) for row in lookup if row[0]} == set(range(1, 11))


def test_simd_ranks_reach_2022_output_areas_through_the_nrs_index():
    """The registered NRS index already links each 2022 output area to SIMD 2020v2."""
    ranks = _after_header(
        _xlsx_rows("scotgov/simd_2020v2_ranks", "SIMD 2020v2 ranks"), "Data_Zone"
    )
    rank_by_zone = {row[0]: int(row[5]) for row in ranks if row[0]}
    with zipfile.ZipFile(
        DATA_ROOT / "nrs/census2022_index/scotland_census_2022_index.zip"
    ) as archive:
        member = archive.open("Census_2022_Index/OA_TO_HIGHER_AREAS.csv")
        areas = list(csv.DictReader(io.TextIOWrapper(member, encoding="utf-8-sig")))
    assert len(areas) == 46_363
    assert all(rank_by_zone[area["DZ2011"]] == int(area["SIMD2020"]) for area in areas)
    # Best fit by output area centroid leaves four 2011 data zones with no 2022 area.
    assert len({area["DZ2011"] for area in areas}) == 6_972


def test_nimdm_ranks_soas_and_small_areas():
    soa = xlrd.open_workbook(_path("nisra/nimdm_2017_soa_results")).sheet_by_name("MDM")
    assert soa.cell_value(0, 2) == "SOA2001"
    soa_ranks = {
        soa.cell_value(i, 2): int(soa.cell_value(i, 4)) for i in range(1, soa.nrows)
    }
    assert len(soa_ranks) == 890
    assert sorted(soa_ranks.values()) == list(range(1, 891))
    small_areas = xlrd.open_workbook(
        _path("nisra/nimdm_2017_sa_results")
    ).sheet_by_name("MDM")
    assert small_areas.cell_value(0, 2) == "SA2011"
    assert sorted(
        int(small_areas.cell_value(i, 4)) for i in range(1, small_areas.nrows)
    ) == list(range(1, 4_538))


def test_lsoa_lookup_change_indicator():
    path = _path("ons/lsoa11_lsoa21_lad22_exact_fit_lookup_v3")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 35_796
    assert Counter(row["CHGIND"] for row in rows) == {
        "U": 33_647,
        "S": 1_900,
        "M": 239,
        "X": 10,
    }
    assert len({row["LSOA11CD"] for row in rows}) == 34_753
    assert len({row["LSOA21CD"] for row in rows}) == 35_672


def test_2024_25_band_table_is_numbered_8():
    """The 2025-26 workbook's Table 9 is Table 8 in the 2024-25 release."""
    rows = _ods_rows("mhclg/council_tax_levels_england_2024_25_table_8", "Table_8")
    assert rows[0][0].startswith(
        "Table 8: Area council tax for a dwelling occupied by two adults by band 2024 to 2025"
    )
    header = [str(value).strip() for value in rows[2][:14]]
    assert header == [
        "E Code",
        "ONS Code",
        "Authority",
        "Region",
        "Class",
        "Area",
        *(f"Band {band}" for band in "ABCDEFGH"),
    ]
    authorities = [row for row in rows[3:] if str(row[1]).startswith("E0")]
    assert len(authorities) == len({row[1] for row in authorities}) == 296
    # Barnsley and Sheffield keep their pre-April 2025 codes here; the NSPL's
    # district columns and the 2025-26 workbook carry E08000038 and E08000039.
    codes = {row[1]: row[2] for row in authorities}
    assert codes["E08000016"] == "Barnsley"
    assert codes["E08000019"] == "Sheffield"
    assert not {"E08000038", "E08000039"} & codes.keys()
    notes = _ods_rows("mhclg/council_tax_levels_england_2024_25_table_8", "Notes")
    assert ["[note a]", "Figures include adult social care and parish precepts."] in [
        row[:2] for row in notes
    ]
    later = pd.read_excel(
        DATA_ROOT
        / "mhclg/council_tax_levels_england_summary_2025_26/Tables_1-9_2025-26.ods",
        sheet_name="Table_9",
        header=None,
        engine="odf",
    )
    assert later.iloc[0, 0].startswith(
        "Table 9: Area council tax for a dwelling occupied by two adults by band 2025 to 2026"
    )
    later_codes = set(later[1].astype(str))
    assert {"E08000038", "E08000039"} <= later_codes
    assert not {"E08000016", "E08000019"} & later_codes


def test_statswales_band_d_matches_the_2024_25_release():
    """The release's Table 1, rounded to the pound, agrees with the StatsWales export."""
    text = (
        PdfReader(_path("welshgov/council_tax_levels_2024_25")).pages[1].extract_text()
    )
    printed = {}
    for line in text.splitlines():
        match = re.fullmatch(
            r"([A-Z][A-Za-z ]+?) ([\d,]+) ([\d,]+) (\d+) (\d+) ([\d,]+)\s*", line
        )
        if match:
            printed[match.group(1)] = [
                int(value.replace(",", "")) for value in match.groups()[1:5]
            ]
    assert len(printed) == 23

    with _path("welshgov/band_d_council_tax_composition_1993_94_to_2026_27").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        reader = csv.DictReader(handle)
        # Authorities are named, not coded; the Wales row is "Total Unitary Authorities".
        assert reader.fieldnames == [
            "Data values",
            "Data description",
            "Row",
            "Year",
            "Authority",
            "Notes",
        ]
        values = {
            (row["Authority"], row["Row"]): float(row["Data values"])
            for row in reader
            if row["Year"] == "2024-25" and row["Data description"] == "£ per band D"
        }
    columns = (
        "Total CT for billing authority area",
        "County council CT (exc. community councils)",
        "Community council CT",
        "Police council tax within county area",
    )
    for name, pounds in printed.items():
        authority = "Total Unitary Authorities" if name == "Wales average" else name
        for column, rounded in zip(columns, pounds, strict=True):
            assert abs(values[(authority, column)] - rounded) <= 0.5


def test_oac_2011_classifies_every_uk_output_area():
    with zipfile.ZipFile(_path("ons/oac2011_clusters_and_names_v3")) as archive:
        (member,) = archive.namelist()
        assert member == "2011 OAC Clusters and Names Excel v3.csv"
        rows = list(
            csv.DictReader(io.TextIOWrapper(archive.open(member), encoding="utf-8-sig"))
        )
    assert Counter(row["Output Area Code"][0] for row in rows) == {
        "E": 171_372,
        "W": 10_036,
        "S": 46_351,
        "N": 4_537,
    }
    assert len({row["Supergroup Code"] for row in rows}) == 8
    assert len({row["Group Code"] for row in rows}) == 26
    assert len({row["Subgroup Code"] for row in rows}) == 76
