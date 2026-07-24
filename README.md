# Deltarune — Traducción al Español Chileno 🇨🇱

Traducción de **Deltarune** al español chileno (Capítulo 1 y siguientes).

El flujo tiene **dos programas**: uno que usa solo el mantenedor para generar la
traducción desde el Google Sheet, y otro que se reparte a la comunidad para
parchar el juego. El Google Sheet y las credenciales **nunca** se exponen: al
repo solo llega el resultado.

```
Cap. 1  (texto externo lang_en.json):
  Sheet ──[builder text]──▶ dist/chapter1/texts/lang_cl.json ──[patcher]──▶ intercambia el JSON

Cap. 2+ (texto dentro de data.win):
  data.win ──[builder extract]──▶ semilla CSV ──▶ Sheet
  Sheet ──[builder data + UTMT]──▶ parche binario (.patch) ──[patcher]──▶ aplica sobre TU data.win
```

El parche de Cap.2+ es un **diff binario** (bsdiff/detools): no redistribuye el
juego, se aplica sobre el `data.win` que el jugador ya tiene, y solo funciona con
la misma versión del juego (se verifica por SHA-256).

## Estructura del repo

```
scripts/
  dr_core.py     núcleo compartido (carga, validación, seguridad, parcheo)
  builder.py     PROGRAMA 1 — genera artefactos desde el Sheet (solo mantenedor)
  patcher.py     PROGRAMA 2 — baja del repo y parcha el juego (se reparte)
  utmt/
    export_strings.csx   UTMT: data.win -> JSON de strings de diálogo
    import_strings.csx   UTMT: reinyecta la traducción en el data.win
dist/
  chapter1/
    manifest.json              índice de assets + sha256
    texts/lang_cl.json(.sha256) la traducción publicada (Cap.1)
  chapter2/
    manifest.json
    data/chapter2.patch        parche binario del data.win (Cap.2+)
original_lang/
  lang_en.json   texto original en inglés (referencia para validar Cap.1)
sheets/
  chapterN_seed.csv  semillas generadas por `extract` para subir al Sheet
```

Cada capítulo se describe con un `manifest.json`. Tipos de asset implementados:
`text` (Cap.1, intercambia `lang_en.json`) y `data` (Cap.2+, parche binario del
`data.win`). `image` / `font` se agregarán sin rehacer el flujo.

## Para USAR la traducción (jugadores)

### GUI (recomendado)
1. Descarga el `.exe` en *Releases* (o `patcher.py`) y ábrelo.
2. Elige el **Capítulo**.
3. Auto-detecta el juego; si no, botón **Ubicar juego...**.
4. Un solo botón: **♥ PARCHAR AL ESPAÑOL**.
5. Para volver al inglés: link **restaurar original** (restaura todos los backups).

### Línea de comandos
```bash
python scripts/patcher.py patch --repo Exesito/deltarune-chile-traduccion@main --chapter 2 --game "RUTA/DELTARUNE"
python scripts/patcher.py restore --game "RUTA/DELTARUNE"
```

El parchador respalda el original (`*.orig.bak`) antes de tocar nada, verifica el
**SHA-256** (del artefacto y, en Cap.2+, de tu `data.win` antes y después),
valida el esquema, y solo descarga desde GitHub por HTTPS.

## Para GENERAR/actualizar la traducción (mantenedor)

Requiere el Sheet compartido como **"cualquiera con el link: lector"**. Para
Cap.2+ además necesitas **UndertaleModCli** (busca en `--utmt`, `$UTMT_CLI`,
`PATH`, o `~/tools/utmt-cli/extracted/UndertaleModCli`).

```bash
cd scripts

# --- Cap. 1 (texto externo) ---
python builder.py text --sheet "https://docs.google.com/spreadsheets/d/XXXX/edit" --publish

# --- Cap. 2+ : 1) sacar los strings del juego para sembrar el Sheet ---
python builder.py extract --datawin "RUTA/DELTARUNE/chapter2_windows/data.win" --chapter 2
#   -> genera sheets/chapter2_seed.csv (id, en, cl). Súbelo como pestaña nueva del Sheet.

# --- Cap. 2+ : 2) construir el parche desde el Sheet (pestaña gid=123456) ---
python builder.py data --sheet XXXX --gid 123456 --chapter 2 \
       --datawin "RUTA/DELTARUNE/chapter2_windows/data.win" --publish
```

El builder **no** guarda credenciales de Google (baja el Sheet como CSV público).
Alternativa sin conectar: `--input archivo.xlsx`. Para hospedar el parche en un
Release en vez del repo: `builder.py data ... --release vX.Y.Z` y luego
`gh release upload vX.Y.Z dist/chapter2/data/chapter2.patch`.

## Columnas del Sheet

`id` · `en` (original) · `cl` (traducción; vacío = cae al inglés)

- **Cap. 1**: `id` es la clave del `lang_en.json`.
- **Cap. 2+**: `id` es el **índice del string** en el pool del `data.win`
  (lo pone `extract`). No lo cambies: el `import` reinyecta por ese índice.

**Códigos de control** que deben quedar idénticos entre `en` y `cl` (el builder
avisa si se rompen): `^6` (pausa), `\M0` (cara), `\cY` (color), `&` y `#` (salto
de línea), `%` (fin de texto).

> Seguridad Cap.2+: `import_strings.csx` **nunca** reescribe strings usados como
> nombres internos (objetos, sprites, scripts, rooms, variables…), aunque queden
> traducidos por error en el Sheet — así no rompe el juego.

## Empaquetar el patcher para Windows (.exe)

Lo hace el GitHub Action `build-windows.yml` al empujar un tag `vX.Y.Z`.
Manual:
```bash
pip install pyinstaller detools
cd scripts
pyinstaller --onefile --windowed --name patcher-deltarune-cl patcher.py
```

## Requisitos

- Python 3.9+
- `pip install -r requirements.txt` (`detools` para el parche binario; `openpyxl`
  para `.xlsx`).
- **UndertaleModCli** (solo el mantenedor, para `extract`/`data`) —
  [UndertaleModTool releases](https://github.com/UnderminersTeam/UndertaleModTool/releases),
  asset `UTMT_CLI_*`.
