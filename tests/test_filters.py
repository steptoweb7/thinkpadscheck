from olx_bot.db import init_db, record_price_observation
from olx_bot.filters import (
    capacity_bucket,
    extract_ssd_capacity_gb,
    passes_hard_filters,
    passes_ssd_deal_filter,
)

CONFIG = {"max_price": 1500}
SSD_CONFIG = {
    "ssd_deal": {
        "max_price": 800,
        "min_ssd_gb": 512,
        "min_samples": 5,
        "discount_threshold": 0.6,
    }
}


def _conn_with_market_prices(tmp_path, bucket, prices, name="market.db"):
    conn = init_db(str(tmp_path / name))
    for i, price in enumerate(prices):
        record_price_observation(conn, f"market-ad-{bucket}-{i}", bucket, price, "2026-09-12T00:00:00")
    return conn


def standalone_drive_listing(**overrides):
    listing = {
        "title": "SSD Samsung 512GB SATA",
        "description": "SSD nou, sigilat",
        "price": 150,
        "is_business": False,
        "params": {"state": "Nou", "tip": "SSD"},
    }
    listing.update(overrides)
    return listing


def ssd_deal_listing(**overrides):
    listing = {
        "title": "Laptop HP i5-1035G1, 8GB, 512GB SSD",
        "description": "Stare buna, functioneaza perfect",
        "price": 700,
        "is_business": False,
        "params": {"tip_stocare": "SSD"},
    }
    listing.update(overrides)
    return listing


def qualifying_listing(**overrides):
    listing = {
        "title": "Laptop Lenovo ThinkPad T14 i5-1135G7",
        "description": "16GB RAM DDR4, SSD 512GB, stare impecabila",
        "price": 1200,
        "is_business": False,
        "params": {
            "tip_stocare": "SSD",
            "capacitate_memorie_ram": "> 16 GB",
        },
    }
    listing.update(overrides)
    return listing


def test_qualifying_listing_passes():
    assert passes_hard_filters(qualifying_listing(), CONFIG) is True


def test_excludes_defective():
    listing = qualifying_listing(
        title="Laptop Lenovo ThinkPad T14 i5-1135G7 - vandut pentru piese, nu porneste"
    )
    assert passes_hard_filters(listing, CONFIG) is False


def test_excludes_non_business_model():
    listing = qualifying_listing(title="Laptop Asus X515 i5-1135G7")
    assert passes_hard_filters(listing, CONFIG) is False


def test_excludes_low_ram_bucket():
    listing = qualifying_listing(
        params={"tip_stocare": "SSD", "capacitate_memorie_ram": "8 - 12 GB"}
    )
    assert passes_hard_filters(listing, CONFIG) is False


def test_excludes_old_cpu():
    listing = qualifying_listing(
        title="Laptop Lenovo ThinkPad T14 i5-6200U",
        description="8GB RAM, SSD 256GB",
    )
    assert passes_hard_filters(listing, CONFIG) is False


def test_excludes_hdd_only():
    listing = qualifying_listing(
        params={"tip_stocare": "HDD", "capacitate_memorie_ram": "> 16 GB"}
    )
    assert passes_hard_filters(listing, CONFIG) is False


def test_excludes_over_price():
    listing = qualifying_listing(price=1600)
    assert passes_hard_filters(listing, CONFIG) is False


def test_excludes_business_seller():
    listing = qualifying_listing(is_business=True)
    assert passes_hard_filters(listing, CONFIG) is False


def test_ambiguous_ram_bucket_passes_with_explicit_mention():
    listing = qualifying_listing(
        title="Laptop Lenovo ThinkPad T14 i5-1135G7 16GB",
        description="SSD 512GB",
        params={"tip_stocare": "SSD", "capacitate_memorie_ram": "12 - 16 GB"},
    )
    assert passes_hard_filters(listing, CONFIG) is True


def test_ambiguous_ram_bucket_fails_without_explicit_mention():
    listing = qualifying_listing(
        description="RAM generoasa, SSD 512GB",
        params={"tip_stocare": "SSD", "capacitate_memorie_ram": "12 - 16 GB"},
    )
    assert passes_hard_filters(listing, CONFIG) is False


def test_title_qualifies_despite_defect_boilerplate_in_description():
    """Real bug: buyback/trade-in disclaimer about the OLD laptop in the
    description used to match the 'defect' exclusion keyword even though
    the listed item itself is fine."""
    listing = qualifying_listing(
        title="Laptop Lenovo ThinkPad T14 gen2 i5-1145G7",
        description=(
            "Vino cu laptopul tau vechi, poate fi si defect, pentru o "
            "reducere la achizitia unui laptop nou."
        ),
    )
    assert passes_hard_filters(listing, CONFIG) is True


def test_non_business_title_not_saved_by_description_boilerplate():
    """Real bug: 'x1' in an accessory-count blurb ('incarcator x1') used to
    match the ThinkPad X1 model pattern, and an unrelated CPU mentioned in
    inventory boilerplate used to satisfy the CPU-gen check."""
    listing = qualifying_listing(
        title="Laptop Asus X515 i3-1005G1",
        description=(
            "In pachet: incarcator x1, mouse x1. Avem in stoc si modele cu "
            "i5-1135G7 la comanda."
        ),
    )
    assert passes_hard_filters(listing, CONFIG) is False


def test_ambiguous_ram_bucket_fails_when_16gb_only_in_description_upgrade_offer():
    """Real bug: a paid RAM-upgrade offer in the description ('upgrade la
    16gb + 120 lei') used to satisfy the ambiguous-bucket check even though
    the listed unit itself isn't 16GB."""
    listing = qualifying_listing(
        description="8gb DDR4, upgrade la 16gb + 120 lei",
        params={"tip_stocare": "SSD", "capacitate_memorie_ram": "12 - 16 GB"},
    )
    assert passes_hard_filters(listing, CONFIG) is False


# --- SSD-deal rule: any specs, just a real SSD >= min_ssd_gb at a very low price ---


def test_extract_ssd_capacity_gb_from_title():
    assert extract_ssd_capacity_gb("Laptop HP i5, 512GB SSD") == 512


def test_extract_ssd_capacity_gb_handles_terabytes():
    assert extract_ssd_capacity_gb("SSD 1TB NVMe, stare buna") == 1000


def test_extract_ssd_capacity_gb_handles_reversed_order():
    assert extract_ssd_capacity_gb("Stocare: 512 GB SSD") == 512


def test_extract_ssd_capacity_gb_returns_none_when_not_mentioned():
    assert extract_ssd_capacity_gb("Laptop HP i5, stare buna") is None


def test_extract_ssd_capacity_gb_takes_largest_mention():
    assert extract_ssd_capacity_gb("SSD 256GB + slot liber pentru inca un SSD 1TB") == 1000


def test_extract_ssd_capacity_gb_handles_decimal_terabytes():
    """Real bug: enterprise SSD listings commonly say '1.92TB'; the old
    regex only captured the digits after the decimal point, reading it as
    92000GB."""
    assert extract_ssd_capacity_gb("Intel SSD DC S4610 1.92TB SATA enterprise") == 1920


def test_extract_ssd_capacity_gb_ignores_implausibly_large_numbers():
    """Real bug: an unrelated large number in the description (a serial
    number, a price, whatever) immediately followed by 'gb'/'tb' text
    elsewhere produced a multi-million-GB 'capacity'. Cap at a generous
    but sane ceiling for a consumer/enterprise drive."""
    assert extract_ssd_capacity_gb("SSD 512GB, cod produs 1139000gb-serial-xyz") == 512


def test_extract_ssd_capacity_gb_ignores_hdd_capacity_in_mixed_listing():
    """Real bug: a server listing with a tiny boot SSD and a large HDD for
    storage ("SSD Corsair 32 GB ... HDD 3 TB WD") reported the HDD's 3TB
    as if it were the SSD capacity, because the old logic just took the
    largest GB/TB number in the whole text regardless of which drive it
    described. Must attribute each number to its NEAREST ssd/hdd keyword
    and ignore numbers that belong to an HDD mention."""
    text = (
        "server Dell Poweredge T20, procesor Intel Pentium G3220, "
        "SSD Corsair 32 GB pentru sistem de operare, "
        "HDD 3 TB WD (NASware) pentru stocare"
    )
    assert extract_ssd_capacity_gb(text) == 32


def test_ssd_deal_qualifying_listing_passes():
    assert passes_ssd_deal_filter(ssd_deal_listing(), SSD_CONFIG) is True


def test_ssd_deal_excludes_business_seller():
    listing = ssd_deal_listing(is_business=True)
    assert passes_ssd_deal_filter(listing, SSD_CONFIG) is False


def test_ssd_deal_excludes_over_price():
    listing = ssd_deal_listing(price=850)
    assert passes_ssd_deal_filter(listing, SSD_CONFIG) is False


def test_ssd_deal_excludes_hdd_only():
    listing = ssd_deal_listing(params={"tip_stocare": "HDD"})
    assert passes_ssd_deal_filter(listing, SSD_CONFIG) is False


def test_ssd_deal_accepts_hdd_plus_ssd_combo():
    listing = ssd_deal_listing(params={"tip_stocare": "HDD+SSD"})
    assert passes_ssd_deal_filter(listing, SSD_CONFIG) is True


def test_ssd_deal_accepts_standalone_drive_listing_schema(tmp_path):
    """Standalone SSD/HDD listings (sold as a bare component, not inside a
    laptop/PC) use a different OLX category with a different params schema:
    "tip" (SSD/HDD) instead of "tip_stocare", no capacity field at all."""
    conn = _conn_with_market_prices(tmp_path, capacity_bucket(960), [400, 420, 380, 410, 390])
    listing = ssd_deal_listing(
        title="SSD Kingston A400, 960GB, 2.5\", SATA III - Nou Sigilat",
        description="SSD nou, sigilat, garantie.",
        price=140,
        params={"state": "Nou", "tip": "SSD"},
    )
    assert passes_ssd_deal_filter(listing, SSD_CONFIG, conn) is True


def test_ssd_deal_excludes_standalone_hdd_listing():
    listing = ssd_deal_listing(
        title="Hard disk 4TB Seagate",
        description="HDD extern, functioneaza perfect.",
        price=400,
        params={"state": "Utilizat", "tip": "HDD"},
    )
    assert passes_ssd_deal_filter(listing, SSD_CONFIG) is False


# --- standalone-drive rule compares against a live market median (built
# from previously observed standalone-drive prices at the same capacity
# bucket), not the flat max_price used for laptops/PCs: a bare drive isn't
# "arbitrage" (the seller knows exactly what they're selling), so the bar
# is however cheap the *current real market* actually is for that size.


def test_standalone_drive_alerts_when_price_is_deep_discount_of_market_median(tmp_path):
    conn = _conn_with_market_prices(tmp_path, capacity_bucket(512), [300, 310, 290, 320, 280])
    listing = standalone_drive_listing(title="SSD Samsung 512GB SATA", price=180)  # 60% of 300
    assert passes_ssd_deal_filter(listing, SSD_CONFIG, conn) is True


def test_standalone_drive_rejects_price_above_discount_threshold(tmp_path):
    conn = _conn_with_market_prices(tmp_path, capacity_bucket(512), [300, 310, 290, 320, 280])
    listing = standalone_drive_listing(title="SSD Samsung 512GB SATA", price=190)
    assert passes_ssd_deal_filter(listing, SSD_CONFIG, conn) is False


def test_standalone_drive_rejects_when_too_few_market_samples(tmp_path):
    """Only 2 observed prices for this bucket -- not enough to trust a
    median, so no alert even at a very low price."""
    conn = _conn_with_market_prices(tmp_path, capacity_bucket(1000), [400, 420])
    listing = standalone_drive_listing(title="SSD Samsung 1TB NVMe", price=50)
    assert passes_ssd_deal_filter(listing, SSD_CONFIG, conn) is False


def test_standalone_drive_rejects_when_no_conn_given():
    listing = standalone_drive_listing(title="SSD Samsung 512GB SATA", price=1)
    assert passes_ssd_deal_filter(listing, SSD_CONFIG) is False


def test_standalone_drive_2tb_deal_works_same_as_any_other_size(tmp_path):
    """The whole point of the market-median approach: large capacities
    (2TB+) get real deals recognized too, not just whatever fixed tier
    someone guessed."""
    conn = _conn_with_market_prices(tmp_path, capacity_bucket(2000), [500, 520, 480, 510, 490])
    cheap = standalone_drive_listing(title="SSD Samsung 2TB NVMe", price=290)  # ~58% of 500
    assert passes_ssd_deal_filter(cheap, SSD_CONFIG, conn) is True

    not_cheap_enough = standalone_drive_listing(title="SSD Samsung 2TB NVMe", price=310)
    assert passes_ssd_deal_filter(not_cheap_enough, SSD_CONFIG, conn) is False


def test_standalone_drive_capacity_bucketing_pools_similar_sizes(tmp_path):
    """Real listings say "960GB" or "1TB" for what's the same drive size --
    both must land in the same market bucket."""
    conn = _conn_with_market_prices(tmp_path, capacity_bucket(1000), [400, 420, 380, 410, 390])
    listing = standalone_drive_listing(title="SSD Samsung 960GB NVMe", price=230)  # ~57% of 400
    assert passes_ssd_deal_filter(listing, SSD_CONFIG, conn) is True


def test_laptop_ssd_deal_still_uses_flat_max_price_not_market_median():
    """The market-median approach is standalone-drive-only. A laptop/PC
    listing with a huge SSD should still be judged against the flat
    ssd_deal max_price (800) -- a bundled system's price says nothing
    about the drive's own market value."""
    listing = ssd_deal_listing(
        title="Laptop HP i5, 2TB SSD",
        params={"tip_stocare": "SSD"},
        price=750,
    )
    assert passes_ssd_deal_filter(listing, SSD_CONFIG) is True


def test_ssd_deal_excludes_small_ssd():
    listing = ssd_deal_listing(title="Laptop HP i5, 256GB SSD")
    assert passes_ssd_deal_filter(listing, SSD_CONFIG) is False


def test_ssd_deal_excludes_when_capacity_not_mentioned_anywhere():
    listing = ssd_deal_listing(title="Laptop HP i5, SSD", description="Stare buna")
    assert passes_ssd_deal_filter(listing, SSD_CONFIG) is False


def test_ssd_deal_ignores_specs_entirely():
    """This rule doesn't care about CPU/RAM/model at all — only the SSD."""
    listing = ssd_deal_listing(
        title="Laptop Asus vechi, i3 gen 2, 4GB RAM, 512GB SSD"
    )
    assert passes_ssd_deal_filter(listing, SSD_CONFIG) is True


def test_ssd_deal_does_not_exclude_optional_disassembly_offer():
    """A seller offering to disassemble a complete, normally-priced system
    on request ("dezmembrez la cerere") is NOT the same as a part-out
    listing where the price only covers part of the machine — must not
    false-positive on the bare word "dezmembr"."""
    listing = ssd_deal_listing(
        title="Laptop HP i5-1035G1, 8GB, 512GB SSD",
        description="Stare buna, functioneaza perfect. La cerere pot sa il si dezmembrez.",
        price=700,
    )
    assert passes_ssd_deal_filter(listing, SSD_CONFIG) is True


def test_ssd_deal_excludes_part_out_listing():
    """Real bug: title mentions "1000GB SSD" but description makes clear the
    price is for the case+PSU only and everything else (including the drive)
    is negotiated separately — the SSD isn't actually for sale at that
    price."""
    listing = ssd_deal_listing(
        title="Dell Precision T3610 - statie PC TOP - 500 lei (1000GB SSD)",
        description=(
            "Atentie! Dezmembrez. 500 ron este pretul pentru carcasa + sursa. "
            "Pentru restul se negociaza."
        ),
        price=500,
    )
    assert passes_ssd_deal_filter(listing, SSD_CONFIG) is False
