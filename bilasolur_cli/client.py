import re
from html import unescape
from typing import Any

import httpx

BASE_URL = "https://bilasolur.is"

# The search form is an ASP.NET WebForms page: every control is prefixed with the
# naming container of the "Nakvaem leit" user control.
FORM_PREFIX = "ctl00$contentSearchEngine$searchCars$"

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# Checkbox fields, keyed by the CLI-facing name.
FUEL_FIELDS = {
    "bensin": "search_ft_0",
    "disel": "search_ft_1",
    "rafmagn": "search_fe",
    "hybrid": "search_fh",
    "plugin": "search_fph",
    "metan": "search_fth_4",
}
DRIVE_FIELDS = {
    "fwd": "search_drv_1",
    "rwd": "search_drv_2",
    "awd": "search_drv_4",
}
TRANSMISSION_FIELDS = {
    "auto": "search_xma",
    "manual": "search_xmm",
}
FLAG_FIELDS = {
    "new_only": "search_n",
    "good_price": "search_off",
    "tow_hitch": "search_db",
    "on_site": "search_p",
    "trade_down": "search_td",
    "trade_up": "search_tu",
}

# Range fields: cli name -> (form field, divisor applied to the user's value).
RANGE_FIELDS: dict[str, tuple[str, int]] = {
    "year_from": ("search_arf", 1),
    "year_to": ("search_art", 1),
    "price_from": ("search_vf", 1000),
    "price_to": ("search_vt", 1000),
    "km_from": ("search_ef", 1000),
    "km_to": ("search_et", 1000),
    "hp_from": ("search_hpf", 1),
    "hp_to": ("search_hpt", 1),
    "cc_from": ("search_ccf", 1),
    "cc_to": ("search_cct", 1),
    "co2_from": ("search_co2f", 1),
    "co2_to": ("search_co2t", 1),
    "seats_from": ("search_pf", 1),
    "seats_to": ("search_pt", 1),
    "doors_from": ("search_df", 1),
    "doors_to": ("search_dt", 1),
    "battery_from": ("search_bcf", 1),
    "battery_to": ("search_bct", 1),
    "range_from": ("search_brf", 1),
    "range_to": ("search_brt", 1),
    "weight_from": ("search_tf", 1),
    "weight_to": ("search_tt", 1),
    "tow_weight_from": ("search_dgfh", 1),
    "tow_weight_to": ("search_dgth", 1),
}

# Sort keys -> the label bilasolur.is uses in the sort dropdown.
SORT_LABELS = {
    "price-asc": "Verð, lægsta fyrst",
    "price-desc": "Verð, hæsta fyrst",
    "year-asc": "Árgerð, elsta fyrst",
    "year-desc": "Árgerð, nýjasta fyrst",
    "km": "Akstur",
    "make": "Framleiðandi",
    "newest": "Skráð á söluskrá, nýjasta fyrst",
    "battery": "Stærð rafhlöðu",
    "range": "Drægni rafhlöðu",
}

_RE_HIDDEN = r'id="{}"[^>]*value="([^"]*)"'
_RE_SELECT = r'<select[^>]*id="{}"[^>]*>(.*?)</select>'
_RE_OPTION = re.compile(r'<option[^>]*value="([^"]*)"[^>]*>(.*?)</option>', re.S)
_RE_LABEL = re.compile(r'<label for="ctl00_contentSearchEngine_searchCars_(search_\w+)"[^>]*>(.*?)</label>', re.S)
_RE_SORT_CURRENT = re.compile(r'class="nav-link dropdown-toggle"[^>]*>\s*<i[^>]*></i>\s*([^<]+)</a>')
_RE_SORT_ITEM = re.compile(
    r'href="javascript:__doPostBack\(&#39;(ctl00\$contentCenter\$searchResults\$ctl\d+)&#39;,&#39;&#39;\)"[^>]*>\s*(?:<i[^>]*></i>)?\s*([^<]+)</a>'
)


class BilasolurError(Exception):
    """Raised when the site cannot fulfil a request as asked."""


def _text(raw: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", raw)).replace("\xa0", " ").strip()


class BilasolurClient:
    def __init__(self) -> None:
        self._client = httpx.Client(
            timeout=30.0,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json;q=0.9"},
            follow_redirects=False,
        )
        self._form: str | None = None
        self.adjustments: list[str] = []

    def __enter__(self) -> "BilasolurClient":
        return self

    def __exit__(self, *_: object) -> None:
        self._client.close()

    def close(self) -> None:
        self._client.close()

    # === Low level ===

    def _get(self, path: str) -> str:
        r = self._client.get(f"{BASE_URL}/{path.lstrip('/')}")
        r.raise_for_status()
        return r.text

    def _form_page(self) -> str:
        """The advanced search page, cached: it carries the viewstate and every option list."""
        if self._form is None:
            self._form = self._get("SearchCars.aspx")
        return self._form

    @staticmethod
    def _hidden(html: str, name: str) -> str:
        m = re.search(_RE_HIDDEN.format(name), html)
        return unescape(m.group(1)) if m else ""

    @staticmethod
    def _options(html: str, element_id: str) -> list[tuple[str, str]]:
        m = re.search(_RE_SELECT.format(re.escape(element_id)), html, re.S)
        if not m:
            return []
        return [(v, _text(t)) for v, t in _RE_OPTION.findall(m.group(1)) if v not in ("-1", "")]

    @staticmethod
    def _checkbox_group(html: str, prefix: str) -> list[tuple[str, str]]:
        found = [(f, _text(t)) for f, t in _RE_LABEL.findall(html) if f.startswith(prefix)]
        return sorted(dict(found).items(), key=lambda kv: int(kv[0].rsplit("_", 1)[1]))

    # === Reference data ===

    def makes(self) -> list[dict[str, str]]:
        """All vehicle makes (framleiðendur)."""
        return [{"id": v, "name": n} for v, n in self._options(self._form_page(), "search_f1")]

    def models(self, make_id: str) -> list[dict[str, str]]:
        """Models for a make, via the site's own AJAX endpoint."""
        r = self._client.post(
            f"{BASE_URL}/Functions.aspx/GetModelsFromMake",
            json={"sid": "", "mid": str(make_id), "rto": "search_g1"},
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        r.raise_for_status()
        flat: list[str] = r.json()["d"]
        pairs = list(zip(flat[1::2], flat[2::2], strict=False))
        return [{"id": v, "name": n} for v, n in pairs if v not in ("-1", "")]

    def categories(self) -> list[dict[str, str]]:
        """Vehicle categories (Fólksbíll, Jeppi, ...)."""
        return [
            {"id": f.rsplit("_", 1)[1], "name": n} for f, n in self._checkbox_group(self._form_page(), "search_cat_")
        ]

    def colors(self) -> list[dict[str, str]]:
        """Colour tones (litatónn)."""
        return [
            {"id": f.rsplit("_", 1)[1], "name": n} for f, n in self._checkbox_group(self._form_page(), "search_col_")
        ]

    def regions(self) -> list[dict[str, str]]:
        """Regions of Iceland used for the location filter."""
        return [
            {"id": f.rsplit("_", 1)[1], "name": n} for f, n in self._checkbox_group(self._form_page(), "search_reg_")
        ]

    def dealer_options(self) -> list[dict[str, str]]:
        """Dealers as listed in the search form's seller dropdown."""
        return [{"id": v, "name": n} for v, n in self._options(self._form_page(), "search_btshid") if v != "-1"]

    def allowed_values(self, cli_name: str) -> list[int]:
        """The values the site accepts for a range field; anything else is silently ignored."""
        field, _ = RANGE_FIELDS[cli_name]
        values = [
            int(v)
            for v, _ in self._options(self._form_page(), f"ctl00_contentSearchEngine_searchCars_{field}")
            if v.lstrip("-").isdigit()
        ]
        return sorted(v for v in values if v > 0)

    # === Search ===

    def resolve(self, options: list[dict[str, str]], value: str, kind: str) -> str:
        if value.isdigit() and any(o["id"] == value for o in options):
            return value
        lowered = value.casefold()
        exact = [o for o in options if o["name"].casefold() == lowered]
        if exact:
            return exact[0]["id"]
        partial = [o for o in options if lowered in o["name"].casefold()]
        if len(partial) == 1:
            return partial[0]["id"]
        if len(partial) > 1:
            names = ", ".join(o["name"] for o in partial[:10])
            raise BilasolurError(f"{kind} '{value}' is ambiguous: {names}")
        raise BilasolurError(f"Unknown {kind}: '{value}'")

    def _snap(self, cli_name: str, value: int, label: str) -> str:
        """Snap a value onto the site's option list, widening the range rather than narrowing it."""
        _, divisor = RANGE_FIELDS[cli_name]
        wanted = value // divisor
        allowed = self.allowed_values(cli_name)
        if not allowed or wanted in allowed:
            return str(wanted)
        if cli_name.endswith("_from"):
            candidates = [v for v in allowed if v <= wanted]
            snapped = candidates[-1] if candidates else allowed[0]
        else:
            candidates = [v for v in allowed if v >= wanted]
            snapped = candidates[0] if candidates else allowed[-1]
        self.adjustments.append(f"{label} {wanted * divisor:,} -> {snapped * divisor:,}")
        return str(snapped)

    def search(
        self,
        *,
        make: str | None = None,
        model: str | None = None,
        submodel: str | None = None,
        serial: str | None = None,
        dealer: str | None = None,
        category: tuple[str, ...] = (),
        color: tuple[str, ...] = (),
        region: tuple[str, ...] = (),
        fuel: tuple[str, ...] = (),
        drive: tuple[str, ...] = (),
        transmission: tuple[str, ...] = (),
        flags: tuple[str, ...] = (),
        updated_days: int | None = None,
        ranges: dict[str, int] | None = None,
    ) -> str:
        """Run a search and return the id of the stored result set."""
        self.adjustments = []
        html = self._form_page()
        data: dict[str, str] = {
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": self._hidden(html, "__VIEWSTATE"),
            "__VIEWSTATEGENERATOR": self._hidden(html, "__VIEWSTATEGENERATOR"),
            f"{FORM_PREFIX}btnSearch": "Leita",
        }

        if make:
            make_id = self.resolve(self.makes(), make, "make")
            data[f"{FORM_PREFIX}search_f1"] = make_id
            if model:
                data[f"{FORM_PREFIX}search_g1"] = self.resolve(self.models(make_id), model, "model")
        elif model:
            raise BilasolurError("--model needs --make as well")
        if submodel:
            data[f"{FORM_PREFIX}search_ug1"] = submodel
        if serial:
            data[f"{FORM_PREFIX}search_cid"] = serial
        if dealer:
            data[f"{FORM_PREFIX}search_btshid"] = self.resolve(self.dealer_options(), dealer, "dealer")
        if updated_days is not None:
            data[f"{FORM_PREFIX}search_modage"] = str(updated_days)

        for values, options, field, kind in (
            (category, self.categories(), "search_cat_", "category"),
            (color, self.colors(), "search_col_", "colour"),
            (region, self.regions(), "search_reg_", "region"),
        ):
            for value in values:
                data[f"{FORM_PREFIX}{field}{self.resolve(options, value, kind)}"] = "on"

        for values, mapping, kind in (
            (fuel, FUEL_FIELDS, "fuel"),
            (drive, DRIVE_FIELDS, "drivetrain"),
            (transmission, TRANSMISSION_FIELDS, "transmission"),
        ):
            for value in values:
                if value not in mapping:
                    raise BilasolurError(f"Unknown {kind} '{value}' (pick from: {', '.join(mapping)})")
                data[f"{FORM_PREFIX}{mapping[value]}"] = "on"

        for flag in flags:
            data[f"{FORM_PREFIX}{FLAG_FIELDS[flag]}"] = "on"

        for name, value in (ranges or {}).items():
            data[f"{FORM_PREFIX}{RANGE_FIELDS[name][0]}"] = self._snap(name, value, name.replace("_", " "))

        r = self._client.post(f"{BASE_URL}/SearchCars.aspx", data=data)
        return self._search_id(r)

    @staticmethod
    def _search_id(response: httpx.Response) -> str:
        location = response.headers.get("location", "")
        m = re.search(r"id=([0-9a-f-]{36})", location)
        if not m:
            raise BilasolurError("bilasolur.is did not return a search result set")
        return m.group(1)

    def results_page(self, search_id: str, page: int = 1) -> str:
        suffix = f"page={page}&" if page > 1 else ""
        return self._get(f"SearchResults.aspx?{suffix}id={search_id}")

    def sort(self, search_id: str, sort_key: str) -> str:
        """Re-sort a stored result set; returns the id of the re-sorted set."""
        if sort_key not in SORT_LABELS:
            raise BilasolurError(f"Unknown sort '{sort_key}' (pick from: {', '.join(SORT_LABELS)})")
        target_label = SORT_LABELS[sort_key]
        html = self.results_page(search_id)
        current = _RE_SORT_CURRENT.search(html)
        if current and _text(current.group(1)) == target_label:
            return search_id
        for target, label in _RE_SORT_ITEM.findall(html):
            if _text(label) == target_label:
                url = f"{BASE_URL}/SearchResults.aspx?id={search_id}"
                r = self._client.post(
                    url,
                    data={
                        "__EVENTTARGET": target,
                        "__EVENTARGUMENT": "",
                        "__VIEWSTATE": self._hidden(html, "__VIEWSTATE"),
                        "__VIEWSTATEGENERATOR": self._hidden(html, "__VIEWSTATEGENERATOR"),
                    },
                )
                return self._search_id(r)
        raise BilasolurError(f"Sort '{sort_key}' is not offered for this result set")

    # === Detail pages ===

    def car_page(self, bid: str, cid: str, sid: str) -> str:
        return self._get(f"CarDetails.aspx?bid={bid}&cid={cid}&sid={sid}")

    def find_by_serial(self, serial: str) -> dict[str, Any]:
        """Look up a single listing by its raðnúmer."""
        cars = parse_results(self.results_page(self.search(serial=serial)))
        if not cars:
            raise BilasolurError(f"No listing with serial number {serial}")
        return cars[0]

    def dealers_page(self, region: str | None = None) -> str:
        if region:
            return self._get(f"ListServiceProviders.aspx?o=r&t=9&r={region}")
        return self._get("ListServiceProviders.aspx?o=n&t=9&r=-1")


# === Parsing ===


def car_url(bid: str, cid: str, sid: str) -> str:
    return f"{BASE_URL}/CarDetails.aspx?bid={bid}&cid={cid}&sid={sid}"


_RE_CARD_LINK = re.compile(r'class="sr-link" href="(CarDetails\.aspx\?[^"]+)"')
_RE_CARD_IDS = re.compile(r'name="rnr_(\d+)_(\d+)_(\d+)"')
_RE_CARD_MAKE = re.compile(r'class="car-make-and-model"><span class="car-make">([^<]*)</span>\s*([^<]*)</div>')
_RE_CARD_NOTE = re.compile(r'class="short-note">(.*?)</div>', re.S)
_RE_CARD_TECH = re.compile(r'class="tech-details">((?:<div>.*?</div>)+)</div>', re.S)
_RE_CARD_TECH_ITEM = re.compile(r"<div>(.*?)</div>", re.S)
_RE_CARD_PRICE = re.compile(r'class="car-price">kr\.\s*<span[^>]*>([\d.]+)')
_RE_CARD_IMG = re.compile(r'class="swiper-slide" src="([^"]+)"')
_RE_CARD_PILL = re.compile(r'class="pill pill-[a-z-]+" title="([^"]*)"')
_RE_NEXT_PAGE = re.compile(r'href="SearchResults\.aspx\?page=(\d+)&amp;id=')


def parse_results(html: str) -> list[dict[str, Any]]:
    """Parse the listing cards out of a SearchResults page."""
    cards: list[dict[str, Any]] = []
    for chunk in html.split('<a class="car-anchor"')[1:]:
        ids = _RE_CARD_IDS.search(chunk)
        if not _RE_CARD_LINK.search(chunk) or not ids:
            continue
        make_model = _RE_CARD_MAKE.search(chunk)
        tech_block = _RE_CARD_TECH.search(chunk)
        tech = [_text(t) for t in _RE_CARD_TECH_ITEM.findall(tech_block.group(1))] if tech_block else []
        head = [p.strip() for p in tech[0].split("·")] if tech else []
        note = _RE_CARD_NOTE.search(chunk)
        price = _RE_CARD_PRICE.search(chunk)
        image = _RE_CARD_IMG.search(chunk)
        cards.append(
            {
                "serial": ids.group(2),
                "bid": ids.group(1),
                "sid": ids.group(3),
                "make": _text(make_model.group(1)) if make_model else "",
                "model": _text(make_model.group(2)) if make_model else "",
                "note": _text(note.group(1)) if note else "",
                "registered": head[0] if head else "",
                "mileage": head[1] if len(head) > 1 else "",
                "fuel": tech[1] if len(tech) > 1 else "",
                "drivetrain": tech[2] if len(tech) > 2 else "",
                "price": price.group(1) if price else "",
                "image": image.group(1) if image else "",
                "tags": [_text(t) for t in _RE_CARD_PILL.findall(chunk)],
                "url": car_url(ids.group(1), ids.group(2), ids.group(3)),
            }
        )
    return cards


def has_next_page(html: str) -> bool:
    return bool(_RE_NEXT_PAGE.search(html))


_RE_CD_MAKE = re.compile(r'class="col cd-make-and-model"><span class="car-make">([^<]*)</span>\s*([^<]*)</div>')
_RE_CD_SERIAL = re.compile(r'class="serial-number"><span[^>]*>[^<]*</span><br />(\d+)')
_RE_CD_PRICE = re.compile(r'class="cd-price">([\d.]+)')
_RE_CD_PRICE_NOTE = re.compile(r'class="font-size-small text-overflow-ellipsis">(.*?)</div>', re.S)
_RE_CD_SELLER = re.compile(r'class="seller-name"><a href="([^"]*)">(.*?)</a>', re.S)
_RE_CD_SELLER_ADDR = re.compile(r'class="seller-address"><div>(.*?)</div>', re.S)
_RE_CD_NOTE = re.compile(r'class="row mt-3 text-overflow-ellipsis"><div class="col-12">(.*?)</div>', re.S)
_RE_CD_TAG = re.compile(r'<i class="bisicon bi-[a-z-]+"></i>\s*([^<]+)<')
_RE_CD_PHOTO = re.compile(r'class="pswp-popup-area cd-car-photo[^"]*"[^>]*src="([^"]+)"')
_RE_CD_SECTION = re.compile(
    r'class="cd-section-title">(.*?)</div>(.*?)(?=class="cd-section-title">|<div class="footer")', re.S
)
_RE_CD_SPEC = re.compile(r'class="mb-1">(.*?)</div>', re.S)
_RE_CD_FIELDS = {
    "registered": re.compile(r"Nýskráning(?:&nbsp;|\s)*<span class=\"font-weight-bold\">([^<]*)</span>"),
    "mileage": re.compile(r"Akstur(?:&nbsp;|\s)*<span class=\"font-weight-bold\">([^<]*)</span>"),
    "inspection": re.compile(r"Næsta skoðun(?:&nbsp;|\s)*([^<]+)<"),
    "color": re.compile(r"Litur\s*<span class=\"font-weight-bold\">([^<]*)</span>"),
    "listed": re.compile(r"Skráð á söluskrá\s*([^<]+)<"),
    "updated": re.compile(r"Síðast uppfært\s*([^<]+)<"),
    "fuel": re.compile(r'class="col-6 text-right"><span class="font-weight-bold">([^<]*)</span>'),
    "transmission": re.compile(r'class="col-6 font-weight-bold">([^<]*)</div>'),
}


def parse_car(html: str) -> dict[str, Any]:
    """Parse a CarDetails page into a flat record plus its spec sections."""
    make_model = _RE_CD_MAKE.search(html)
    seller = _RE_CD_SELLER.search(html)
    addr = _RE_CD_SELLER_ADDR.search(html)
    price = _RE_CD_PRICE.search(html)
    price_note = _RE_CD_PRICE_NOTE.search(html)
    serial = _RE_CD_SERIAL.search(html)
    note = _RE_CD_NOTE.search(html)

    car: dict[str, Any] = {
        "serial": serial.group(1) if serial else "",
        "make": _text(make_model.group(1)) if make_model else "",
        "model": _text(make_model.group(2)) if make_model else "",
        "note": _text(note.group(1)) if note else "",
        "price": price.group(1) if price else "",
        "price_note": _text(price_note.group(1)) if price_note else "",
        "seller": _text(seller.group(2)) if seller else "",
        "seller_url": f"{BASE_URL}/{unescape(seller.group(1))}" if seller else "",
        "seller_address": _text(addr.group(1)) if addr else "",
        "tags": [_text(t) for t in _RE_CD_TAG.findall(html)],
        "photos": [unescape(p) for p in _RE_CD_PHOTO.findall(html)],
    }
    for key, rx in _RE_CD_FIELDS.items():
        m = rx.search(html)
        car[key] = _text(m.group(1)) if m else ""
    car["specs"] = {
        _text(title): [_text(s) for s in _RE_CD_SPEC.findall(body)] for title, body in _RE_CD_SECTION.findall(html)
    }
    return car


_RE_DEALER_NAME = re.compile(r'<span class="font-weight-bold">(.*?)</span><br/>\s*(.*?)<br />', re.S)
_RE_DEALER_PHONE = re.compile(r'<a href="tel:[^"]*">(.*?)</a>', re.S)
_RE_DEALER_SITE = re.compile(r'<a href="(https?://[^"]+)" target="_blank">')
_RE_DEALER_MAIL = re.compile(r'href="mailto:([^"]+)"')
_RE_DEALER_ID = re.compile(r"BilasalaDetails\.aspx\?g?id=([0-9a-f-]+)")


def parse_dealers(html: str) -> list[dict[str, str]]:
    """Parse the dealer directory."""
    dealers: list[dict[str, str]] = []
    for chunk in html.split("section-margin-below text-center mobile-separator")[1:]:
        name = _RE_DEALER_NAME.search(chunk)
        if not name:
            continue
        phone = _RE_DEALER_PHONE.search(chunk)
        site = _RE_DEALER_SITE.search(chunk)
        mail = _RE_DEALER_MAIL.search(chunk)
        dealer_id = _RE_DEALER_ID.search(chunk)
        dealers.append(
            {
                "id": dealer_id.group(1) if dealer_id else "",
                "name": _text(name.group(1)),
                "address": _text(name.group(2)),
                "phone": _text(phone.group(1)) if phone else "",
                "website": unescape(site.group(1)) if site else "",
                "email": unescape(mail.group(1)) if mail else "",
            }
        )
    return dealers
