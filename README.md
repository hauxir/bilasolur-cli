# bilasolur-cli

A command-line tool for searching vehicle listings on [bilasolur.is](https://bilasolur.is), the Icelandic vehicle marketplace.

The site is an ASP.NET WebForms app with no public API, so the CLI drives the same search form the browser does: it posts the advanced search (`Nákvæm leit`), follows the redirect to the stored result set, and parses the result and detail pages.

## Installation

Requires Python 3.12+.

```bash
pip install .
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv pip install .
```

No authentication is needed — everything the CLI reads is public.

## Commands

### Search

```bash
bilasolur search -m Toyota --year-from 2018
bilasolur search -m BMW --model X5 -f disel -s year-desc
bilasolur search -c Jeppi --price-to 4000000 -r Norðurland
bilasolur search --serial 357806
```

Makes, models, categories, colours, regions and dealers can be given by name or ID; names are
matched case-insensitively and a unique partial match is accepted.

| Option | Filter |
| --- | --- |
| `-m, --make`, `--model`, `--submodel` | Make (framleiðandi), model (gerð), sub-model text |
| `-c, --category` | Vehicle category — `bilasolur categories` |
| `--color`, `-r, --region` | Colour tone, region — `bilasolur colors` / `regions` |
| `-f, --fuel` | `bensin`, `disel`, `rafmagn`, `hybrid`, `plugin`, `metan` |
| `-d, --drive` | `fwd`, `rwd`, `awd` |
| `-t, --transmission` | `auto`, `manual` |
| `--year-from/-to`, `--price-from/-to`, `--km-from/-to` | Year, price in ISK, mileage in km |
| `--hp-from/-to`, `--seats-from/-to`, `--doors-from/-to` | Power, seats, doors |
| `--range-from`, `--battery-from` | Electric range (km), battery capacity (kWh) |
| `--tow-weight-from/-to` | Braked trailer capacity, in kg |
| `--dealer` | Restrict to one seller |
| `--new-only`, `--good-price`, `--tow-hitch`, `--on-site` | Boolean filters |
| `--updated-days` | Updated within 1, 7, 30, 60, 90 or 120 days |
| `-s, --sort` | Sort order — `bilasolur sorts` |
| `-p, --page`, `-l, --limit` | Paging (48 listings per page) and display cap |

The site only accepts range values from a fixed list (prices in 100k/1M steps, mileage in 10k steps,
and so on). Values that are not on that list are snapped to the nearest one that *widens* the range,
and the adjustment is printed so results are never silently dropped.

### A single listing

```bash
bilasolur car 357806        # by serial number (raðnúmer)
```

Shows registration, mileage, fuel, transmission, colour, inspection, price, seller and every
equipment section from the listing.

### Reference data

```bash
bilasolur makes             # all makes
bilasolur makes toy         # filtered by name
bilasolur models Tesla      # models for a make
bilasolur categories        # vehicle categories
bilasolur colors            # colour tones
bilasolur regions           # regions used by the location filter
bilasolur sorts             # available sort orders
bilasolur dealers           # dealer directory with contact details
bilasolur dealers -r Austurland
```

## JSON output

Every listing command supports `-j` / `--json-output` for raw JSON:

```bash
bilasolur search -m Tesla -j
bilasolur car 357806 -j
bilasolur dealers -j
```

## Development

```bash
pip install -e ".[dev]"
ruff check bilasolur_cli/
basedpyright
```

## License

MIT
