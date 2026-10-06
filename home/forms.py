import re

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

from .models import Customer, STATE_CHOICES
from .validators import lookup_pincode, lookup_city_states

STATE_NAMES = dict(STATE_CHOICES)


def norm(s):
    s = (s or "").lower().replace("&", "and")
    s = re.sub(r"[^a-z ]", "", s)
    return " ".join(s.split())


# state code -> acceptable India Post spellings (normalized)
ACCEPTED = {code: {norm(name)} for code, name in STATE_CHOICES}
ACCEPTED["PY"] = {"pondicherry", "puducherry"}
ACCEPTED["LA"] = {"ladakh", "jammu and kashmir"}  # some Ladakh PINs are still filed under J&K
_merged = "dadra and nagar haveli and daman and diu"
ACCEPTED["DN"] |= {_merged}
ACCEPTED["DD"] |= {_merged}


# Offline map of major, unambiguous cities -> state code. Works with no network.
CITY_STATE = {
    "mumbai": "MH", "pune": "MH", "nagpur": "MH", "nashik": "MH", "thane": "MH",
    "delhi": "DL", "new delhi": "DL",
    "bengaluru": "KA", "bangalore": "KA", "mysuru": "KA", "mysore": "KA",
    "mangaluru": "KA", "hubli": "KA",
    "chennai": "TN", "coimbatore": "TN", "madurai": "TN",
    "hyderabad": "TS", "warangal": "TS",
    "visakhapatnam": "AP", "vijayawada": "AP",
    "kolkata": "WB", "howrah": "WB", "siliguri": "WB",
    "ahmedabad": "GJ", "surat": "GJ", "vadodara": "GJ", "rajkot": "GJ",
    "jaipur": "RJ", "jodhpur": "RJ", "udaipur": "RJ",
    "lucknow": "UP", "kanpur": "UP", "varanasi": "UP", "agra": "UP", "noida": "UP",
    "bhopal": "MP", "indore": "MP",
    "patna": "BR", "ranchi": "JH",
    "chandigarh": "CH", "amritsar": "PB", "ludhiana": "PB",
    "gurugram": "HR", "gurgaon": "HR", "faridabad": "HR",
    "shimla": "HP", "dehradun": "UK",
    "kochi": "KL", "thiruvananthapuram": "KL", "kozhikode": "KL",
    "bhubaneswar": "OD", "guwahati": "AS", "raipur": "CG", "panaji": "GA",
}

# Offline fallback: first two digits of an Indian PIN -> possible state codes.
# Deliberately coarse (some prefixes are shared); only used when the PIN API is down.
PIN_PREFIX_STATES = {
    "11": {"DL"},
    "12": {"HR"}, "13": {"HR"},
    "14": {"PB"}, "15": {"PB"}, "16": {"PB", "CH", "HR"},
    "17": {"HP"},
    "18": {"JK"}, "19": {"JK", "LA"},
    **{str(p): {"UP", "UK"} for p in range(20, 29)},
    **{str(p): {"RJ"} for p in range(30, 35)},
    "36": {"GJ"}, "37": {"GJ"}, "38": {"GJ"}, "39": {"GJ", "DN", "DD"},
    "40": {"MH", "GA"}, "41": {"MH"}, "42": {"MH"}, "43": {"MH"}, "44": {"MH"},
    "45": {"MP"}, "46": {"MP"}, "47": {"MP"}, "48": {"MP"},
    "49": {"CG"},
    "50": {"TS", "AP"}, "51": {"AP", "TS"}, "52": {"AP", "TS"}, "53": {"AP"},
    "56": {"KA"}, "57": {"KA"}, "58": {"KA"}, "59": {"KA"},
    "60": {"TN"}, "61": {"TN"}, "62": {"TN"}, "63": {"TN"}, "64": {"TN", "PY"},
    "67": {"KL"}, "68": {"KL", "LD"}, "69": {"KL"},
    "70": {"WB"}, "71": {"WB"}, "72": {"WB"}, "73": {"WB", "SK"}, "74": {"WB", "AN"},
    "75": {"OD"}, "76": {"OD"}, "77": {"OD"},
    "78": {"AS"},
    "79": {"AR", "ML", "MN", "MZ", "NL", "TR", "AS"},
    "80": {"BR", "JH"}, "81": {"BR", "JH"}, "82": {"BR", "JH"},
    "83": {"JH"}, "84": {"BR"}, "85": {"BR", "JH"},
}


def normalize_indian_mobile(raw):
    """Accepts '98765 43210', '+91-98765-43210', '09876543210', '919876543210'
    and returns the bare 10 digits. Raises ValidationError if it isn't a
    plausible Indian mobile number."""
    digits = re.sub(r"\D", "", raw or "")

    if len(digits) == 12 and digits.startswith("91"):      # +91 / 91 prefix
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):     # trunk prefix 0
        digits = digits[1:]

    if not re.fullmatch(r"[6-9]\d{9}", digits):
        raise ValidationError("Enter a valid 10-digit Indian mobile number.")
    if len(set(digits)) == 1:                              # 9999999999 etc.
        raise ValidationError("Enter a valid 10-digit Indian mobile number.")
    return digits


def city_matches(city, places):
    """Whole-word match (not raw substring) between the typed city and any
    place name returned for the PIN."""
    if len(city) < 3:
        return False
    padded_city = f" {city} "
    for p in places:
        padded_p = f" {p} "
        if city == p or padded_city in padded_p or padded_p in padded_city:
            return True
    return False


class CustomerForm(forms.ModelForm):
    zipcode = forms.CharField(
        validators=[RegexValidator(r"^\d{6}$", "Enter a valid 6-digit PIN code.")]
    )
    # No regex validator: field validators run on the RAW input, which would
    # reject "+91 98765 43210" before we can normalize it.
    phone = forms.CharField(max_length=20)

    class Meta:
        model = Customer
        fields = ["name", "phone", "address", "city", "zipcode", "state"]

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_phone(self):
        phone = normalize_indian_mobile(self.cleaned_data["phone"])

        taken = Customer.objects.filter(phone=phone)
        if self.user is not None:
            taken = taken.exclude(user=self.user)
        if taken.exists():
            raise ValidationError(
                "This mobile number is already registered with another account."
            )
        return phone  # stored as bare 10 digits

    def clean(self):
        cleaned = super().clean()
        pin = cleaned.get("zipcode")
        city = norm(cleaned.get("city"))
        code = cleaned.get("state")

        # 1) City vs state: independent of the PIN lookup ------------------
        state_error_added = False
        if city and code:
            expected = CITY_STATE.get(city)
            if expected:
                if expected != code:
                    self.add_error(
                        "state",
                        f"{city.title()} is in {STATE_NAMES[expected]}, "
                        f"not {STATE_NAMES.get(code, code)}."
                    )
                    state_error_added = True
            else:
                states = lookup_city_states(city)
                if states and not (states & ACCEPTED.get(code, set())):
                    self.add_error(
                        "state",
                        f"{city.title()} is in "
                        f"{', '.join(s.title() for s in sorted(states))}, "
                        f"not {STATE_NAMES.get(code, code)}."
                    )
                    state_error_added = True

        if not pin:
            return cleaned

        # 2) PIN checks ----------------------------------------------------
        info = lookup_pincode(pin)

        if info is not None and not info:
            self.add_error("zipcode", "This PIN code does not exist.")
            return cleaned

        # API down: rough offline state check; city can't be verified
        if info is None:
            allowed = PIN_PREFIX_STATES.get(pin[:2])
            if code and not state_error_added and allowed and code not in allowed:
                self.add_error(
                    "state",
                    f"PIN code {pin} doesn't look like it belongs to "
                    f"{STATE_NAMES.get(code, code)}."
                )
            elif getattr(settings, "PINCODE_STRICT", True) and not self.errors:
                raise ValidationError(
                    "We couldn't verify your PIN code and city right now. "
                    "Please try again in a moment."
                )
            return cleaned

        # API up: check PIN against state and city independently
        if code and not state_error_added:
            api_states = {norm(s) for s in info["states"]}
            if not (api_states & ACCEPTED.get(code, set())):
                self.add_error(
                    "state",
                    f"This PIN code belongs to "
                    f"{', '.join(s.title() for s in sorted(api_states))}, "
                    f"not {STATE_NAMES.get(code, code)}."
                )

        if city and not city_matches(city, info["places"]):
            self.add_error("city", "City doesn't match this PIN code.")

        return cleaned