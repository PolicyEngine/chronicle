"""Raw publisher inputs for Microcosm's UK atomic-area supports.

Issue #269 registers these artifacts without turning them into Chronicle facts.
The expected identities come from Microcosm's committed provenance register for
its UK atomic-area support builder.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from chronicle.bundle import UK_BUNDLE_SOURCES
from chronicle.source_package import SOURCE_PACKAGE_ALIASES


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPOSITORY_ROOT / "db" / "data"

# directory, source id, package id, year, filename, URL, sha256, bytes,
# retrieval date, primary vintage, every geography vintage carried by the file.
RAW_SOURCES = (
    (
        "ons/oa21_lsoa_msoa_lad22_lookup",
        "ons",
        "ons-oa21-lsoa-msoa-lad22-lookup",
        2021,
        "ew_oa21_lsoa_msoa_lad22_hierarchy.csv",
        "https://open-geography-portalx-ons.hub.arcgis.com/api/download/v1/"
        "items/b9ca90c10aaa4b8d9791e9859a38ca67/csv?layers=0",
        "1b7e715936374c586efbe669d82e3f3d6d093dc5295c2d99ce6ea2349f85153a",
        18_193_283,
        "2026-08-19",
        "2021_census",
        ("2021_census",),
    ),
    (
        "ons/oa21_parncp_lad_rgn_ctry_dec2024_lookup",
        "ons",
        "ons-oa21-parncp-lad-rgn-ctry-dec2024-lookup",
        2024,
        "ew_oa21_parncp_lad24_rgn24_dec2024.csv",
        "https://open-geography-portalx-ons.hub.arcgis.com/api/download/v1/"
        "items/7507c0292db546ed83e4ba60f1115b1d/csv?layers=0",
        "e01842a57c26036641fa5d6c2769dd5ac67af03a64d6790d4f35883f04eb2694",
        27_249_403,
        "2026-09-15",
        "2023_april_lad",
        ("2023_april_lad", "2024_rgn"),
    ),
    (
        "ons/oa21_pcon_jul2024_lookup",
        "ons",
        "ons-oa21-pcon-jul2024-lookup",
        2024,
        "ew_oa21_pcon24_lookup.csv",
        "https://open-geography-portalx-ons.hub.arcgis.com/api/download/v1/"
        "items/5968b5b2c0f14dd29ba277beaae6dec3/csv?layers=0",
        "e4ec577416bde73d5718ef133af4adeaae9b95a41867aeb006b5fc0260c790c0",
        12_879_604,
        "2026-08-19",
        "2024_pcon",
        ("2024_pcon",),
    ),
    (
        "ons/oa21_wd24_lad24_lookup",
        "ons",
        "ons-oa21-wd24-lad24-lookup",
        2024,
        "ew_oa21_ward24_lad24_bestfit.csv",
        "https://open-geography-portalx-ons.hub.arcgis.com/api/download/v1/"
        "items/b21c632804094c149ccdfea1ae59c8c8/csv?layers=0",
        "f2d2df158c6e3e29da09a96d456c718a065e1229590d27f6f5349e45689d7b67",
        12_628_147,
        "2026-09-15",
        "2024_wd",
        ("2024_wd",),
    ),
    (
        "ons/lad_dec2024_itl_jan2025_lookup",
        "ons",
        "ons-lad-dec2024-itl-jan2025-lookup",
        2025,
        "uk_lad24_itl25_lookup.csv",
        "https://open-geography-portalx-ons.hub.arcgis.com/api/download/v1/"
        "items/15bdb6b0ff1c4a64b34a64e2e39f8caf/csv?layers=0",
        "2db528a486fdefebfb03a3fb89d706d037cd10f06692c98cdef60a9b7796b284",
        45_097,
        "2026-09-15",
        "2025_itl",
        ("2025_itl",),
    ),
    (
        "ons/census2021_ts001_oa",
        "ons",
        "ons-census2021-ts001-oa",
        2021,
        "census2021-ts001.zip",
        "https://www.nomisweb.co.uk/output/census/2021/census2021-ts001.zip",
        "b724c1208b7628c7c558156fcc619446486353a12d0b6e0bf388add225653dc6",
        1_870_128,
        "2026-08-19",
        "2021_census",
        ("2021_census",),
    ),
    (
        "ons/census2021_ts041_oa",
        "ons",
        "ons-census2021-ts041-oa",
        2021,
        "census2021-ts041.zip",
        "https://www.nomisweb.co.uk/output/census/2021/census2021-ts041.zip",
        "e4f11fc0ea22393fe3be444027878e67b51d2a44687e122c37439d19a548cb9f",
        1_511_641,
        "2026-08-19",
        "2021_census",
        ("2021_census",),
    ),
    (
        "nrs/oa22_dz22_iz22_lookup",
        "nrs",
        "nrs-oa22-dz22-iz22-lookup",
        2022,
        "scotland_oa22_dz22_iz22.zip",
        "https://www.nrscotland.gov.uk/media/iz3evrqt/oa22_dz22_iz22.zip",
        "3565794561306479b6c618aaa3915f1f29fdce31ee798fdcdab45f880a7ba4aa",
        237_841,
        "2026-08-19",
        "2022_census",
        ("2022_census",),
    ),
    (
        "nrs/oa22_lau25_itl25_lookup",
        "nrs",
        "nrs-oa22-lau25-itl25-lookup",
        2025,
        "scotland_oa22_lau25_itl25.zip",
        "https://www.nrscotland.gov.uk/media/qsxon3dm/oa22_lau25_itl25.zip",
        "4d94e959dfcc83ce6bcd0c09cfc073ad597fb89812eab1d8ab664f4ccbc6ba77",
        369_739,
        "2026-08-19",
        "2019_council_area",
        ("2019_council_area", "2025_itl"),
    ),
    (
        "nrs/oa22_ukpc24_lookup",
        "nrs",
        "nrs-oa22-ukpc24-lookup",
        2024,
        "scotland_oa22_ukpc24.zip",
        "https://www.nrscotland.gov.uk/media/njkmhppf/oa22_ukpc24.zip",
        "b63829d28cdf93606d17ffd12999ec12f54a8bc3065cc40fbf9e975629e4689a",
        181_009,
        "2026-08-19",
        "2024_pcon",
        ("2024_pcon",),
    ),
    (
        "nrs/census2022_oa22_usual_resident_population",
        "nrs",
        "nrs-census2022-oa22-usual-resident-population",
        2022,
        "scotland_outputarea2022_population.csv",
        "https://www.nrscotland.gov.uk/media/owpknvgk/"
        "outputarea2022_usualresidentpopulation.csv",
        "f7af756710c56f335d9332c08f95a68a5775aec4f25f17b21ab979257ed40148",
        678_338,
        "2026-08-19",
        "2022_census",
        ("2022_census",),
    ),
    (
        "nrs/census2022_index",
        "nrs",
        "nrs-census2022-index",
        2022,
        "scotland_census_2022_index.zip",
        "https://www.nrscotland.gov.uk/media/utrbt5ze/census_2022_index.zip",
        "0e4096a321cba2318dc5d2e35c197bf815ac333aebdf4cb0ddce82112b57a261",
        2_922_015,
        "2026-08-19",
        "2022_census",
        ("2022_census", "2022_ew"),
    ),
    (
        "nisra/dz2021_geojson",
        "nisra",
        "nisra-dz2021-geojson",
        2021,
        "ni_dz2021_geojson.zip",
        "https://www.nisra.gov.uk/files/nisra/publications/"
        "geography-dz2021-geojson.zip",
        "3acb357ebdecae64dbc2fb645e62c68f529a00f7ae9c19684bd3b7a10e62676b",
        26_823_947,
        "2026-08-19",
        "2021_census",
        ("2021_census", "2014_lgd", "2014_dea"),
    ),
    (
        "nisra/census2021_dz21_people",
        "nisra",
        "nisra-census2021-dz21-people",
        2021,
        "ni_dz21_population.csv",
        "https://build.nisra.gov.uk/en/custom/table.csv?d=PEOPLE&v=DZ21",
        "5fea5eb724034b4d8d749c67114d903383074dca090e8203a8e819a0d6dd445b",
        108_660,
        "2026-08-19",
        "2021_census",
        ("2021_census",),
    ),
    (
        "nisra/census2021_dz21_households",
        "nisra",
        "nisra-census2021-dz21-households",
        2021,
        "ni_dz21_households.csv",
        "https://build.nisra.gov.uk/en/custom/table.csv?d=HOUSEHOLD&v=DZ21",
        "fa97a7f61036f9a3ec40ea6e3812249d87d0010375f0ff7df0b5d9f77864563d",
        108_641,
        "2026-08-19",
        "2021_census",
        ("2021_census",),
    ),
    (
        "nisra/dz_sdz_lookups_v3",
        "nisra",
        "nisra-dz-sdz-lookups-v3",
        2025,
        "ni_dz21_sdz21_lookups_v3.xlsx",
        "https://www.nisra.gov.uk/files/nisra/documents/2025-04/"
        "geography-data-zone-and-super-data-zone-lookups-v3.xlsx",
        "8e2e1f6daaddd2f5b6887ccab1bf9d0bf179f6d0d2ba60ef8e0ebb495a3e1999",
        603_543,
        "2026-09-09",
        "2024_pcon",
        ("2021_census", "2014_lgd", "2014_dea", "2024_pcon"),
    ),
)


@pytest.mark.parametrize(
    (
        "relative_directory",
        "source_id",
        "package_id",
        "year",
        "filename",
        "source_url",
        "sha256",
        "size_bytes",
        "retrieved_at",
        "vintage",
        "vintages",
    ),
    RAW_SOURCES,
)
def test_uk_atomic_area_source_is_registered_raw_only(
    relative_directory: str,
    source_id: str,
    package_id: str,
    year: int,
    filename: str,
    source_url: str,
    sha256: str,
    size_bytes: int,
    retrieved_at: str,
    vintage: str,
    vintages: tuple[str, ...],
) -> None:
    """Each registered artifact must remain byte-identical and facts-free."""
    directory = DATA_ROOT / relative_directory
    manifest = yaml.safe_load((directory / "manifest.yaml").read_text())
    artifact = manifest["files"][year]

    assert manifest["source_id"] == source_id
    assert manifest["package_id"] == package_id
    assert artifact["filename"] == filename
    assert artifact["source_url"] == source_url
    assert artifact["sha256"] == sha256
    assert artifact["size_bytes"] == size_bytes
    assert artifact["fetched_at"] == retrieved_at
    assert artifact["retrieved_at"] == retrieved_at
    assert artifact["vintage"] == vintage
    assert tuple(artifact["vintages"]) == vintages

    payload = (directory / filename).read_bytes()
    assert len(payload) == size_bytes
    assert hashlib.sha256(payload).hexdigest() == sha256

    r2 = artifact["storage"]["r2"]
    expected_key = f"raw/uk/{source_id}/{package_id}/{year}/{sha256}/{filename}"
    assert r2 == {
        "provider": "r2",
        "bucket": "ledger-raw",
        "key": expected_key,
        "uri": f"r2://ledger-raw/{expected_key}",
    }

    assert {path.name for path in directory.iterdir()} == {
        "manifest.yaml",
        filename,
    }
    package_directory = REPOSITORY_ROOT / "packages" / relative_directory
    assert not (package_directory / "source_package.yaml").exists()


def test_retired_uk_atomic_area_sources_are_not_registered() -> None:
    """Superseded lookups must not be added alongside the current vintages."""
    retired_filenames = {
        "england_lad22_region22_lookup.csv",
        "ew_oa21_lad23_lookup.csv",
        "ew_oa21_ward22_bestfit.csv",
        "uk_lad23_itl21_lookup.csv",
    }

    registered = {
        path.name
        for publisher in ("ons", "nrs", "nisra")
        for path in (DATA_ROOT / publisher).rglob("*")
        if path.is_file()
    }
    assert retired_filenames.isdisjoint(registered)


def test_uk_atomic_area_sources_stay_out_of_fact_package_registries() -> None:
    """Raw-only registrations must not enter aliases or the consumer bundle."""
    raw_package_ids = {source[2] for source in RAW_SOURCES}

    assert raw_package_ids.isdisjoint(SOURCE_PACKAGE_ALIASES)
    assert raw_package_ids.isdisjoint(UK_BUNDLE_SOURCES)
