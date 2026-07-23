import json
import os
import re
from typing import Iterable

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]
MONTH_MAP = {
    "ENE": "ENE",
    "ENERO": "ENE",
    "FEB": "FEB",
    "FEBRERO": "FEB",
    "MAR": "MAR",
    "MARZO": "MAR",
    "ABR": "ABR",
    "ABRIL": "ABR",
    "MAY": "MAY",
    "MAYO": "MAY",
    "JUN": "JUN",
    "JUNIO": "JUN",
    "JUL": "JUL",
    "JULIO": "JUL",
    "AGO": "AGO",
    "AGOSTO": "AGO",
    "SEP": "SEP",
    "SEPT": "SEP",
    "SEPTIEMBRE": "SEP",
    "OCT": "OCT",
    "OCTUBRE": "OCT",
    "NOV": "NOV",
    "NOVIEMBRE": "NOV",
    "DIC": "DIC",
    "DICIEMBRE": "DIC",
}
DEFAULT_DIEZMADORES_FOLDER_ID = "14d72317gO2jg5iM6vnPy16pV1raqVdme"


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value).strip().lower())


def parse_monto(value: str) -> float:
    text = str(value).strip()
    if not text:
        raise ValueError("Monto vacío.")

    text = text.replace("Bs.", "").replace("Bs", "").replace("$", "").strip()
    has_comma = "," in text
    has_dot = "." in text

    if has_dot and has_comma:
        text = text.replace(".", "").replace(",", ".")
    elif has_comma:
        text = text.replace(",", ".")

    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"Monto inválido: '{value}'. Use números con coma decimal, por ejemplo 600,00.") from exc


def format_currency_bs(value: float) -> str:
    formatted = f"{value:,.2f}"
    # Cambiar separador de miles a punto y separador decimal a coma
    return "Bs. " + formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def get_credentials(creds_json: str = "credentials.json"):
    if not os.path.exists(creds_json):
        raise FileNotFoundError(f"No se encontró el archivo de credenciales: {creds_json}")
    return Credentials.from_service_account_file(creds_json, scopes=SCOPES)


def get_service(creds_json: str = "credentials.json", service_name: str = "sheets", version: str = "v4"):
    credentials = get_credentials(creds_json)
    return build(service_name, version, credentials=credentials)


def is_likely_spreadsheet_id(value: str) -> bool:
    value = str(value).strip()
    if "/" in value or "docs.google.com" in value:
        return True
    return bool(re.fullmatch(r"[a-zA-Z0-9_-]{30,}", value))


def resolve_spreadsheet_id(spreadsheet_ref: str, creds_json: str = "credentials.json") -> str:
    spreadsheet_ref = str(spreadsheet_ref).strip()
    if is_likely_spreadsheet_id(spreadsheet_ref):
        return spreadsheet_ref

    drive_service = get_service(creds_json, service_name="drive", version="v3")
    safe_name = spreadsheet_ref.replace("'", "''")
    query = (
        f"name = '{safe_name}' and mimeType = 'application/vnd.google-apps.spreadsheet' "
        "and trashed = false"
    )
    response = drive_service.files().list(q=query, fields="files(id,name)").execute()
    files = response.get("files", [])
    if not files:
        raise ValueError(
            f"No se encontró ningún spreadsheet con el nombre '{spreadsheet_ref}'."
        )
    if len(files) > 1:
        names = ", ".join(f"{item['name']} ({item['id']})" for item in files)
        raise ValueError(
            f"Se encontraron varios spreadsheets con ese nombre: {names}. Use el ID exacto."
        )
    return files[0]["id"]


def column_index_to_letter(index: int) -> str:
    letter = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letter = chr(65 + remainder) + letter
    return letter


def quote_sheet_name(sheet_name: str) -> str:
    sheet_name = str(sheet_name)
    if sheet_name.startswith("'") and sheet_name.endswith("'"):
        return sheet_name
    safe_name = sheet_name.replace("'", "''")
    return f"'{safe_name}'"


def find_header_column(headers: Iterable[str], month: str) -> int:
    normalized_month = MONTH_MAP.get(normalize_text(month).upper(), None)
    if not normalized_month:
        normalized_month = normalize_text(month).upper()
    for idx, header in enumerate(headers, start=1):
        if normalize_text(header).upper() == normalized_month:
            return idx
    raise ValueError(f"No se encontró la columna del mes '{month}' en los encabezados: {headers}")


def find_name_row(rows: list[list[str]], persona: str, name_column: int) -> int:
    target_name = normalize_text(persona)
    for row_index, row in enumerate(rows[1:], start=2):
        if len(row) > 0 and normalize_text(row[0]) == target_name:
            return row_index
        if name_column - 1 < len(row) and normalize_text(row[name_column - 1]) == target_name:
            return row_index
    raise ValueError(f"No se encontró a la persona '{persona}' en la hoja.")


def count_marked_months(row: list[str], start_col_idx: int = 2, end_col_idx: int | None = None) -> int:
    """Cuenta cuántas columnas de meses tienen un valor verdadero en la fila."""
    if end_col_idx is None:
        end_col_idx = len(row) - 1 if len(row) > 2 else 2
    count = 0
    for col_idx in range(start_col_idx, end_col_idx):
        if col_idx < len(row) and str(row[col_idx]).upper() in ("TRUE", "VERDADERO", "1"):
            count += 1
    return count


def mark_diezmo(
    spreadsheet_id: str,
    persona: str,
    mes: str,
    creds_json: str = "credentials.json",
    sheet_name: str | None = None,
) -> str:
    """Marca la casilla del mes indicado para la persona indicada.

    Args:
        spreadsheet_id: Id del Spreadsheet o nombre del archivo.
        persona: Nombre completo o número Nro tal como aparece en la hoja.
        mes: Mes a marcar (ej. ENE, Febrero, MAR, ...).
        creds_json: Ruta al JSON de credenciales de servicio.
        sheet_name: Nombre de la pestaña dentro del Spreadsheet. Si no se pasa, usa la primera pestaña.

    Returns:
        El rango actualizado.
    """
    spreadsheet_id = resolve_spreadsheet_id(spreadsheet_id, creds_json)
    service = get_service(creds_json)

    try:
        spreadsheet = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="properties.title,sheets(properties(title))",
        ).execute()
    except HttpError as exc:
        raise ValueError(
            "No se puede abrir el spreadsheet. Verifique el ID y los permisos del archivo."
        ) from exc

    sheets = [sheet["properties"]["title"] for sheet in spreadsheet.get("sheets", [])]
    if not sheets:
        raise ValueError("El spreadsheet no tiene pestañas visibles.")

    if sheet_name is None:
        sheet_name = sheets[0]
    elif sheet_name not in sheets:
        raise ValueError(
            f"La hoja '{sheet_name}' no existe. Hojas disponibles: {', '.join(sheets)}"
        )

    quoted_sheet = quote_sheet_name(sheet_name)
    range_name = f"{quoted_sheet}!A1:Z"
    response = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        majorDimension="ROWS",
    ).execute()

    values = response.get("values", [])
    if not values:
        raise ValueError("La hoja está vacía o no se pudo leer el rango.")

    headers = values[0]
    name_column = None
    for idx, header in enumerate(headers, start=1):
        if normalize_text(header) in {"nombres", "nombre", "name"}:
            name_column = idx
            break
    if name_column is None:
        name_column = 2

    if not persona.strip():
        raise ValueError("Debe indicar el nombre de la persona o el número Nro del tablero.")

    month_column = find_header_column(headers, mes)
    row_index = find_name_row(values, persona, name_column)

    column_letter = column_index_to_letter(month_column)
    target_range = f"{quoted_sheet}!{column_letter}{row_index}"

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=target_range,
        valueInputOption="RAW",
        body={"values": [[True]]},
    ).execute()

    return target_range


def add_persona(spreadsheet_id: str, nombre: str, creds_json: str = "credentials.json", sheet_name: str | None = None) -> str:
    """Agrega una nueva persona con el número correlativo siguiente.

    Args:
        spreadsheet_id: Id del Spreadsheet o nombre del archivo.
        nombre: Nombre de la nueva persona.
        creds_json: Ruta al JSON de credenciales.
        sheet_name: Nombre de la pestaña.

    Returns:
        El rango de la fila agregada.
    """
    spreadsheet_id = resolve_spreadsheet_id(spreadsheet_id, creds_json)
    service = get_service(creds_json)

    try:
        spreadsheet = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="properties.title,sheets(properties(title))",
        ).execute()
    except HttpError as exc:
        raise ValueError(
            "No se puede abrir el spreadsheet. Verifique el ID y los permisos del archivo."
        ) from exc

    sheets = [sheet["properties"]["title"] for sheet in spreadsheet.get("sheets", [])]
    if not sheets:
        raise ValueError("El spreadsheet no tiene pestañas visibles.")

    if sheet_name is None:
        sheet_name = sheets[0]
    elif sheet_name not in sheets:
        raise ValueError(
            f"La hoja '{sheet_name}' no existe. Hojas disponibles: {', '.join(sheets)}"
        )

    quoted_sheet = quote_sheet_name(sheet_name)
    range_name = f"{quoted_sheet}!A:Z"
    response = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        majorDimension="ROWS",
    ).execute()

    values = response.get("values", [])
    if not values or len(values) < 1:
        raise ValueError("La hoja está vacía o no tiene encabezados.")

    headers = values[0]
    if not headers or len(headers) < 2:
        raise ValueError("Los encabezados no son válidos.")

    # Encontrar el último número correlativo
    last_nro = 0
    for row in values[1:]:
        if row and row[0].strip().isdigit():
            try:
                nro = int(row[0].strip())
                if nro > last_nro:
                    last_nro = nro
            except ValueError:
                pass
    new_nro = last_nro + 1

    # Preparar la nueva fila: [Nro, Nombre, False, False, ...] para cada mes
    new_row = [str(new_nro), nombre] + [False] * (len(headers) - 2)

    # Agregar la fila al final
    append_range = f"{quoted_sheet}!A{len(values) + 1}"
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=append_range,
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [new_row]},
    ).execute()

    return f"{quoted_sheet}!A{len(values) + 1}:{column_index_to_letter(len(headers))}{len(values) + 1}"


def show_diezmos_info(spreadsheet_id: str, persona: str, creds_json: str = "credentials.json", sheet_name: str | None = None) -> str:
    """Muestra información de diezmos de una persona.

    Args:
        spreadsheet_id: Id del Spreadsheet o nombre del archivo.
        persona: Nombre completo o número Nro de la persona.
        creds_json: Ruta al JSON de credenciales.
        sheet_name: Nombre de la pestaña.

    Returns:
        Información formateada.
    """
    spreadsheet_id = resolve_spreadsheet_id(spreadsheet_id, creds_json)
    service = get_service(creds_json)

    try:
        spreadsheet = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="properties.title,sheets(properties(title))",
        ).execute()
    except HttpError as exc:
        raise ValueError(
            "No se puede abrir el spreadsheet. Verifique el ID y los permisos del archivo."
        ) from exc

    sheets = [sheet["properties"]["title"] for sheet in spreadsheet.get("sheets", [])]
    if not sheets:
        raise ValueError("El spreadsheet no tiene pestañas visibles.")

    if sheet_name is None:
        sheet_name = sheets[0]
    elif sheet_name not in sheets:
        raise ValueError(
            f"La hoja '{sheet_name}' no existe. Hojas disponibles: {', '.join(sheets)}"
        )

    quoted_sheet = quote_sheet_name(sheet_name)
    range_name = f"{quoted_sheet}!A:Z"
    response = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        majorDimension="ROWS",
    ).execute()

    values = response.get("values", [])
    if not values or len(values) < 2:
        raise ValueError("La hoja está vacía o no tiene datos.")

    headers = values[0]
    name_column = None
    for idx, header in enumerate(headers, start=1):
        if normalize_text(header) in {"nombres", "nombre", "name"}:
            name_column = idx
            break
    if name_column is None:
        name_column = 2

    target_name = normalize_text(persona)
    for row in values[1:]:
        if len(row) > 0 and normalize_text(row[0]) == target_name:
            nro = row[0] if len(row) > 0 else "N/A"
            nombre_encontrado = row[name_column - 1] if name_column - 1 < len(row) else persona
            meses_marcados = []
            for col_idx, header in enumerate(headers[2:], start=2):
                if col_idx < len(row) and str(row[col_idx]).upper() in ("TRUE", "VERDADERO", "1"):
                    meses_marcados.append(header)
            total_porcentaje = row[-1] if len(row) > len(headers) - 1 else "N/A"
            info = f"Nro: {nro}\nNombre: {nombre_encontrado}\nMeses marcados: {', '.join(meses_marcados) if meses_marcados else 'Ninguno'}\nPorcentaje Total: {total_porcentaje}"
            return info

        if name_column - 1 < len(row) and normalize_text(row[name_column - 1]) == target_name:
            nro = row[0] if len(row) > 0 else "N/A"
            nombre_encontrado = row[name_column - 1] if name_column - 1 < len(row) else persona
            meses_marcados = []
            for col_idx, header in enumerate(headers[2:], start=2):
                if col_idx < len(row) and str(row[col_idx]).upper() in ("TRUE", "VERDADERO", "1"):
                    meses_marcados.append(header)
            total_porcentaje = row[-1] if len(row) > len(headers) - 1 else "N/A"
            info = f"Nro: {nro}\nNombre: {nombre_encontrado}\nMeses marcados: {', '.join(meses_marcados) if meses_marcados else 'Ninguno'}\nPorcentaje Total: {total_porcentaje}"
            return info

    raise ValueError(f"No se encontró a la persona '{persona}' en la hoja.")


def list_all_diezmadores(spreadsheet_id: str, creds_json: str = "credentials.json", sheet_name: str | None = None) -> str:
    """Lista todos los diezmadores ordenados por porcentaje Total (mayor a menor).

    Args:
        spreadsheet_id: Id del Spreadsheet o nombre del archivo.
        creds_json: Ruta al JSON de credenciales.
        sheet_name: Nombre de la pestaña.

    Returns:
        Información formateada.
    """
    spreadsheet_id = resolve_spreadsheet_id(spreadsheet_id, creds_json)
    service = get_service(creds_json)

    try:
        spreadsheet = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="properties.title,sheets(properties(title))",
        ).execute()
    except HttpError as exc:
        raise ValueError(
            "No se puede abrir el spreadsheet. Verifique el ID y los permisos del archivo."
        ) from exc

    sheets = [sheet["properties"]["title"] for sheet in spreadsheet.get("sheets", [])]
    if not sheets:
        raise ValueError("El spreadsheet no tiene pestañas visibles.")

    if sheet_name is None:
        sheet_name = sheets[0]
    elif sheet_name not in sheets:
        raise ValueError(
            f"La hoja '{sheet_name}' no existe. Hojas disponibles: {', '.join(sheets)}"
        )

    quoted_sheet = quote_sheet_name(sheet_name)
    range_name = f"{quoted_sheet}!A:Z"
    response = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        majorDimension="ROWS",
    ).execute()

    values = response.get("values", [])
    if not values or len(values) < 2:
        raise ValueError("La hoja está vacía o no tiene datos.")

    headers = values[0]
    month_headers = headers[2:-1] if len(headers) > 3 else []
    registros = []

    for row in values[1:]:
        if len(row) >= 2:
            try:
                nro = row[0] if row[0] else "N/A"
                nombre = row[1] if len(row) > 1 else "N/A"
                total = row[-1] if len(row) > 0 else "N/A"

                # Extraer valor numérico del total
                total_str = str(total).replace("%", "").strip()
                try:
                    total_num = float(total_str)
                except ValueError:
                    total_num = 0

                month_values = []
                for col_idx in range(2, len(headers) - 1):
                    cell = row[col_idx] if col_idx < len(row) else ""
                    month_values.append(
                        "X" if str(cell).upper() in ("TRUE", "VERDADERO", "1") else ""
                    )

                registros.append((nro, nombre, total, total_num, month_values))
            except Exception:
                pass

    # Ordenar por total descendente
    registros.sort(key=lambda x: x[3], reverse=True)

    resultado = "📊 INFORMACIÓN DE DIEZMADORES (Ordenado por Total Mayor a Menor)\n"
    resultado += "=" * 100 + "\n"
    header_format = f"{'Nro':<5} {'Nombres':<35}"
    for month in month_headers:
        header_format += f" {str(month)[:3]:<3}"
    header_format += f" {'Total':<10}\n"
    resultado += header_format
    resultado += "-" * 100 + "\n"

    for nro, nombre, total, _, month_values in registros:
        row_format = f"{nro:<5} {nombre:<35}"
        for value in month_values:
            row_format += f" {value:<3}"
        row_format += f" {total:<10}\n"
        resultado += row_format

    resultado += "=" * 100 + "\n"
    resultado += f"Total de registros: {len(registros)}\n"

    return resultado


def list_active_diezmadores(spreadsheet_id: str, creds_json: str = "credentials.json", sheet_name: str | None = None) -> str:
    """Lista solo los diezmadores que tienen al menos 1 mes marcado (filtrados).

    Args:
        spreadsheet_id: Id del Spreadsheet o nombre del archivo.
        creds_json: Ruta al JSON de credenciales.
        sheet_name: Nombre de la pestaña.

    Returns:
        Información formateada.
    """
    spreadsheet_id = resolve_spreadsheet_id(spreadsheet_id, creds_json)
    service = get_service(creds_json)

    try:
        spreadsheet = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="properties.title,sheets(properties(title))",
        ).execute()
    except HttpError as exc:
        raise ValueError(
            "No se puede abrir el spreadsheet. Verifique el ID y los permisos del archivo."
        ) from exc

    sheets = [sheet["properties"]["title"] for sheet in spreadsheet.get("sheets", [])]
    if not sheets:
        raise ValueError("El spreadsheet no tiene pestañas visibles.")

    if sheet_name is None:
        sheet_name = sheets[0]
    elif sheet_name not in sheets:
        raise ValueError(
            f"La hoja '{sheet_name}' no existe. Hojas disponibles: {', '.join(sheets)}"
        )

    quoted_sheet = quote_sheet_name(sheet_name)
    range_name = f"{quoted_sheet}!A:Z"
    response = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        majorDimension="ROWS",
    ).execute()

    values = response.get("values", [])
    if not values or len(values) < 2:
        raise ValueError("La hoja está vacía o no tiene datos.")

    headers = values[0]
    month_headers = headers[2:-1] if len(headers) > 3 else []
    registros = []
    total_personas = 0
    total_inactivos = 0

    for row in values[1:]:
        if len(row) >= 2:
            try:
                nro = row[0] if row[0] else "N/A"
                nombre = row[1] if len(row) > 1 else "N/A"
                total = row[-1] if len(row) > 0 else "N/A"

                # Extraer valor numérico del total
                total_str = str(total).replace("%", "").strip()
                try:
                    total_num = float(total_str)
                except ValueError:
                    total_num = 0

                month_values = []
                has_mark = False
                for col_idx in range(2, len(headers) - 1):
                    cell = row[col_idx] if col_idx < len(row) else ""
                    is_marked = str(cell).upper() in ("TRUE", "VERDADERO", "1")
                    month_values.append("X" if is_marked else "")
                    if is_marked:
                        has_mark = True

                total_personas += 1
                # Solo agregar si tiene al menos 1 mes marcado
                if has_mark:
                    registros.append((nro, nombre, total, total_num, month_values))
                else:
                    total_inactivos += 1
            except Exception:
                pass

    # Ordenar por total descendente
    registros.sort(key=lambda x: x[3], reverse=True)

    resultado = "📊 DIEZMADORES ACTIVOS (Con al menos 1 marcado - Ordenado por Total Mayor a Menor)\n"
    resultado += "=" * 100 + "\n"
    header_format = f"{'Nro':<5} {'Nombres':<35}"
    for month in month_headers:
        header_format += f" {str(month)[:3]:<3}"
    header_format += f" {'Total':<10}\n"
    resultado += header_format
    resultado += "-" * 100 + "\n"

    for nro, nombre, total, _, month_values in registros:
        row_format = f"{nro:<5} {nombre:<35}"
        for value in month_values:
            row_format += f" {value:<3}"
        row_format += f" {total:<10}\n"
        resultado += row_format

    resultado += "=" * 100 + "\n"
    
    if total_personas > 0:
        porcentaje_activos = (len(registros) / total_personas) * 100
        porcentaje_inactivos = (total_inactivos / total_personas) * 100
        resultado += f"Diezmadores activos: {len(registros)} de {total_personas} ({porcentaje_activos:.2f}%)\n"
        resultado += f"Diezmadores inactivos (sin marcar): {total_inactivos} de {total_personas} ({porcentaje_inactivos:.2f}%)\n"
    else:
        resultado += "No hay registros de personas.\n"

    return resultado


def list_non_diezmadores(
    spreadsheet_id: str,
    creds_json: str = "credentials.json",
    sheet_name: str | None = None,
    diezmaciones: int | None = None,
) -> str:
    """Lista personas según la cantidad de meses marcados.

    Args:
        spreadsheet_id: Id del Spreadsheet o nombre del archivo.
        creds_json: Ruta al JSON de credenciales.
        sheet_name: Nombre de la pestaña.
        diezmaciones: Cantidad exacta de diezmaciones a filtrar. Si es None, usa 0.

    Returns:
        Información formateada con resumen.
    """
    spreadsheet_id = resolve_spreadsheet_id(spreadsheet_id, creds_json)
    service = get_service(creds_json)

    try:
        spreadsheet = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="properties.title,sheets(properties(title))",
        ).execute()
    except HttpError as exc:
        raise ValueError(
            "No se puede abrir el spreadsheet. Verifique el ID y los permisos del archivo."
        ) from exc

    sheets = [sheet["properties"]["title"] for sheet in spreadsheet.get("sheets", [])]
    if not sheets:
        raise ValueError("El spreadsheet no tiene pestañas visibles.")

    if sheet_name is None:
        sheet_name = sheets[0]
    elif sheet_name not in sheets:
        raise ValueError(
            f"La hoja '{sheet_name}' no existe. Hojas disponibles: {', '.join(sheets)}"
        )

    quoted_sheet = quote_sheet_name(sheet_name)
    range_name = f"{quoted_sheet}!A:Z"
    response = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        majorDimension="ROWS",
    ).execute()

    values = response.get("values", [])
    if not values or len(values) < 2:
        raise ValueError("La hoja está vacía o no tiene datos.")

    headers = values[0]
    no_diezmadores = []
    total_personas = 0
    target_diezmaciones = 0 if diezmaciones is None else int(diezmaciones)

    for row in values[1:]:
        if len(row) >= 2 and row[0] and str(row[0]).strip().isdigit():
            total_personas += 1
            nro = row[0]
            nombre = row[1] if len(row) > 1 else "N/A"
            total = row[-1] if len(row) > 0 else "N/A"
            cantidad_diezmos = count_marked_months(row, start_col_idx=2, end_col_idx=len(row) - 1)

            if cantidad_diezmos == target_diezmaciones:
                no_diezmadores.append((nro, nombre, total, cantidad_diezmos))

    if target_diezmaciones == 0:
        titulo = "⚠️  PERSONAS SIN DIEZMACIONES REGISTRADAS"
    else:
        titulo = f"📋  PERSONAS CON {target_diezmaciones} DIEZMACIONES REGISTRADAS"

    resultado = f"{titulo}\n"
    resultado += "=" * 100 + "\n"
    resultado += f"{'Nro':<5} {'Nombres':<35} {'Diezmos':<8} {'Total':<10}\n"
    resultado += "-" * 100 + "\n"

    for nro, nombre, total, cantidad_diezmos in no_diezmadores:
        resultado += f"{nro:<5} {nombre:<35} {cantidad_diezmos:<8} {total:<10}\n"

    resultado += "=" * 100 + "\n"

    if total_personas > 0:
        porcentaje = (len(no_diezmadores) / total_personas) * 100
        resultado += f"Personas encontradas: {len(no_diezmadores)} de {total_personas}\n"
        resultado += f"Porcentaje: {porcentaje:.2f}%\n"
    else:
        resultado += "No hay registros de personas.\n"

    return resultado


# =============================================================================
# NUEVAS FUNCIONES PARA GESTIÓN DE SOBRES DE DIEZMOS
# =============================================================================

def normalize_month_label(value: str) -> str:
    """Normaliza etiquetas de meses a formato estándar (ENE, FEB, etc.)."""
    normalized = normalize_text(value).upper()
    return MONTH_MAP.get(normalized, normalized)


def resolve_folder_id(folder_ref: str, creds_json: str = "credentials.json") -> str:
    """Resuelve ID de carpeta desde URL o ID directo."""
    folder_ref = str(folder_ref).strip()
    # Si contiene URL de Drive, extrae el ID
    if "drive.google.com" in folder_ref and "/folders/" in folder_ref:
        return folder_ref.split("/folders/")[-1].split("?")[0]
    # Si es ID válido (largo y caracteres válidos)
    if re.fullmatch(r"[a-zA-Z0-9_-]+", folder_ref) and len(folder_ref) > 15:
        return folder_ref
    # Si no, usa el ID por defecto
    return DEFAULT_DIEZMADORES_FOLDER_ID


def list_person_files(folder_id: str, creds_json: str = "credentials.json") -> list[dict]:
    """Lista todos los archivos de personas en la carpeta."""
    drive_service = get_service(creds_json, service_name="drive", version="v3")
    query = f"'{folder_id}' in parents and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
    response = drive_service.files().list(
        q=query,
        fields="files(id,name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        corpora="allDrives",
    ).execute()
    return response.get("files", [])


def search_spreadsheets_by_name(query_name: str, creds_json: str = "credentials.json") -> list[dict]:
    """Busca spreadsheets por nombre en Drive cuando la carpeta no devuelve resultados."""
    drive_service = get_service(creds_json, service_name="drive", version="v3")
    safe_name = query_name.replace("'", "''")
    queries = [
        f"name contains '{safe_name}' and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false",
        f"name = '{safe_name}' and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false",
    ]

    for query in queries:
        response = drive_service.files().list(
            q=query,
            fields="files(id,name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            corpora="allDrives",
        ).execute()
        files = response.get("files", [])
        if files:
            return files
    return []


def get_service_account_email(creds_json: str = "credentials.json") -> str:
    """Devuelve el correo de la cuenta de servicio si está disponible."""
    if not os.path.exists(creds_json):
        return ""
    try:
        with open(creds_json, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data.get("client_email", "")
    except Exception:
        return ""


def extract_person_info(filename: str) -> tuple[str, str]:
    """Extrae código y nombre de la persona del nombre del archivo.

    Formatos aceptados:
    - 005-Roberto Perez Paredes-Diezmos-SILOE
    - 005-Roberto Perez Paredes-SILOE
    - 005-Roberto Perez Paredes
    """
    name_clean = filename.replace(".gsheet", "").replace(".xlsx", "").strip()
    suffixes = ["-SILOE", "-DIEZMOS"]
    for suffix in suffixes:
        if name_clean.upper().endswith(suffix.upper()):
            name_clean = name_clean[: -len(suffix)].rstrip("-")
            break

    first_dash = name_clean.find("-")
    if first_dash == -1:
        return "", name_clean.strip()

    codigo = name_clean[:first_dash].strip()
    second_dash = name_clean.find("-", first_dash + 1)
    if second_dash != -1:
        nombre = name_clean[first_dash + 1:second_dash].strip()
    else:
        nombre = name_clean[first_dash + 1:].strip()

    return codigo, nombre


def find_person_spreadsheet(folder_id: str, persona_ref: str, creds_json: str = "credentials.json") -> dict:
    """Busca archivo de persona por código o nombre."""
    persona_norm = normalize_text(persona_ref).upper()

    files = list_person_files(folder_id, creds_json)
    if not files:
        files = search_spreadsheets_by_name(persona_ref, creds_json)

    for file in files:
        codigo, nombre = extract_person_info(file["name"])
        code_norm = normalize_text(codigo).upper()
        name_norm = normalize_text(nombre).upper()

        if persona_norm == code_norm or persona_norm in name_norm:
            return file

    if not files:
        account_email = get_service_account_email(creds_json)
        if account_email:
            raise ValueError(
                f"No se encontró el archivo para '{persona_ref}'. Verifique que la carpeta sea compartida con la cuenta de servicio '{account_email}' y que el ID de carpeta sea correcto."
            )
        raise ValueError(
            f"No se encontró el archivo para '{persona_ref}'. Verifique el ID de la carpeta y los permisos de Drive."
        )

    raise ValueError(f"No se encontró archivo para '{persona_ref}' en la carpeta.")


def find_header_row(rows: list[list[str]]) -> tuple[int, list[str]]:
    """Encuentra la fila de encabezados que contiene 'MES' y las columnas D1-D5."""
    for row_idx, row in enumerate(rows, start=1):
        if any(normalize_text(cell).upper() == "MES" for cell in row):
            return row_idx, row
    raise ValueError("No se encontró la fila de encabezados con 'MES'.")


def find_month_row(rows: list[list[str]], month: str, start_row: int = 1) -> int:
    """Encuentra la fila que contiene el mes especificado en la primera columna."""
    month_norm = normalize_month_label(month)
    for offset, row in enumerate(rows[start_row - 1 :], start=0):
        if not row:
            continue
        cell = row[0] if len(row) > 0 else ""
        if normalize_month_label(cell) == month_norm:
            return start_row + offset
    raise ValueError(f"No se encontró mes '{month}' en la hoja.")


def find_sunday_column(headers: Iterable[str], domingo: str | int) -> int:
    """Encuentra columna del domingo (D1, D2, D3, D4, D5)."""
    domingo_str = str(domingo).strip().upper()
    if not domingo_str.startswith("D"):
        domingo_str = f"D{domingo_str}"
    
    for idx, header in enumerate(headers, start=1):
        header_norm = normalize_text(header).upper()
        if header_norm == normalize_text(domingo_str).upper():
            return idx
    raise ValueError(f"No se encontró columna para '{domingo}'. Esperado: D1-D5")


def registrar_monto_sobre(persona_ref: str, mes: str, domingo: str | int, monto: float | str,
                         folder_id: str = DEFAULT_DIEZMADORES_FOLDER_ID,
                         creds_json: str = "credentials.json", year: int = 2026) -> str:
    """Registra monto en el sobre de una persona."""
    person_file = find_person_spreadsheet(folder_id, persona_ref, creds_json)
    spreadsheet_id = person_file["id"]
    codigo, nombre = extract_person_info(person_file["name"])
    
    if not isinstance(monto, (int, float)):
        monto = parse_monto(monto)

    service = get_service(creds_json)
    
    spreadsheet = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets(properties(title))"
    ).execute()
    sheets = [sheet["properties"]["title"] for sheet in spreadsheet.get("sheets", [])]
    
    sheet_name = None
    for sheet in sheets:
        if str(year) in sheet:
            sheet_name = sheet
            break
    if not sheet_name:
        sheet_name = sheets[0]
    
    quoted_sheet = quote_sheet_name(sheet_name)
    response = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{quoted_sheet}!A:Z"
    ).execute()
    
    values = response.get("values", [])
    if not values:
        raise ValueError(f"Hoja '{sheet_name}' esta vacía.")
    
    header_row_index, headers = find_header_row(values)
    month_row = find_month_row(values, mes, start_row=header_row_index + 1)
    sunday_col = find_sunday_column(headers, domingo)
    
    col_letter = column_index_to_letter(sunday_col)
    target_range = f"{quoted_sheet}!{col_letter}{month_row}"
    
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=target_range,
        valueInputOption="USER_ENTERED",
        body={"values": [[float(monto)]]}
    ).execute()
    
    mensaje_monto = format_currency_bs(float(monto))
    return f"{mensaje_monto} registrado en {nombre} ({codigo}) - {normalize_month_label(mes)} - {domingo}"


def generar_reporte_sobre(persona_ref: str, folder_id: str = DEFAULT_DIEZMADORES_FOLDER_ID,
                         creds_json: str = "credentials.json", year: int = 2026) -> str:
    """Genera reporte individual de una persona."""
    person_file = find_person_spreadsheet(folder_id, persona_ref, creds_json)
    spreadsheet_id = person_file["id"]
    codigo, nombre = extract_person_info(person_file["name"])
    
    service = get_service(creds_json)
    spreadsheet = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets(properties(title))"
    ).execute()
    sheets = [sheet["properties"]["title"] for sheet in spreadsheet.get("sheets", [])]
    
    sheet_name = None
    for sheet in sheets:
        if str(year) in sheet:
            sheet_name = sheet
            break
    if not sheet_name:
        sheet_name = sheets[0]
    
    quoted_sheet = quote_sheet_name(sheet_name)
    response = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{quoted_sheet}!A:Z"
    ).execute()
    
    values = response.get("values", [])
    if not values:
        raise ValueError(f"Hoja '{sheet_name}' está vacía.")

    header_row_index, headers = find_header_row(values)
    sunday_columns = [idx for idx, header in enumerate(headers) if normalize_text(header) in {"d1", "d2", "d3", "d4", "d5"}]
    if not sunday_columns:
        raise ValueError("No se encontraron columnas D1-D5 en el reporte individual.")
    total_col_idx = next((idx for idx, header in enumerate(headers) if normalize_text(header) == "total"), len(headers) - 1)

    reporte = f"\n📋 REPORTE DE SOBRE DE DIEZMOS\n"
    reporte += f"Persona: {nombre} ({codigo})\n"
    reporte += f"Año: {year} | Hoja: {sheet_name}\n"
    reporte += "=" * 110 + "\n"
    reporte += f"{'MES':<15} {'D1':<12} {'D2':<12} {'D3':<12} {'D4':<12} {'D5':<12} {'Total':<12}\n"
    reporte += "-" * 110 + "\n"

    total_sum = 0.0
    for row in values[header_row_index:]:
        if not row or not str(row[0]).strip():
            continue
        mes = str(row[0]).strip()
        if mes.upper() == "TOTAL":
            continue

        valores_domingo = [str(row[col_idx]).strip() if col_idx < len(row) else "" for col_idx in sunday_columns]
        total_value = str(row[total_col_idx]).strip() if total_col_idx < len(row) else ""
        total_num = 0.0
        if total_value:
            try:
                total_num = parse_monto(total_value)
            except ValueError:
                try:
                    total_num = float(total_value.replace(",", "."))
                except Exception:
                    total_num = 0.0

        total_sum += total_num
        reporte += f"{mes:<15}"
        for val in valores_domingo:
            reporte += f" {val:<12}"
        reporte += f" {total_value:<12}\n"

    reporte += "=" * 110 + "\n"
    reporte += f"Suma de Totales: {format_currency_bs(total_sum)}\n"
    reporte += "=" * 110 + "\n"
    return reporte


def generar_reporte_por_mes(mes: str, folder_id: str = DEFAULT_DIEZMADORES_FOLDER_ID,
                           creds_json: str = "credentials.json", year: int = 2026) -> str:
    """Genera reporte de todas las personas para un mes especifico."""
    files = list_person_files(folder_id, creds_json)
    mes_norm = normalize_month_label(mes)
    
    reporte = f"\n📊 REPORTE POR MES - {mes_norm} ({year})\n"
    reporte += "=" * 100 + "\n"
    reporte += f"{'Codigo':<10} {'Nombre':<35} {'D1':<12} {'D2':<12} {'D3':<12} {'D4':<12} {'D5':<12}\n"
    reporte += "-" * 100 + "\n"
    
    for file in files:
        try:
            codigo, nombre = extract_person_info(file["name"])
            spreadsheet_id = file["id"]
            
            service = get_service(creds_json)
            spreadsheet = service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                fields="sheets(properties(title))"
            ).execute()
            sheets = [sheet["properties"]["title"] for sheet in spreadsheet.get("sheets", [])]
            
            sheet_name = None
            for sheet in sheets:
                if str(year) in sheet:
                    sheet_name = sheet
                    break
            if not sheet_name:
                sheet_name = sheets[0]
            
            quoted_sheet = quote_sheet_name(sheet_name)
            response = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=f"{quoted_sheet}!A:Z"
            ).execute()
            
            values = response.get("values", [])
            
            month_row_idx = None
            for row_idx, row in enumerate(values):
                if row and normalize_month_label(row[0]) == mes_norm:
                    month_row_idx = row_idx
                    break
            
            if month_row_idx is not None:
                row = values[month_row_idx]
                valores_domingo = []
                for col_idx in range(1, 6):
                    val = row[col_idx] if col_idx < len(row) else ""
                    valores_domingo.append(str(val).strip())
                
                fila = f"{codigo:<10} {nombre:<35}"
                for val in valores_domingo:
                    fila += f" {val:<12}"
                reporte += fila + "\n"
        except Exception as e:
            reporte += f"Aviso en {file['name']}: {str(e)}\n"
    
    reporte += "=" * 100 + "\n"
    return reporte


def menu_gestion_tablero(spreadsheet_ref: str, creds_json: str = "credentials.json", sheet_name: str = "2026"):
    """Menú para gestionar Tablero de Diezmos (funcionamiento anterior)."""
    while True:
        print("\n=== GESTIÓN DE TABLERO DE DIEZMOS ===")
        print("1. Actualizar Diezmo")
        print("2. Agregar Persona")
        print("3. Información Individual")
        print("4. Listar Todos los Diezmadores")
        print("5. Listar Diezmadores Activos (Con al menos 1 marcado)")
        print("6. Listar Personas Sin Diezmaciones")
        print("7. Volver")
        opcion = input("Seleccione una opción (1-7): ").strip()

        if opcion == "1":
            persona = input("Nro o nombre de la persona: ").strip()
            mes = input("Mes (ej. ENE, FEB): ").strip()
            try:
                mark_diezmo(spreadsheet_ref, persona, mes, creds_json, sheet_name)
                print("✅ Diezmo marcado correctamente.")
            except Exception as e:
                print(f"❌ Error: {e}")

        elif opcion == "2":
            nombre = input("Nombre de la nueva persona: ").strip()
            try:
                add_persona(spreadsheet_ref, nombre, creds_json, sheet_name)
                print("✅ Persona agregada correctamente.")
            except Exception as e:
                print(f"❌ Error: {e}")

        elif opcion == "3":
            persona = input("Nro o nombre de la persona: ").strip()
            try:
                info = show_diezmos_info(spreadsheet_ref, persona, creds_json, sheet_name)
                print(f"\n{info}")
            except Exception as e:
                print(f"❌ Error: {e}")

        elif opcion == "4":
            try:
                info = list_all_diezmadores(spreadsheet_ref, creds_json, sheet_name)
                print(f"\n{info}")
            except Exception as e:
                print(f"❌ Error: {e}")

        elif opcion == "5":
            try:
                info = list_active_diezmadores(spreadsheet_ref, creds_json, sheet_name)
                print(f"\n{info}")
            except Exception as e:
                print(f"❌ Error: {e}")

        elif opcion == "6":
            cantidad = input("Cantidad de diezmaciones a mostrar (0=ninguna, 3=tres veces, dejar vacío para 0): ").strip()
            try:
                cantidad_num = int(cantidad) if cantidad else 0
                info = list_non_diezmadores(spreadsheet_ref, creds_json, sheet_name, diezmaciones=cantidad_num)
                print(f"\n{info}")
            except ValueError:
                print("❌ Debe ingresar un número válido.")
            except Exception as e:
                print(f"❌ Error: {e}")

        elif opcion == "7":
            break
        else:
            print("❌ Opción inválida.")


def menu_gestion_sobres(folder_id: str = DEFAULT_DIEZMADORES_FOLDER_ID,
                       creds_json: str = "credentials.json", year: int = 2026):
    """Menú para gestionar Sobres de Diezmos (nuevas funcionalidades)."""
    while True:
        print(f"\n=== GESTIÓN DE SOBRES DE DIEZMOS {year} ===")
        print("1. Registrar Monto")
        print("2. Reporte de Persona")
        print("3. Volver")
        opcion = input("Seleccione una opción (1-3): ").strip()

        if opcion == "1":
            persona = input("Código o nombre de persona: ").strip()
            mes = input("Mes (ej. ENE, FEB, jul): ").strip()
            domingo = input("Número de domingo (1-5 o D1-D5): ").strip()
            monto = input("Monto a registrar: ").strip()
            try:
                resultado = registrar_monto_sobre(persona, mes, domingo, monto, folder_id, creds_json, year)
                print(resultado)
            except Exception as e:
                print(f"❌ Error: {e}")

        elif opcion == "2":
            persona = input("Código o nombre de persona: ").strip()
            try:
                reporte = generar_reporte_sobre(persona, folder_id, creds_json, year)
                print(reporte)
            except Exception as e:
                print(f"❌ Error: {e}")

        elif opcion == "3":
            break
        else:
            print("❌ Opción inválida.")


def menu_principal(spreadsheet_ref: str, creds_json: str = "credentials.json", sheet_name: str = "2026"):
    """Menú principal redesñado con dos áreas de gestión."""
    while True:
        print("\n" + "="*60)
        print(" SISTEMA DE GESTIÓN DE DIEZMOS SILOE")
        print(" by robperezsystem - v1.4")
        print("="*60)
        print("1. Gestión de Tablero de Diezmos")
        print("2. Gestión de Sobres de Diezmos")
        print("3. Limpiar pantalla")
        print("4. Salir")
        print("="*60)
        opcion = input("Seleccione una opción (1-4): ").strip()

        if opcion == "1":
            menu_gestion_tablero(spreadsheet_ref, creds_json, sheet_name)

        elif opcion == "2":
            menu_gestion_sobres(creds_json=creds_json, year=int(sheet_name) if sheet_name.isdigit() else 2026)

        elif opcion == "3":
            os.system('cls' if os.name == 'nt' else 'clear')
            print("✨ Pantalla limpia")

        elif opcion == "4":
            print("👋 ¡Hasta luego!")
            break

        else:
            print("❌ Opción inválida. Intente de nuevo.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Gestión de Diezmos en Google Sheets.")
    parser.add_argument(
        "spreadsheet_id",
        nargs="?",
        default="Tablero-Diezmos-SILOE",
        help="ID del Spreadsheet o nombre del archivo de Google Sheets (por defecto: Tablero-Diezmos-SILOE)",
    )
    parser.add_argument("--sheet-name", default="2026", help="Nombre de la pestaña dentro del spreadsheet (por defecto: 2026)")
    parser.add_argument("--creds", default="credentials.json", help="Ruta al archivo JSON de credenciales")
    args = parser.parse_args()

    menu_principal(args.spreadsheet_id, args.creds, args.sheet_name)
