#!/usr/bin/env python3
"""
Parser per extreure dades del menú escolar des d'un PDF.
"""
import json
import re
from datetime import date
import pdfplumber
import click
from pathlib import Path


# Mapping de mesos catalans a números
MONTHS_CA = {
    'gener': 1, 'febrer': 2, 'març': 3, 'abril': 4,
    'maig': 5, 'juny': 6, 'juliol': 7, 'agost': 8,
    'setembre': 9, 'octubre': 10, 'novembre': 11, 'desembre': 12
}

WEEKDAYS_CA = {
    'DILLUNS': 'Dilluns',
    'DIMARTS': 'Dimarts',
    'DIMECRES': 'Dimecres',
    'DIJOUS': 'Dijous',
    'DIVENDRES': 'Divendres'
}


def extract_month_year_from_filename(filename: str) -> tuple[str, int]:
    """
    Extreu el mes i any del nom del fitxer.

    Args:
        filename: Nom del fitxer (ex: "novembre_2025.pdf")

    Returns:
        Tupla amb (mes, any)
    """
    name = Path(filename).stem

    # Intentar extreure mes i any amb regex
    match = re.search(r'([a-zç]+).*?(\d{4})', name, re.IGNORECASE)

    if match:
        month_name = match.group(1).lower()
        year = int(match.group(2))
        return month_name, year

    # Si no es pot extreure, retornar valors per defecte
    return "desconegut", date.today().year


def day_to_iso_date(day_number: int, month: str, year: int) -> str:
    """
    Converteix un dia del mes a format ISO (YYYY-MM-DD).

    Args:
        day_number: Número del dia (1-31)
        month: Nom del mes en català
        year: Any (ex: 2025)

    Returns:
        Data en format ISO
    """
    month_number = MONTHS_CA.get(month.lower(), 1)
    return date(year, month_number, day_number).isoformat()


def extract_table_from_pdf(pdf_path: str) -> list:
    """
    Extreu la taula del PDF del menú.

    Args:
        pdf_path: Ruta al fitxer PDF

    Returns:
        Llista amb les files de la taula
    """
    tables = []

    with pdfplumber.open(pdf_path) as pdf:
        # Iterem per cada pàgina del PDF
        for page in pdf.pages:
            # Extraiem totes les taules de la pàgina
            page_tables = page.extract_tables()

            if page_tables:
                tables.extend(page_tables)

    return tables


def parse_cell(cell_content: str) -> dict | None:
    """
    Processa el contingut d'una cel·la del menú.
    Usa majúscules per detectar l'inici de cada plat.

    Args:
        cell_content: Text de la cel·la amb format "DIA X\nPrimer\nSegon\nPostre"

    Returns:
        Diccionari amb dia i plats, o None si la cel·la és buida
    """
    if not cell_content or cell_content.strip() == "":
        return None

    # Guardar el contingut raw
    raw_content = cell_content.strip()

    lines = [line.strip() for line in cell_content.split('\n') if line.strip()]

    if len(lines) < 2:
        return None

    # Primera línia: "DIA X" o "DIA X sense proteïna animal"
    day_line = lines[0]
    if not day_line.startswith('DIA'):
        return None

    # Extreure número del dia
    day_number = day_line.replace('DIA', '').strip().split()[0]

    # Comprovar si és sense proteïna animal
    notes = []
    if 'sense proteïna animal' in day_line:
        notes.append('sense proteïna animal')

    # Identificar el postre (última línia)
    postre = lines[-1]

    # Les línies entre la primera i l'última són els plats
    menu_lines = lines[1:-1]

    if not menu_lines:
        return {
            "dia": int(day_number),
            "primer": "",
            "segon": "",
            "postre": postre,
            "notes": notes,
            "raw": raw_content
        }

    # Agrupar línies per plats usant majúscules com a indicador
    plats = []
    current_plat = []

    for line in menu_lines:
        # Si comença amb majúscula i ja tenim un plat, guardem l'anterior
        if line and line[0].isupper() and current_plat:
            plats.append(" ".join(current_plat))
            current_plat = [line]
        else:
            # Continuació del plat actual
            current_plat.append(line)

    # Afegir l'últim plat
    if current_plat:
        plats.append(" ".join(current_plat))

    # Assignar plats (normalment 2: primer i segon)
    primer = plats[0] if len(plats) > 0 else ""
    segon = plats[1] if len(plats) > 1 else ""

    # Si hi ha més de 2 plats, unir els extres al segon
    if len(plats) > 2:
        segon = " ".join(plats[1:])

    return {
        "dia": int(day_number),
        "primer": primer,
        "segon": segon,
        "postre": postre,
        "notes": notes,
        "raw": raw_content
    }


def review_menu_interactive(menu_data: dict) -> dict:
    """
    Revisa interactivament tot el menú.

    Args:
        menu_data: Diccionari amb metadades i llista de dies

    Returns:
        Diccionari amb les dades validades/corregides
    """
    click.echo("\n" + "="*60)
    click.echo("🔍 MODE INTERACTIU - Revisió del menú")
    click.echo("="*60)
    click.echo(f"\n📅 {menu_data['month'].capitalize()} {menu_data['year']}")
    click.echo("\nRevisa cada dia i corregeix si és necessari.")
    click.echo("Prem 's' si és correcte, 'n' per corregir.\n")

    validated_days = []

    for day_data in menu_data['days']:
        # Mostrar el dia amb la data
        day_display = f"{day_data['weekday']} {day_data['dia']} ({day_data['date']})"

        click.echo(f"\n{'='*60}")
        click.echo(f"📅 {day_display}")
        click.echo(f"{'='*60}")

        if day_data.get('notes'):
            click.echo(f"📝 Notes: {', '.join(day_data['notes'])}")
            click.echo()

        click.echo(f"  🍲 Primer: {day_data['primer']}")
        click.echo(f"  🍽️  Segon:  {day_data['segon']}")
        click.echo(f"  🍨 Postre:  {day_data['postre']}")
        click.echo()

        if click.confirm('❓ És correcte?', default=True):
            validated_days.append(day_data)
        else:
            # Corregir les dades
            click.echo("\n✏️  Corregeix les dades (prem Enter per mantenir):")

            primer = click.prompt('  Primer plat',
                                  default=day_data['primer'],
                                  show_default=False)
            segon = click.prompt('  Segon plat',
                                 default=day_data['segon'],
                                 show_default=False)
            postre = click.prompt('  Postre',
                                  default=day_data['postre'],
                                  show_default=False)

            corrected_day = day_data.copy()
            corrected_day['primer'] = primer
            corrected_day['segon'] = segon
            corrected_day['postre'] = postre

            validated_days.append(corrected_day)

    click.echo("\n" + "="*60)
    click.echo("✅ Revisió completada!")
    click.echo("="*60 + "\n")

    return {
        "month": menu_data['month'],
        "year": menu_data['year'],
        "days": validated_days
    }


def parse_menu(tables: list, month: str, year: int) -> dict:
    """
    Processa les taules extretes i les converteix en estructura de dades.

    Args:
        tables: Llista de taules extretes del PDF
        month: Nom del mes en català
        year: Any del menú

    Returns:
        Diccionari amb metadades i llista de dies
    """
    if len(tables) < 2:
        return {"month": month, "year": year, "days": []}

    # Agafem la segona taula (la ben estructurada)
    table = tables[1]

    if len(table) < 2:
        return {"month": month, "year": year, "days": []}

    # Primera fila: noms dels dies
    day_names = [day.strip() for day in table[0]]

    # Processar totes les files (setmanes) i crear una llista plana de dies
    all_days = []

    for row in table[1:]:
        for i, cell in enumerate(row):
            if i >= len(day_names):
                break

            weekday_key = day_names[i]
            cell_data = parse_cell(cell)

            if cell_data:
                # Crear la data ISO
                iso_date = day_to_iso_date(cell_data['dia'], month, year)

                # Normalitzar el nom del dia
                weekday = WEEKDAYS_CA.get(weekday_key, weekday_key)

                day_entry = {
                    "date": iso_date,
                    "weekday": weekday,
                    "dia": cell_data['dia'],
                    "primer": cell_data['primer'],
                    "segon": cell_data['segon'],
                    "postre": cell_data['postre'],
                    "raw": cell_data['raw']
                }

                # Afegir notes si n'hi ha
                if cell_data.get('notes'):
                    day_entry['notes'] = cell_data['notes']

                all_days.append(day_entry)

    # Ordenar per data
    all_days.sort(key=lambda x: x['date'])

    return {
        "month": month,
        "year": year,
        "days": all_days
    }


@click.command()
@click.argument('pdf_file', type=click.Path(exists=True))
@click.option('--output', '-o', 'output_file', type=click.Path(),
              help='Fitxer JSON de sortida (per defecte: menu/data/[nom_pdf].json)')
@click.option('--print', 'print_output', is_flag=True,
              help='Mostrar el resultat per pantalla')
@click.option('--interactive', '-i', 'interactive', is_flag=True,
              help='Mode interactiu per revisar i corregir les dades')
def main(pdf_file: str, output_file: str, print_output: bool, interactive: bool):
    """
    Parser del menú escolar des d'un PDF.

    Exemple:
        python src/pdf_menu_parser.py menu/pdfs/novembre_2025.pdf --interactive
    """
    click.echo(f"📖 Llegint PDF: {pdf_file}")

    # Extreure mes i any del nom del fitxer
    month, year = extract_month_year_from_filename(pdf_file)
    click.echo(f"📅 Detectat: {month.capitalize()} {year}")

    # Si no s'especifica output, generar-lo automàticament
    if not output_file:
        pdf_path = Path(pdf_file)
        pdf_name = pdf_path.stem  # Nom sense extensió
        output_file = f"menu/data/{pdf_name}.json"
        click.echo(f"📁 Output automàtic: {output_file}")

    # Extreure taules del PDF
    tables = extract_table_from_pdf(pdf_file)
    click.echo(f"✅ Taules extretes: {len(tables)}")

    # Processar les dades
    menu_data = parse_menu(tables, month, year)
    click.echo(f"✅ Menú processat: {len(menu_data.get('days', []))} dies")

    # Mode interactiu per revisar i corregir
    if interactive:
        menu_data = review_menu_interactive(menu_data)

    # Mostrar per pantalla si s'ha demanat
    if print_output:
        click.echo("\n📋 Dades finals:")
        click.echo(json.dumps(menu_data, indent=2, ensure_ascii=False))

    # Guardar a fitxer (sempre)
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(menu_data, f, indent=2, ensure_ascii=False)

    click.echo(f"💾 Dades guardades a: {output_file}")


if __name__ == '__main__':
    main()

