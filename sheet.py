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


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value).strip().lower())


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
        if name_column - 1 < len(row) and normalize_text(row[name_column - 1]) == target_name:
            return row_index
    raise ValueError(f"No se encontró a la persona '{persona}' en la hoja.")


def mark_diezmo(spreadsheet_id: str, persona: str, mes: str, creds_json: str = "credentials.json", sheet_name: str | None = None) -> str:
    """Marca la casilla del mes indicado para la persona indicada.

    Args:
        spreadsheet_id: Id del Spreadsheet o nombre del archivo.
        persona: Nombre completo tal como aparece en la hoja.
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
        persona: Nombre de la persona.
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
        if name_column - 1 < len(row) and normalize_text(row[name_column - 1]) == target_name:
            nro = row[0] if len(row) > 0 else "N/A"
            meses_marcados = []
            for col_idx, header in enumerate(headers[2:], start=2):
                if col_idx < len(row) and str(row[col_idx]).upper() in ("TRUE", "VERDADERO", "1"):
                    meses_marcados.append(header)
            total_porcentaje = row[-1] if len(row) > len(headers) - 1 else "N/A"
            info = f"Nro: {nro}\nNombre: {persona}\nMeses marcados: {', '.join(meses_marcados) if meses_marcados else 'Ninguno'}\nPorcentaje Total: {total_porcentaje}"
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
    resultado += "=" * 80 + "\n"
    header_format = f"{'Nro':<5} {'Nombres':<35}"
    for month in month_headers:
        header_format += f" {str(month)[:3]:<3}"
    header_format += f" {'Total':<10}\n"
    resultado += header_format
    resultado += "-" * 80 + "\n"

    for nro, nombre, total, _, month_values in registros:
        row_format = f"{nro:<5} {nombre:<35}"
        for value in month_values:
            row_format += f" {value:<3}"
        row_format += f" {total:<10}\n"
        resultado += row_format

    resultado += "=" * 80 + "\n"
    resultado += f"Total de registros: {len(registros)}\n"

    return resultado


def list_non_diezmadores(spreadsheet_id: str, creds_json: str = "credentials.json", sheet_name: str | None = None) -> str:
    """Lista todas las personas que no tienen ningún mes marcado.

    Args:
        spreadsheet_id: Id del Spreadsheet o nombre del archivo.
        creds_json: Ruta al JSON de credenciales.
        sheet_name: Nombre de la pestaña.

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

    for row in values[1:]:
        if len(row) >= 2 and row[0] and str(row[0]).strip().isdigit():
            total_personas += 1
            nro = row[0]
            nombre = row[1] if len(row) > 1 else "N/A"
            total = row[-1] if len(row) > 0 else "N/A"

            # Verificar si ningún mes está marcado (columnas 2 a -1, excluyendo Total)
            tiene_diezmo = False
            for col_idx in range(2, len(row) - 1):
                if str(row[col_idx]).upper() in ("TRUE", "VERDADERO", "1"):
                    tiene_diezmo = True
                    break

            if not tiene_diezmo:
                no_diezmadores.append((nro, nombre, total))

    resultado = "⚠️  PERSONAS SIN DIEZMACIONES REGISTRADAS\n"
    resultado += "=" * 60 + "\n"
    resultado += f"{'Nro':<5} {'Nombres':<35} {'Total':<10}\n"
    resultado += "-" * 60 + "\n"

    for nro, nombre, total in no_diezmadores:
        resultado += f"{nro:<5} {nombre:<35} {total:<10}\n"

    resultado += "=" * 60 + "\n"
    
    if total_personas > 0:
        porcentaje_no_diezmo = (len(no_diezmadores) / total_personas) * 100
        resultado += f"Personas sin diezmaciones: {len(no_diezmadores)} de {total_personas}\n"
        resultado += f"Porcentaje de personas sin diezmaciones: {porcentaje_no_diezmo:.2f}%\n"
    else:
        resultado += "No hay registros de personas.\n"

    return resultado


def menu_principal(spreadsheet_ref: str, creds_json: str = "credentials.json", sheet_name: str = "2026"):
    while True:
        print("\n=== CONTROL Tablero de Diezmos SILOE===")
        print("1. Actualizar Tablero Diezmo")
        print("2. Agregar Persona al Tablero")
        print("3. Mostrar Información de Diezmos (Individual)")
        print("4. Mostrar Información Diezmadores (Ordenado por Total)")
        print("5. Mostrar Personas Sin Diezmaciones")
        print("6. Salir")
        opcion = input("Seleccione una opción (1-6): ").strip()

        if opcion == "1":
            persona = input("Ingrese el nombre de la persona: ").strip()
            mes = input("Ingrese el mes a marcar (ej. ENE, FEB, MAR): ").strip()
            try:
                updated_range = mark_diezmo(spreadsheet_ref, persona, mes, creds_json, sheet_name)
                print(f"✅ Casilla marcada en: {updated_range}")
            except Exception as e:
                print(f"❌ Error: {e}")

        elif opcion == "2":
            nombre = input("Ingrese el nombre de la nueva persona: ").strip()
            try:
                added_range = add_persona(spreadsheet_ref, nombre, creds_json, sheet_name)
                print(f"✅ Persona agregada en: {added_range}")
            except Exception as e:
                print(f"❌ Error: {e}")

        elif opcion == "3":
            persona = input("Ingrese el nombre de la persona: ").strip()
            try:
                info = show_diezmos_info(spreadsheet_ref, persona, creds_json, sheet_name)
                print(f"\n📊 Información de Diezmos:\n{info}")
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
                info = list_non_diezmadores(spreadsheet_ref, creds_json, sheet_name)
                print(f"\n{info}")
            except Exception as e:
                print(f"❌ Error: {e}")

        elif opcion == "6":
            print("👋 Saliendo...")
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
