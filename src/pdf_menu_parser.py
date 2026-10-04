#!/usr/bin/env python3
"""
Parser per extreure dades del menú escolar des d'un PDF.
"""
import json
import re
import shutil
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

# Postres coneguts (per detectar l'últim plat com a postre al format nou).
# Tolerant a la confusió OCR entre I/l/1 a "iogurt"
POSTRES_RE = re.compile(r'^(fruita|[iyl1]?ogurt|yogurt|yoghurt)\b', re.IGNORECASE)


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


# ---------------------------------------------------------------------------
# OCR (PDFs amb el menú com a imatge, ex. octubre 2026)
# ---------------------------------------------------------------------------

# Marcador "DIA" tolerant a errors d'OCR (D1A, D!A, DIA...); el número
# del dia sol venir com a token separat a la mateixa línia
OCR_DIA_TOKEN_RE = re.compile(r'^D[I1l!|]A$', re.IGNORECASE)
OCR_NUMBER_RE = re.compile(r'^\d{1,2}$')

# Tokens que són soroll d'icones d'al·lèrgens, no text del menú
OCR_NOISE_RE = re.compile(r'^(E-?X|EX)$', re.IGNORECASE)


def _detect_ocr_language() -> str:
    """
    Detecta el primer idioma de tesseract disponible, preferint el català.

    Returns:
        Codi d'idioma per a pytesseract (ex: "cat", "spa", "eng").
    """
    import pytesseract

    available = set()
    try:
        available = set(pytesseract.get_languages(config=''))
    except Exception:
        pass

    for lang in ('cat', 'spa', 'eng'):
        if lang in available:
            return lang
    return 'eng'


def _render_page_to_image(pdf_path: str, page_index: int = 0, scale: float = 4.0):
    """
    Renderitza una pàgina del PDF amb pypdfium2 i la prepara per a l'OCR.

    Els PDFs del menú incrusten icones d'al·lèrgens acolorides dins de les
    cel·les; en gris es converteixen en blobs foscos que l'OCR llegeix com
    a símbols. Aquí s'emmascaren els píxels saturats (icones) a blanc,
    conservant el text negre/gris.

    Args:
        pdf_path: Ruta al fitxer PDF
        page_index: Índex de la pàgina
        scale: Factor d'escala (4.0 ≈ 288 dpi)

    Returns:
        Imatge PIL en escala de grisos sense icones acolorides
    """
    import pypdfium2 as pdfium
    from PIL import Image, ImageChops, ImageOps

    doc = pdfium.PdfDocument(pdf_path)
    try:
        page = doc[page_index]
        bitmap = page.render(scale=scale)
        pil_image = bitmap.to_pil().convert('RGB')
    finally:
        doc.close()

    # Saturació per píxel = max(RGB) - min(RGB); el text (negre/gris) té
    # saturació propera a zero, les icones acolorides no
    r, g, b = pil_image.split()
    mx = ImageChops.lighter(ImageChops.lighter(r, g), b)
    mn = ImageChops.darker(ImageChops.darker(r, g), b)
    sat = ImageChops.subtract(mx, mn)
    keep_text = sat.point(lambda v: 255 if v < 60 else 0)

    white = Image.new('RGB', pil_image.size, (255, 255, 255))
    masked = Image.composite(pil_image, white, keep_text)

    return ImageOps.grayscale(masked)


def _group_words_into_lines(words: list[dict]) -> list[list[dict]]:
    """
    Agrupa paraules OCR en línies per coordenada vertical.

    Args:
        words: Llista de dicts amb 'text', 'x0', 'top' i 'height'

    Returns:
        Llista de línies (cada línia és una llista de paraules ordenades per x)
    """
    lines: list[list[dict]] = []
    current: list[dict] = []
    current_top = None
    tolerance = None

    for w in sorted(words, key=lambda w: (w['top'], w['x0'])):
        if tolerance is None:
            tolerance = w['height'] * 0.8 if w['height'] else 10

        if current_top is None or abs(w['top'] - current_top) <= tolerance:
            current.append(w)
            if current_top is None:
                current_top = w['top']
        else:
            lines.append(current)
            current = [w]
            current_top = w['top']

    if current:
        lines.append(current)

    return lines


# Tokens d'una sola lletra (case-sensitive): només les que són paraules
# vàlides en català dins del menú ("patata i bajoca", "a la planxa")
OCR_ALLOWED_SINGLE_CHARS = {'i', 'a', 'y', 'o', 'u'}


def _is_ocr_junk_token(text: str) -> bool:
    """
    Detecta tokens que són restes d'icones d'al·lèrgens, no text del menú.

    Les icones grises/desaturades deixen restes curtes sense sentit:
    "GO)", "EP.", "GG", "es)"... El text real del menú és frases amb
    paraules catalanes completes.
    """
    if len(text) == 1:
        return text not in OCR_ALLOWED_SINGLE_CHARS
    # Puntuació de tancament en tokens curts: "GO)", "es)", "EP."
    if len(text) <= 4 and re.search(r'[\)\(\[\].,;:]', text):
        return True
    # Sigles de 2-3 majúscules: "GG", "SS", "EQ"
    if len(text) <= 3 and text.isupper() and text.isalpha():
        return True
    # 2 lletres amb inicial majúscula: "Pr", "En" (excepte articles reals)
    if len(text) == 2 and text.isalpha() and text[0].isupper() and text not in ('El', 'La'):
        return True
    return False


def _split_postre_lines(lines: list[str]) -> list[str]:
    """
    Separa el postre quan l'OCR l'ha enganxat a la mateixa línia que el
    segon plat (ex: "...amb humus logurt" -> ["...amb humus", "logurt"]).
    """
    result = []
    for line in lines:
        match = re.search(r'\b(fruita de temporada|[iylo1]?ogurt)\s*$', line, re.IGNORECASE)
        if match and match.start() > 0:
            before = line[:match.start()].strip()
            if before:
                result.append(before)
            result.append(match.group(1).strip())
        else:
            result.append(line)
    return result


def extract_days_ocr(pdf_path: str) -> dict[int, list[str]]:
    """
    Extreu les cel·les de dia dels PDFs que tenen el menú com a imatge
    (a partir d'octubre 2026), usant tesseract (OCR).

    El PDF incrusta la graella del menú com una imatge rasteritzada, sense
    text extreuible. Estratègia:
      1. Renderitzar la pàgina a alta resolució (pypdfium2).
      2. OCR amb pytesseract (psm 11, text dispers) obtenint caixes per paraula.
      3. Detectar els marcadors "DIA N" i reconstruir la graella 5xN
         geomètricament (columnes per X dels marcadors, files per Y).
      4. Assignar paraules a cada cel·la i agrupar-les en línies.

    Args:
        pdf_path: Ruta al fitxer PDF

    Returns:
        Diccionari {numero_dia: [linies de text de la cel·la]}
        Buit si l'OCR no troba marcadors "DIA N".
    """
    try:
        import pytesseract
    except ImportError:
        return {}

    image = _render_page_to_image(pdf_path)
    lang = _detect_ocr_language()

    # Passada 1: OCR dispers de tota la pàgina NOMÉS per localitzar els
    # marcadors "DIA" (el text de cel·les s'extreu per cel·la, passada 2)
    data = pytesseract.image_to_data(
        image,
        lang=lang,
        config='--psm 11',
        output_type=pytesseract.Output.DICT,
    )

    n = len(data['text'])
    words = []
    for i in range(n):
        text = (data['text'][i] or '').strip()
        if not text:
            continue
        # Descartar tokens sense lletres ni xifres (soroll d'icones)
        if not re.search(r'[A-Za-z0-9À-ÿ]', text):
            continue
        if OCR_NOISE_RE.match(text):
            continue
        words.append({
            'text': text,
            'x0': data['left'][i],
            'top': data['top'][i],
            'x1': data['left'][i] + data['width'][i],
            'bottom': data['top'][i] + data['height'][i],
            'height': data['height'][i],
        })

    # Detectar marcadors "DIA" + número (sovint tokens separats)
    anchors = []
    used_numbers = set()
    for w in words:
        if not OCR_DIA_TOKEN_RE.match(w['text']):
            continue
        partner = None
        for w2 in words:
            if not OCR_NUMBER_RE.match(w2['text']):
                continue
            if id(w2) in used_numbers:
                continue
            same_line = abs(w2['top'] - w['top']) < max(w['height'], w2['height']) * 0.7
            # Les caixes de "DIA" sovint són més amples que el glif i el
            # número hi solapa: midem des de l'inici del token DIA
            close = 0 < w2['x0'] - w['x0'] < w['height'] * 6
            if same_line and close:
                partner = w2
                break
        if partner:
            used_numbers.add(id(partner))
            anchors.append({
                'day': int(partner['text']),
                'x0': w['x0'],
                'cx': (w['x0'] + w['x1']) / 2,
                'top': w['top'],
                'height': w['height'],
            })

    if len(anchors) < 2:
        return {}

    # Les capçaleres "DIA N" van CENTRADES a cada cel·la: la columna es
    # deriva del centre de cada àncora i els límits són els punts mitjos
    # entre centres de columnes consecutives.
    centers = sorted({a['cx'] for a in anchors})
    col_clusters: list[list[float]] = []
    for x in centers:
        if col_clusters and x - col_clusters[-1][-1] < image.width * 0.04:
            col_clusters[-1].append(x)
        else:
            col_clusters.append([x])
    col_centers = sorted(sum(cl) / len(cl) for cl in col_clusters)

    if len(col_centers) < 2:
        return {}

    col_bounds = []
    for i, cx in enumerate(col_centers):
        if i == 0:
            mid_next = (col_centers[0] + col_centers[1]) / 2
            left = max(0, int(2 * cx - mid_next))
            right = int(mid_next)
        elif i == len(col_centers) - 1:
            mid_prev = (col_centers[-2] + col_centers[-1]) / 2
            left = int(mid_prev)
            right = min(image.width, int(2 * cx - mid_prev))
        else:
            left = int((col_centers[i - 1] + cx) / 2)
            right = int((cx + col_centers[i + 1]) / 2)
        col_bounds.append((left, right))

    # Files: els top de les àncores marquen la capçalera de cada fila
    tops = sorted({a['top'] for a in anchors})
    row_clusters: list[list[float]] = []
    for t in tops:
        if row_clusters and t - row_clusters[-1][-1] < image.height * 0.03:
            row_clusters[-1].append(t)
        else:
            row_clusters.append([t])
    row_starts = sorted(min(cl) for cl in row_clusters)

    # Pas entre files (mitjana de les diferències) per tancar l'última fila
    row_pitch = (int(sum(b - a for a, b in zip(row_starts, row_starts[1:]))
                     / (len(row_starts) - 1)) if len(row_starts) > 1 else int(image.height * 0.15))

    header_height = int(max(a['height'] for a in anchors))

    def row_bounds_of(i: int) -> tuple[int, int]:
        start = row_starts[i]
        top = start + header_height + 6
        if i + 1 < len(row_starts):
            bottom = row_starts[i + 1] - 8
        else:
            bottom = min(image.height, start + row_pitch - 8)
        return (top, bottom)

    # Passada 2: retallar cada cel·la de la graella i fer-hi OCR per bloc
    # (psm 6), molt més estable que assignar tokens de la passada global
    days: dict[int, list[str]] = {}
    for anchor in anchors:
        col = next((i for i, cx in enumerate(col_centers) if col_bounds[i][0] <= anchor['cx'] < col_bounds[i][1]), None)
        # Files per punts mitjos entre inicis de fila consecutius
        row = None
        for i in range(len(row_starts)):
            lower = (row_starts[i - 1] + row_starts[i]) / 2 if i > 0 else float('-inf')
            upper = (row_starts[i] + row_starts[i + 1]) / 2 if i + 1 < len(row_starts) else float('inf')
            if lower <= anchor['top'] < upper:
                row = i
                break
        if col is None or row is None:
            continue

        col_left, col_right = col_bounds[col]
        cell_top, cell_bottom = row_bounds_of(row)

        cell_box = (max(0, col_left), max(0, cell_top),
                    min(image.width, col_right), min(image.height, cell_bottom))
        if cell_box[2] <= cell_box[0] or cell_box[3] <= cell_box[1]:
            continue

        cell_img = image.crop(cell_box)
        cell_data = pytesseract.image_to_data(
            cell_img,
            lang=lang,
            config='--psm 6',
            output_type=pytesseract.Output.DICT,
        )

        cell_words = []
        for i in range(len(cell_data['text'])):
            text = (cell_data['text'][i] or '').strip()
            if not text:
                continue
            # Només tokens amb lletres: les xifres i puntuació sola són
            # soroll de les icones d'al·lèrgens
            if not re.search(r'[A-Za-zÀ-ÿ]', text):
                continue
            if OCR_NOISE_RE.match(text):
                continue
            if _is_ocr_junk_token(text):
                continue
            cell_words.append({
                'text': text,
                'x0': cell_data['left'][i] + cell_box[0],
                'top': cell_data['top'][i] + cell_box[1],
                'x1': cell_data['left'][i] + cell_data['width'][i] + cell_box[0],
                'bottom': cell_data['top'][i] + cell_data['height'][i] + cell_box[1],
                'height': cell_data['height'][i],
                # Línia segmentada per tesseract (més fiable que agrupar per top)
                'line_key': (cell_data['block_num'][i], cell_data['par_num'][i], cell_data['line_num'][i]),
            })

        # Agrupar per la línia que segmenta tesseract, ordenant per x
        by_line: dict[tuple, list[dict]] = {}
        for w in cell_words:
            by_line.setdefault(w['line_key'], []).append(w)
        text_lines = [
            ' '.join(x['text'] for x in sorted(ws, key=lambda w: w['x0']))
            for _, ws in sorted(by_line.items(), key=lambda kv: min(w['top'] for w in kv[1]))
        ]
        text_lines = [line for line in text_lines if line.strip()]
        text_lines = _split_postre_lines(text_lines)
        # Correccions de paraules freqüents on l'OCR perd l'accent
        ocr_word_fixes = {'tomaquet': 'tomàquet', 'sipia': 'sípia'}
        text_lines = [
            re.sub(r'\b(tomaquet|sipia)\b', lambda m: ocr_word_fixes[m.group(1)], line)
            for line in text_lines
        ]

        # Cel·la de festiu: cap contingut més enllà del marcador.
        # Tolerant a errors d'OCR sobre "FESTIU" (FESUY, FESIU...)
        if len(text_lines) == 1 and text_lines[0].upper().startswith('FES'):
            continue

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
        # un plat nou; les línies en minúscula són continuació. El postre
        # ("iogurt", sovint en minúscula) també inicia plat nou.
        plats = []
        current_plat: list[str] = []
        for line in lines:
            if (line and line[0].isupper() or POSTRES_RE.match(line)) and current_plat:
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

    # Si tampoc hi ha text útil, el menú és una imatge: provar l'OCR
    if not menu_data.get('days'):
        click.echo("ℹ️  Sense text extreuible; el menú sembla una imatge, provant OCR (tesseract)...")
        try:
            day_cells = extract_days_ocr(pdf_file)
        except Exception as e:
            click.echo(f"⚠️  OCR ha fallat: {e}")
            day_cells = {}
        if day_cells:
            menu_data = build_menu_from_new_format(day_cells, month, year)
        elif not shutil.which('tesseract'):
            click.echo("⚠️  tesseract no està instal·lat. Instal·la'l amb:")
            click.echo("   sudo apt install tesseract-ocr tesseract-ocr-spa tesseract-ocr-cat")

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

