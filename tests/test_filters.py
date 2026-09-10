from olx_bot.filters import (
    extract_ssd_capacity_gb,
    passes_hard_filters,
    passes_ssd_deal_filter,
)

CONFIG = {"max_price": 1500}
SSD_CONFIG = {
    "ssd_deal": {
        "max_price": 800,
        "min_ssd_gb": 512,
        "standalone_drive_max_price_by_gb": {512: 150, 1000: 200, 2000: 300},
    }
}


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


def test_ssd_deal_accepts_standalone_drive_listing_schema():
    """Standalone SSD/HDD listings (sold as a bare component, not inside a
    laptop/PC) use a different OLX category with a different params schema:
    "tip" (SSD/HDD) instead of "tip_stocare", no capacity field at all."""
    listing = ssd_deal_listing(
        title="SSD Kingston A400, 960GB, 2.5\", SATA III - Nou Sigilat",
        description="SSD nou, sigilat, garantie.",
        price=140,
        params={"state": "Nou", "tip": "SSD"},
    )
    assert passes_ssd_deal_filter(listing, SSD_CONFIG) is True


def test_ssd_deal_excludes_standalone_hdd_listing():
    listing = ssd_deal_listing(
        title="Hard disk 4TB Seagate",
        description="HDD extern, functioneaza perfect.",
        price=400,
        params={"state": "Utilizat", "tip": "HDD"},
    )
    assert passes_ssd_deal_filter(listing, SSD_CONFIG) is False


# --- standalone-drive rule uses tiered pricing by capacity, not the flat
# max_price used for laptops/PCs: a bare drive isn't "arbitrage" (the
# seller knows exactly what they're selling), so the price bar is much
# lower and scales with how much storage you're actually getting.


def test_standalone_drive_512gb_tier_passes_under_threshold():
    listing = standalone_drive_listing(title="SSD Samsung 512GB SATA", price=149)
    assert passes_ssd_deal_filter(listing, SSD_CONFIG) is True


def test_standalone_drive_512gb_tier_fails_over_threshold():
    listing = standalone_drive_listing(title="SSD Samsung 512GB SATA", price=151)
    assert passes_ssd_deal_filter(listing, SSD_CONFIG) is False


def test_standalone_drive_1tb_tier_passes_under_threshold():
    listing = standalone_drive_listing(title="SSD Samsung 1TB NVMe", price=199)
    assert passes_ssd_deal_filter(listing, SSD_CONFIG) is True


def test_standalone_drive_1tb_tier_fails_over_threshold():
    listing = standalone_drive_listing(title="SSD Samsung 1TB NVMe", price=201)
    assert passes_ssd_deal_filter(listing, SSD_CONFIG) is False


def test_standalone_drive_2tb_tier_passes_under_threshold():
    listing = standalone_drive_listing(title="SSD Samsung 2TB NVMe", price=299)
    assert passes_ssd_deal_filter(listing, SSD_CONFIG) is True


def test_standalone_drive_2tb_tier_fails_over_threshold():
    listing = standalone_drive_listing(title="SSD Samsung 2TB NVMe", price=301)
    assert passes_ssd_deal_filter(listing, SSD_CONFIG) is False


def test_standalone_drive_extrapolates_threshold_beyond_largest_tier():
    """No 4TB tier is configured; extrapolate linearly from the rate
    between the two largest configured tiers (1TB->2TB: +100 lei per +1000GB,
    i.e. 0.1 lei/GB), so 4TB (2000GB past the 2TB tier) gets 300 + 200 = 500."""
    listing = standalone_drive_listing(title="SSD Samsung 4TB NVMe", price=499)
    assert passes_ssd_deal_filter(listing, SSD_CONFIG) is True

    listing = standalone_drive_listing(title="SSD Samsung 4TB NVMe", price=501)
    assert passes_ssd_deal_filter(listing, SSD_CONFIG) is False


def test_laptop_ssd_deal_still_uses_flat_max_price_not_tiers():
    """The tiered pricing is standalone-drive-only. A laptop/PC listing
    with a huge SSD should still be judged against the flat ssd_deal
    max_price (800), not the much stricter standalone tiers."""
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
