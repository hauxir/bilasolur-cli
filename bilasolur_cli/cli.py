import json
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from bilasolur_cli.client import (
    DRIVE_FIELDS,
    FLAG_FIELDS,
    FUEL_FIELDS,
    SORT_LABELS,
    TRANSMISSION_FIELDS,
    BilasolurClient,
    BilasolurError,
    car_url,
    has_next_page,
    parse_car,
    parse_dealers,
    parse_results,
)

console = Console()


def _dump(payload: object) -> None:
    console.print(json.dumps(payload, indent=2, ensure_ascii=False), soft_wrap=True)


def _reference_table(title: str, rows: list[dict[str, str]]) -> Table:
    table = Table(title=title)
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    for row in rows:
        table.add_row(row["id"], row["name"])
    return table


@click.group()
def main() -> None:
    """bilasolur-cli - Search vehicle listings on bilasolur.is (Iceland)."""


@main.command()
@click.option("--make", "-m", help="Make, by name or ID (see `bilasolur makes`)")
@click.option("--model", help="Model, by name or ID (needs --make; see `bilasolur models`)")
@click.option("--submodel", help="Sub-model free text (undirgerð)")
@click.option("--serial", help="Serial number (raðnúmer)")
@click.option("--dealer", help="Dealer, by name or ID (see `bilasolur dealers`)")
@click.option("--category", "-c", multiple=True, help="Vehicle category (repeatable)")
@click.option("--color", multiple=True, help="Colour tone (repeatable)")
@click.option("--region", "-r", multiple=True, help="Region of Iceland (repeatable)")
@click.option("--fuel", "-f", multiple=True, type=click.Choice(list(FUEL_FIELDS)), help="Fuel type (repeatable)")
@click.option("--drive", "-d", multiple=True, type=click.Choice(list(DRIVE_FIELDS)), help="Drivetrain (repeatable)")
@click.option(
    "--transmission",
    "-t",
    multiple=True,
    type=click.Choice(list(TRANSMISSION_FIELDS)),
    help="Transmission (repeatable)",
)
@click.option("--year-from", type=int, help="Model year from")
@click.option("--year-to", type=int, help="Model year to")
@click.option("--price-from", type=int, help="Price from, in ISK")
@click.option("--price-to", type=int, help="Price to, in ISK")
@click.option("--km-from", type=int, help="Mileage from, in km")
@click.option("--km-to", type=int, help="Mileage to, in km")
@click.option("--hp-from", type=int, help="Horsepower from")
@click.option("--hp-to", type=int, help="Horsepower to")
@click.option("--seats-from", type=int, help="Seats from")
@click.option("--seats-to", type=int, help="Seats to")
@click.option("--doors-from", type=int, help="Doors from")
@click.option("--doors-to", type=int, help="Doors to")
@click.option("--range-from", type=int, help="Electric range from, in km")
@click.option("--battery-from", type=int, help="Battery capacity from, in kWh")
@click.option("--new-only", is_flag=True, help="New vehicles only")
@click.option("--good-price", is_flag=True, help="Flagged as a good price (flott verð)")
@click.option("--tow-hitch", is_flag=True, help="Has a tow hitch")
@click.option("--on-site", is_flag=True, help="Available on site (á staðnum)")
@click.option("--updated-days", type=click.Choice(["1", "7", "30", "60", "90", "120"]), help="Updated within N days")
@click.option("--sort", "-s", type=click.Choice(list(SORT_LABELS)), help="Sort order (default: price-asc)")
@click.option("--page", "-p", default=1, help="Page number (48 listings per page)")
@click.option("--limit", "-l", type=int, help="Show at most this many listings")
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON")
def search(
    make: str | None,
    model: str | None,
    submodel: str | None,
    serial: str | None,
    dealer: str | None,
    category: tuple[str, ...],
    color: tuple[str, ...],
    region: tuple[str, ...],
    fuel: tuple[str, ...],
    drive: tuple[str, ...],
    transmission: tuple[str, ...],
    sort: str | None,
    page: int,
    limit: int | None,
    json_output: bool,
    **kwargs: Any,
) -> None:
    """Search vehicle listings.

    \b
    Examples:
      bilasolur search -m Toyota --year-from 2018
      bilasolur search -m BMW --model X5 -f disel -s year-desc
      bilasolur search -c Jeppi --price-to 4000000 -r Höfuðborgarsvæðið
    """
    ranges = {k: v for k, v in kwargs.items() if k.endswith(("_from", "_to")) and v is not None}
    flags = tuple(k for k in FLAG_FIELDS if kwargs.get(k))
    with BilasolurClient() as client:
        try:
            search_id = client.search(
                make=make,
                model=model,
                submodel=submodel,
                serial=serial,
                dealer=dealer,
                category=category,
                color=color,
                region=region,
                fuel=fuel,
                drive=drive,
                transmission=transmission,
                flags=flags,
                updated_days=int(kwargs["updated_days"]) if kwargs.get("updated_days") else None,
                ranges=ranges,
            )
            if sort:
                search_id = client.sort(search_id, sort)
        except BilasolurError as exc:
            raise click.ClickException(str(exc))
        html = client.results_page(search_id, page)
        adjustments = client.adjustments

    cars = parse_results(html)
    if limit:
        cars = cars[:limit]
    if json_output:
        _dump({"search_id": search_id, "page": page, "results": cars})
        return
    for adjustment in adjustments:
        console.print(f"[yellow]Adjusted to the nearest value the site accepts: {adjustment}[/yellow]")
    if not cars:
        console.print("[dim]No listings found[/dim]")
        return
    table = Table(title=f"bilasolur.is - page {page}")
    table.add_column("Serial", style="cyan")
    table.add_column("Vehicle", style="green")
    table.add_column("Reg.", style="magenta")
    table.add_column("Mileage", justify="right")
    table.add_column("Fuel", style="dim")
    table.add_column("Drivetrain", style="dim")
    table.add_column("Price", style="yellow", justify="right")
    for car in cars:
        table.add_row(
            car["serial"],
            f"{car['make']} {car['model']}".strip()[:38],
            car["registered"],
            car["mileage"],
            car["fuel"],
            car["drivetrain"],
            f"{car['price']} kr." if car["price"] else "-",
        )
    console.print(table)
    console.print(f"[dim]{len(cars)} listings shown[/dim]")
    if has_next_page(html):
        console.print(f"[dim]More results available - use --page {page + 1}[/dim]")


@main.command()
@click.argument("serial")
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON")
def car(serial: str, json_output: bool) -> None:
    """Show full details for a listing, by serial number (raðnúmer)."""
    with BilasolurClient() as client:
        try:
            found = client.find_by_serial(serial)
        except BilasolurError as exc:
            raise click.ClickException(str(exc))
        details = parse_car(client.car_page(found["bid"], found["serial"], found["sid"]))
    details["url"] = car_url(found["bid"], found["serial"], found["sid"])
    if json_output:
        _dump(details)
        return

    console.print(f"[bold green]{details['make']} {details['model']}[/bold green]")
    if details["note"]:
        console.print(f"[dim]{details['note']}[/dim]")
    console.print()
    for label, key in (
        ("Serial", "serial"),
        ("Registered", "registered"),
        ("Mileage", "mileage"),
        ("Fuel", "fuel"),
        ("Transmission", "transmission"),
        ("Colour", "color"),
        ("Next inspection", "inspection"),
        ("Listed", "listed"),
        ("Updated", "updated"),
    ):
        if details[key]:
            console.print(f"[bold]{label}:[/bold] {details[key]}")
    if details["tags"]:
        console.print(f"[bold]Tags:[/bold] {', '.join(details['tags'])}")
    if details["price"]:
        console.print(f"[bold]Price:[/bold] [yellow]{details['price']} kr.[/yellow]")
    if details["price_note"]:
        console.print(f"[dim]{details['price_note']}[/dim]")
    console.print(f"[bold]Seller:[/bold] {details['seller']} - {details['seller_address']}")
    console.print(f"[bold]URL:[/bold] {details['url']}")
    console.print(f"[bold]Photos:[/bold] {len(details['photos'])}")

    for title, items in details["specs"].items():
        if not items:
            continue
        console.print(f"\n[bold cyan]{title}[/bold cyan]")
        for item in items:
            console.print(f"  {item}")


@main.command()
@click.argument("filter_text", required=False)
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON")
def makes(filter_text: str | None, json_output: bool) -> None:
    """List vehicle makes, optionally filtered by name."""
    with BilasolurClient() as client:
        rows = client.makes()
    if filter_text:
        rows = [r for r in rows if filter_text.casefold() in r["name"].casefold()]
    if json_output:
        _dump(rows)
        return
    console.print(_reference_table("Makes", rows))


@main.command()
@click.argument("make")
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON")
def models(make: str, json_output: bool) -> None:
    """List models for a make."""
    with BilasolurClient() as client:
        try:
            make_id = client.resolve(client.makes(), make, "make")
        except BilasolurError as exc:
            raise click.ClickException(str(exc))
        rows = client.models(make_id)
    if json_output:
        _dump(rows)
        return
    console.print(_reference_table(f"Models for {make}", rows))


@main.command()
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON")
def categories(json_output: bool) -> None:
    """List vehicle categories."""
    with BilasolurClient() as client:
        rows = client.categories()
    if json_output:
        _dump(rows)
        return
    console.print(_reference_table("Categories", rows))


@main.command()
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON")
def colors(json_output: bool) -> None:
    """List colour tones."""
    with BilasolurClient() as client:
        rows = client.colors()
    if json_output:
        _dump(rows)
        return
    console.print(_reference_table("Colours", rows))


@main.command()
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON")
def regions(json_output: bool) -> None:
    """List regions used by the location filter."""
    with BilasolurClient() as client:
        rows = client.regions()
    if json_output:
        _dump(rows)
        return
    console.print(_reference_table("Regions", rows))


@main.command()
@click.option("--region", "-r", help="Restrict to a region, by name or ID")
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON")
def dealers(region: str | None, json_output: bool) -> None:
    """List dealers (söluaðilar) with contact details."""
    with BilasolurClient() as client:
        region_id = None
        if region:
            try:
                region_id = client.resolve(client.regions(), region, "region")
            except BilasolurError as exc:
                raise click.ClickException(str(exc))
        rows = parse_dealers(client.dealers_page(region_id))
    if json_output:
        _dump(rows)
        return
    if not rows:
        console.print("[dim]No dealers found[/dim]")
        return
    table = Table(title="Dealers")
    table.add_column("Name", style="green")
    table.add_column("Address", style="dim")
    table.add_column("Phone", style="cyan")
    table.add_column("Website")
    for row in rows:
        table.add_row(row["name"], row["address"], row["phone"], row["website"])
    console.print(table)


@main.command()
def sorts() -> None:
    """List the available sort orders."""
    table = Table(title="Sort orders")
    table.add_column("Key", style="cyan")
    table.add_column("bilasolur.is label", style="green")
    for key, label in SORT_LABELS.items():
        table.add_row(key, label)
    console.print(table)


if __name__ == "__main__":
    main()
