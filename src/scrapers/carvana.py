"""
Carvana scraper.

Carvana is an online-only used-car retailer — any listing is delivered to
your door so distance-from-Sachse isn't really meaningful. They include
shipping in the headline price. Inventory is modern used (no pre-2005
cars), but they do carry plenty of manual-transmission enthusiast cars
that match our targets: late-model Miatas, BRZ/FR-S/86, 370Z, WRX/STI,
GTI, Golf R, S2000, Civic Si, Boxster/Cayman.

Results pages embed ld+json Vehicle entries per result card:
  <script type="application/ld+json">
    {"@type":"Vehicle","name":"2019 Mazda MX-5 Miata","modelDate":2019,
     "mileageFromOdometer":26335,"offers":{"@type":"Offer","price":...},
     "brand":"Mazda","model":"MX-5 Miata","vehicleIdentificationNumber":"..."}
  </script>

We iterate each target model, hit the filter URL with make/model slug,
parse every ld+json Vehicle, and dedupe by VIN.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional
from urllib.parse import quote

from bs4 import BeautifulSoup

from ..models import Listing
from .base import make_session, polite_get, parse_mileage, parse_year

log = logging.getLogger(__name__)

BASE = "https://www.carvana.com"


def _slug(s: str) -> str:
    """Convert 'Mazda MX-5 Miata' -> 'mx-5-miata' style Carvana slug."""
    s = s.lower().strip()
    s = re.sub(r"[^\w\-\s]", "", s)        # drop non-word chars
    s = re.sub(r"\s+", "-", s)
    return s


def _build_search_url(make: Optional[str], model: Optional[str],
                      max_price: int) -> str:
    """Carvana URL scheme examples:
       /cars/filters/transmission-manual?maxPrice=23000
       /cars/make-mazda/model-mx-5-miata?transmission=manual&maxPrice=23000
    """
    path = "/cars"
    if make:
        path += f"/make-{_slug(make)}"
    if model:
        path += f"/model-{_slug(model)}"
    path += "/filters/transmission-manual"
    return f"{BASE}{path}?maxPrice={max_price}"


def _target_to_make_model(target: str) -> tuple[Optional[str], Optional[str]]:
    """Split 'Mazda Miata' -> ('Mazda', 'Miata'). First token = make. Returns
    (None, None) for classics Carvana won't have."""
    toks = target.split()
    if len(toks) < 2:
        return None, None
    # Carvana doesn't carry pre-2005 cars — skip classics up front.
    classic_makes = {"Datsun", "MG", "Triumph", "Alfa", "Lotus"}
    if toks[0] in classic_makes:
        return None, None
    # Normalize a few edge cases
    make = toks[0]
    model = " ".join(toks[1:])
    # Carvana often spells "Mazda Miata" as "MX-5 Miata"
    if make == "Mazda" and model == "Miata":
        model = "MX-5 Miata"
    if make == "Scion":
        # Scion brand rolled into Toyota at Carvana
        make, model = "Toyota", "86"
    if make == "VW":
        make = "Volkswagen"
    return make, model


def _parse_ld_vehicles(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    for tag in soup.find_all("script", type="application/ld+json"):
        txt = tag.string or tag.get_text() or ""
        if not txt.strip():
            continue
        try:
            d = json.loads(txt)
        except json.JSONDecodeError:
            continue
        if isinstance(d, list):
            items = d
        elif isinstance(d, dict):
            items = [d]
        else:
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            if str(it.get("@type", "")).lower() in ("vehicle", "car", "product"):
                out.append(it)
    return out


def _normalize(item: dict) -> Optional[Listing]:
    name = item.get("name") or ""
    if not name:
        return None

    # URL — Carvana embeds it inside image tags / detail pages. Try multiple.
    url = item.get("url") or ""
    if not url:
        # ld+json doesn't always include the URL — scan for vehicleID
        sku = item.get("sku") or item.get("vehicleIdentificationNumber") or ""
        sku_str = str(sku) if sku else ""
        if sku_str and sku_str.isdigit():
            url = f"{BASE}/vehicle/{sku_str}"
    if url and not url.startswith("http"):
        url = f"{BASE}{url}" if url.startswith("/") else ""

    # Fall back to a search URL if we have nothing — better than nothing
    if not url:
        url = f"{BASE}/cars?q={quote(name)}"

    # Price from offers
    price: Optional[int] = None
    offers = item.get("offers")
    if isinstance(offers, dict):
        p = offers.get("price")
        try:
            price = int(float(p)) if p is not None else None
        except (TypeError, ValueError):
            price = None
        if price and (price < 500 or price > 500_000):
            price = None

    # Year
    year = item.get("modelDate") or item.get("vehicleModelDate")
    try:
        year = int(year) if year is not None else parse_year(name)
    except (TypeError, ValueError):
        year = parse_year(name)

    # Make / model
    make = item.get("brand")
    if isinstance(make, dict):
        make = make.get("name")
    model = item.get("model")
    if isinstance(model, dict):
        model = model.get("name")

    # Mileage
    mileage = None
    m_field = item.get("mileageFromOdometer")
    if isinstance(m_field, dict):
        try:
            mileage = int(float(m_field.get("value", 0))) or None
        except (TypeError, ValueError):
            mileage = None
    elif m_field is not None:
        try:
            mileage = int(float(m_field))
        except (TypeError, ValueError):
            mileage = parse_mileage(str(m_field))

    vin = item.get("vehicleIdentificationNumber") or item.get("sku")

    # Carvana images
    images: list[str] = []
    img = item.get("image")
    if isinstance(img, str):
        images = [img]
    elif isinstance(img, list):
        images = [x for x in img if isinstance(x, str)][:3]

    return Listing(
        source="carvana",
        url=url,
        title=str(name),
        price=price,
        price_type="asking",
        year=year if isinstance(year, int) else None,
        make=str(make) if isinstance(make, str) else None,
        model=str(model) if isinstance(model, str) else None,
        mileage=mileage,
        transmission="manual",                  # we filter server-side
        location="Online (delivered to you)",
        distance_miles=None,                    # Carvana delivers — N/A
        description=str(item.get("description") or "")[:400],
        images=images,
        raw_id=str(vin or ""),
        shipping_estimate_usd=0,                # Carvana includes delivery
    )


def scrape(criteria: dict, target_models: list[str]) -> list[Listing]:
    session = make_session()
    session.headers.update({"Referer": f"{BASE}/"})

    max_price = criteria.get("max_price", 23000)

    out: list[Listing] = []
    seen_vins: set[str] = set()

    # One fetch per target make+model
    for target in target_models:
        make, model = _target_to_make_model(target)
        if not make:
            # Skip classic-makes Carvana doesn't carry (Datsun, Triumph, MG, etc.)
            continue
        url = _build_search_url(make, model, max_price)
        log.info("carvana: %r (%s/%s)", target, make, model)
        resp = polite_get(session, url, sleep=1.2, timeout=25)
        if resp is None:
            continue

        items = _parse_ld_vehicles(resp.text)
        for item in items:
            listing = _normalize(item)
            if listing is None:
                continue
            if listing.price and listing.price > max_price * 1.1:
                continue
            # Dedup by VIN
            if listing.raw_id and listing.raw_id in seen_vins:
                continue
            if listing.raw_id:
                seen_vins.add(listing.raw_id)
            listing.model = target
            out.append(listing)

    log.info("carvana total listings: %d", len(out))
    return out
