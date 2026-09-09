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


WEEKDAY_FROM_DATE_CA = ['Dilluns', 'Dimarts', 'Dimecres', 'Dijous', 'Divendres', 'Dissabte', 'Diumenge']

# Regex per detectar l'inici d'una cel·la de dia al format nou (2026+): "14. ..."
NEW_FORMAT_DAY_RE = re.compile(r'^(\d{1,2})\.(.*)$')

# Postres coneguts (per detectar l'últim plat com a postre al format nou)
POSTRES_RE = re.compile(r'^(fruita|iogurt|iogur|yogurt|yoghurt)\b', re.IGNORECASE)


def extract_days_new_format(pdf_path: str) -> dict[int, list[str]]:
    """
    Extreu les cel·les de dia dels PDFs amb el format nou (a partir de setembre 2026).

    El format nou no usa capçaleres "DIA X" ni files de dies de la setmana a les
    taules detectables. A més, el PDF porta el text dibuixat dues vegades
    (caràcters superposats), espais d'uns 2.4pt (per sota del x_tolerance per
    defecte de pdfplumber) i text que desborda l'amplada de la seva columna.

    Estratègia:
      1. Treure els caràcters superposats duplicats (dedupe_chars).
      2. Extreure paraules amb un x_tolerance reduït.
      3. Detectar les cel·les pels marcadors "NN." i reconstruir-les
         geomètricament: les columnes comencen a la posició X de cada marcador
         i el text pot estendre's fins a l'inici de la columna següent.

    Args:
        pdf_path: Ruta al fitxer PDF

    Returns:
        Diccionari {numero_dia: [linies de text de la cel·la]}
        Buit si el PDF no sembla tenir el format nou.
    """
    days: dict[int, list[str]] = {}

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page = page.dedupe_chars(tolerance=1)
            words = page.extract_words(x_tolerance=2.0, keep_blank_chars=False)

            # Detectar marcadors de dia ("14.", "21.Cigrons...", etc.)
            anchors = []
            for w in words:
                match = NEW_FORMAT_DAY_RE.match(w['text'])
                if match:
                    anchors.append({
                        'day': int(match.group(1)),
                        'rest': match.group(2).strip(),
                        'x0': w['x0'],
                        'top': w['top'],
                        'word': w,
                    })

            if len(anchors) < 2:
                continue

            # Agrupar les X dels marcadors en columnes (les cel·les d'una mateixa
            # columna comparteixen el marge esquerre)
            xs = sorted({a['x0'] for a in anchors})
            clusters: list[list[float]] = []
            for x in xs:
                if clusters and x - clusters[-1][-1] < 20:
                    clusters[-1].append(x)
                else:
                    clusters.append([x])

            if len(clusters) < 2:
                continue

            # Una columna s'estén des del seu inici fins a l'inici de la següent
            # (el text pot desbordar el marge dret de la cel·la). Es deixa un
            # petit marge a l'esquerra per tolerar desviacions subpíxel entre el
            # marcador del dia i la resta de text de la cel·la.
            col_starts = sorted(min(cl) for cl in clusters)
            col_bounds = []
            for i, start in enumerate(col_starts):
                left = start - 1.0
                right = (col_starts[i + 1] - 1.0) if i + 1 < len(col_starts) else page.width
                col_bounds.append((left, right))

            anchors.sort(key=lambda a: a['top'])

            def col_of(x0: float) -> int | None:
                for i, (start, end) in enumerate(col_bounds):
                    if start <= x0 < end:
                        return i
                return None

            # El requadre "POSTRES:" (sota la graella) marca el final de l'última
            # setmana; sense això, el seu text s'atribuiria a l'últim dia
            postres_top = None
            last_anchor_top = max(a['top'] for a in anchors)
            for w in words:
                if w['text'].startswith('POSTRES') and w['top'] > last_anchor_top:
                    postres_top = w['top'] if postres_top is None else min(postres_top, w['top'])

            for anchor in anchors:
                col = col_of(anchor['x0'])
                if col is None:
                    continue

                start, end = col_bounds[col]
                same_col_tops = [a['top'] for a in anchors
                                 if a['top'] > anchor['top'] and col_of(a['x0']) == col]
                bottom = min(same_col_tops + [postres_top if postres_top is not None else page.height])

                cell_words = [w for w in words
                              if start <= w['x0'] < end
                              and anchor['top'] <= w['top'] < bottom
                              and w is not anchor['word']]

                # Si el número de dia va enganxat al primer text ("15.Cigrons"),
                # mantenim la resta com a primera paraula de la cel·la
                if anchor['rest']:
                    cell_words.append({'text': anchor['rest'], 'x0': anchor['x0'], 'top': anchor['top']})

                # Agrupar paraules en línies (clustering per coordenada vertical)
                cell_words.sort(key=lambda w: w['top'])
                lines: list[list] = []
                current_line: list = []
                current_top = None
                for w in cell_words:
                    if current_top is None or abs(w['top'] - current_top) < 4:
                        current_line.append(w)
                        if current_top is None:
                            current_top = w['top']
                    else:
                        lines.append(current_line)
                        current_line = [w]
                        current_top = w['top']
                if current_line:
                    lines.append(current_line)

                text_lines = [' '.join(x['text'] for x in sorted(line, key=lambda w: w['x0']))
                              for line in lines]
                text_lines = [line for line in text_lines if line.strip()]

                if text_lines:
                    days[anchor['day']] = text_lines

    return days


def build_menu_from_new_format(day_cells: dict[int, list[str]], month: str, year: int) -> dict:
    """
    Converteix les cel·les extretes del format nou en l'estructura de menú.

    Args:
        day_cells: Diccionari {numero_dia: [linies de text]}
        month: Nom del mes en català
        year: Any del menú

    Returns:
        Diccionari amb metadades i llista de dies
    """
    all_days = []

    for day_number in sorted(day_cells):
        lines = day_cells[day_number]
        raw_content = '\n'.join(lines)
        full_text = ' '.join(lines)

        notes = []
        if 'sense proteïna animal' in full_text.lower():
            notes.append('sense proteïna animal')

        # Agrupar línies per plats: una línia que comença amb majúscula inicia
        # un plat nou; les línies en minúscula són continuació
        plats = []
        current_plat: list[str] = []
        for line in lines:
            if line and line[0].isupper() and current_plat:
                plats.append(' '.join(current_plat))
                current_plat = [line]
            else:
                current_plat.append(line)
        if current_plat:
            plats.append(' '.join(current_plat))

        primer = plats[0] if len(plats) > 0 else ''
        segon = plats[1] if len(plats) > 1 else ''

        # L'últim plat pot ser el postre (ex: "Fruita de temporada")
        postre = 'N/D'
        if len(plats) > 2 and POSTRES_RE.match(plats[-1]):
            postre = plats[-1]
            plats = plats[:-1]
            segon = ' '.join(plats[1:]) if len(plats) > 1 else ''
        elif len(plats) > 2:
            segon = ' '.join(plats[1:])

        iso_date = day_to_iso_date(day_number, month, year)
        weekday = WEEKDAY_FROM_DATE_CA[date(year, MONTHS_CA[month.lower()], day_number).weekday()]

        day_entry = {
            'date': iso_date,
            'weekday': weekday,
            'dia': day_number,
            'primer': primer,
            'segon': segon,
            'postre': postre,
            'raw': raw_content,
        }

        if notes:
            day_entry['notes'] = notes

        all_days.append(day_entry)

    all_days.sort(key=lambda x: x['date'])

    return {
        'month': month,
        'year': year,
        'days': all_days,
    }


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

    # Extreure taules del PDF (format antic)
    tables = extract_table_from_pdf(pdf_file)
    click.echo(f"✅ Taules extretes: {len(tables)}")

    # Processar les dades (format antic)
    menu_data = parse_menu(tables, month, year)

    # Si el format antic no troba dies, provar el format nou (2026+)
    if not menu_data.get('days'):
        click.echo("ℹ️  Format antic sense resultats; provant el format nou (2026+)...")
        day_cells = extract_days_new_format(pdf_file)
        if day_cells:
            menu_data = build_menu_from_new_format(day_cells, month, year)

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

