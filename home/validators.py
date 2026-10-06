import logging
import time

import requests
from django.core.cache import cache

logger = logging.getLogger(__name__)

API_URL = "https://api.postalpincode.in/pincode/{pin}"
CITY_API_URL = "https://api.postalpincode.in/postoffice/{name}"
CACHE_SECONDS = 60 * 60 * 24 * 30

_session = requests.Session()
_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
})


def _table_loaded():
    from .models import Pincode
    return Pincode.objects.exists()


# ---------------------------------------------------------------- local DB
def _lookup_pincode_db(pin):
    from .models import Pincode
    rows = list(Pincode.objects.filter(pincode=pin))
    if not rows:
        return {}                      # table is loaded, PIN not in it
    places = set()
    for r in rows:
        for v in (r.district, r.division, r.region, r.office):
            if v and v != "na":
                places.add(v)
    return {"states": {r.state for r in rows}, "places": places}


def _lookup_city_states_db(city):
    from .models import Pincode
    states = set(
        Pincode.objects.filter(district=city).values_list("state", flat=True).distinct()
    )
    return states or None


# --------------------------------------------------------------- API fallback
def _fetch_json(url, label):
    for attempt in (1, 2):
        try:
            r = _session.get(url, timeout=6)
            r.raise_for_status()
            return r.json()[0]
        except (requests.RequestException, ValueError, IndexError) as exc:
            logger.warning("%s lookup failed (attempt %s): %s", label, attempt, exc)
            if attempt < 2:
                time.sleep(0.5)
    return None


def _lookup_pincode_api(pin):
    key = f"pincode:{pin}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    data = _fetch_json(API_URL.format(pin=pin), f"PIN {pin}")
    if data is None:
        return None

    if data.get("Status") != "Success" or not data.get("PostOffice"):
        result = {}
    else:
        offices = data["PostOffice"]
        places = set()
        for o in offices:
            for k in ("District", "Block", "Name", "Division", "Region"):
                v = (o.get(k) or "").strip().lower()
                if v and v != "na":
                    places.add(v)
        result = {
            "states": {o["State"].strip().lower() for o in offices},
            "places": places,
        }
    cache.set(key, result, CACHE_SECONDS)
    return result


def _lookup_city_states_api(city):
    key = f"citystates:{city}"
    cached = cache.get(key)
    if cached is not None:
        return cached or None

    data = _fetch_json(CITY_API_URL.format(name=city), f"City {city}")
    if data is None:
        return None

    states = set()
    if data.get("Status") == "Success":
        for o in data.get("PostOffice") or []:
            if (o.get("District") or "").strip().lower() == city:
                states.add(o["State"].strip().lower())
    cache.set(key, states, CACHE_SECONDS)
    return states or None


# ------------------------------------------------------------- public API
def lookup_pincode(pin):
    """None = couldn't verify, {} = PIN doesn't exist, else
    {'states': set, 'places': set}. Uses the local table when loaded."""
    if _table_loaded():
        return _lookup_pincode_db(pin)
    return _lookup_pincode_api(pin)


def lookup_city_states(city):
    """Set of lowercase state names where `city` is a postal district, or None."""
    if _table_loaded():
        return _lookup_city_states_db(city)
    return _lookup_city_states_api(city)