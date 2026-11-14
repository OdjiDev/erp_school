import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from openpyxl.utils.datetime import from_excel


class SheetFormatError(Exception):
    pass


def strip_accents(value):
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in normalized if not unicodedata.combining(char))


def normalize_key(value):
    """Clé de comparaison : sans accents, minuscules, espaces normalisés."""
    return " ".join(strip_accents(value).lower().split())


def normalize_header(value):
    return normalize_key(value)


def text(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Oui" if value else "Non"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def normalize_code(value):
    return text(value).upper()


def parse_date(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return from_excel(value).date()
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"Date Excel invalide : {value}.") from exc

    raw = str(value).strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(
        f"Date invalide : {raw}. Utilisez le format JJ/MM/AAAA."
    )


def parse_decimal(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise ValueError(f"Nombre attendu, valeur reçue : {value}.")
    raw = (
        str(value)
        .strip()
        .replace("\u00a0", "")
        .replace(" ", "")
        .replace(",", ".")
    )
    try:
        number = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"Nombre invalide : {value}.") from exc
    if not number.is_finite():
        raise ValueError(f"Nombre invalide : {value}.")
    return number


def parse_bool(value, default=False):
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)

    key = normalize_key(value)
    if key in {"oui", "o", "1", "vrai", "true", "x"}:
        return True
    if key in {"non", "n", "0", "faux", "false"}:
        return False
    raise ValueError(f"Valeur oui/non attendue : {value}.")


def iter_rows(worksheet, required, optional=()):
    """Lit une feuille et retourne (numéro de ligne, dictionnaire normalisé)."""
    header_row = next(
        worksheet.iter_rows(min_row=1, max_row=1, values_only=True), None
    )
    if not header_row:
        raise SheetFormatError("La feuille est vide.")

    positions = {}
    for index, value in enumerate(header_row):
        key = normalize_header(value)
        if key and key not in positions:
            positions[key] = index

    missing = [
        header for header in required if normalize_header(header) not in positions
    ]
    if missing:
        raise SheetFormatError(
            "Colonnes obligatoires manquantes : " + ", ".join(missing)
        )

    headers = list(dict.fromkeys([*required, *optional]))
    for row_number, values in enumerate(
        worksheet.iter_rows(min_row=2, values_only=True), start=2
    ):
        if not values or all(
            value is None or (isinstance(value, str) and not value.strip())
            for value in values
        ):
            continue
        row = {}
        for header in headers:
            key = normalize_header(header)
            index = positions.get(key)
            row[key] = (
                values[index] if index is not None and index < len(values) else None
            )
        yield row_number, row
