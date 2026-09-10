from olx_bot.filters import (
    extract_ssd_capacity_gb,
    passes_hard_filters,
    passes_ssd_deal_filter,
)

CONFIG = {"max_price": 1500}
SSD_CONFIG = {"ssd_deal": {"max_price": 800, "min_ssd_gb": 512}}


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
