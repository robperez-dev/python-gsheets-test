# Gestor de Diezmos - Python Google Sheets

Sistema de gestión de diezmos en Google Sheets que permite marcar, agregar personas y consultar información de diezmos de forma interactiva.

## 📋 Requisitos previos

- Python 3.13+
- Acceso a Google Drive y Google Sheets API habilitada
- Archivo de credenciales JSON de Google Cloud (Cuenta de Servicio)

## ⚙️ Instalación

### 1. Clonar o descargar el proyecto

```bash
cd tu-ruta/python-gsheets
```

### 2. Crear entorno virtual (opcional pero recomendado)

```bash
python -m venv .venv
# En Windows
.\.venv\Scripts\activate
# En Linux/Mac
source .venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install google-api-python-client google-auth
```

## 🔐 Configuración de Credenciales

### Paso 1: Crear Cuenta de Servicio en Google Cloud

1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
2. Crea un nuevo proyecto
3. Habilita las APIs:
   - Google Sheets API
   - Google Drive API
4. Crea una **Cuenta de Servicio**
5. Genera una **clave JSON** y descargar
6. Guarda el archivo como `credentials.json` en la carpeta del proyecto

### Paso 2: Compartir el Spreadsheet

1. Abre tu spreadsheet en Google Sheets (ej: "Tablero-Diezmos-SILOE")
2. Copia el correo de la cuenta de servicio (de `credentials.json`)
3. Comparte el spreadsheet con ese correo

## 🚀 Modo de Uso

### Ejecución básica

```bash
python sheet.py
```

Abre el menú interactivo con el archivo "Tablero-Diezmos-SILOE" por defecto y la hoja "2026".

### Con parámetros personalizados

```bash
python sheet.py "Tu-Archivo-Nombre" --sheet-name "2025" --creds "tu-credenciales.json"
```

## 📊 Funcionalidades del Menú

### 1. Actualizar Tablero Diezmo

Marca la casilla de diezmo para una persona en un mes específico.

**Pasos:**
1. Selecciona opción `1`
2. Ingresa el nombre de la persona
3. Ingresa el mes (ej: ENE, FEB, MAR, ENERO, FEBRERO, etc.)
4. Se marcará la casilla automáticamente

**Ejemplo:**
```
Ingrese el nombre de la persona: Roberto Pérez Paredes
Ingrese el mes a marcar (ej. ENE, FEB, MAR): MAR
✅ Casilla marcada en: '2026'!D2
```

### 2. Agregar Persona

Agrega una nueva persona con el siguiente número correlativo disponible.

**Pasos:**
1. Selecciona opción `2`
2. Ingresa el nombre de la nueva persona
3. Se agregará automáticamente con:
   - Nro: Número correlativo siguiente
   - Nombre: El proporcionado
   - Meses: Todos en falso (sin marcar)

**Ejemplo:**
```
Ingrese el nombre de la nueva persona: Juan García
✅ Persona agregada en: '2026'!A14:Z14
```

### 3. Mostrar Información de Diezmos

Consulta la información de diezmos de una persona.

**Pasos:**
1. Selecciona opción `3`
2. Ingresa el nombre de la persona
3. Se mostrará:
   - Nro: Número correlativo
   - Nombre: Nombre completo
   - Meses marcados: Lista de meses con diezmo registrado
   - Porcentaje Total: Porcentaje en la columna Total

**Ejemplo:**
```
Ingrese el nombre de la persona: Flia. Montenegro (Pastoral)
📊 Información de Diezmos:
Nro: 1
Nombre: Flia. Montenegro (Pastoral)
Meses marcados: ENE, FEB, MAR
Porcentaje Total: 25%
```

### 4. Salir

Cierra el programa.

## 📝 Estructura del Spreadsheet

El spreadsheet debe tener la siguiente estructura:

| Nro | Nombres | ENE | FEB | MAR | ABR | MAY | JUN | JUL | AGO | SEP | OCT | NOV | DIC | Total |
|-----|---------|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-------|
| 1   | Persona 1 | ☑ | ☑ | ☑ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | 25% |
| 2   | Persona 2 | ☐ | ☑ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | 8% |

**Requisitos:**
- Primera columna: Números correlativos
- Segunda columna: Nombres de personas
- Encabezados de meses: ENE, FEB, MAR, ABR, MAY, JUN, JUL, AGO, SEP, OCT, NOV, DIC
- Última columna: Total (opcional para visualizar porcentaje)
- Las celdas de meses deben ser tipo **Checkbox** en Google Sheets

## 🛠️ Funciones Internas

### `mark_diezmo()`
Marca la casilla del mes para una persona específica.

### `add_persona()`
Agrega una nueva persona con correlativo automático.

### `show_diezmos_info()`
Muestra información de diezmos de una persona.

### `resolve_spreadsheet_id()`
Busca el ID del spreadsheet por nombre en Google Drive.

### `normalize_text()`
Normaliza texto para búsquedas case-insensitive.

## 🐛 Solución de Problemas

### Error: "No se encontró el archivo de credenciales"
**Solución:** Asegúrate que `credentials.json` esté en la carpeta del proyecto.

### Error: "No se encontró ningún spreadsheet con el nombre..."
**Solución:** 
- Verifica el nombre exacto del spreadsheet
- Asegúrate que el correo de la cuenta de servicio tiene acceso
- O pasa directamente el ID del spreadsheet

### Error: "La persona no fue encontrada"
**Solución:**
- Verifica que el nombre esté exactamente como aparece en la hoja
- El sistema es flexible con espacios y mayúsculas

### Las casillas no se marcan
**Solución:**
- Asegúrate que las celdas sean tipo "Checkbox" en Google Sheets
- Verifica que el número de fila y columna sean correctos

## � Generar ejecutables por versión

Puedes usar el script de PowerShell para crear una nueva versión sin sobrescribir la anterior:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_release.ps1 -Version "v1.3"
```

Eso generará archivos como:
- Gestor-Diezmos-v1.3.exe
- Sistema-Gestor-Diezmos-v1.3.exe

## �📞 Soporte

Para reportar errores o sugerencias, contacta al administrador del proyecto.

## 📄 Licencia

Este proyecto es de uso interno.

---

**Última actualización:** 18 de abril de 2026
