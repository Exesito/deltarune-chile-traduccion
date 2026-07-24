# Deltarune — Traducción al Español Chileno 🇨🇱

Traducción de **Deltarune (Capítulo 1)** al español chileno.

El flujo tiene **dos programas**: uno que usa solo el mantenedor para generar la
traducción desde el Google Sheet, y otro que reparte a la comunidad para parchar
el juego. El Google Sheet y las credenciales **nunca** se exponen: al repo solo
llega el resultado.

```
Google Sheet ──[builder.py]──▶ dist/chapterN/ (repo GitHub) ──[patcher.py]──▶ tu juego
   (mantenedor, local)              (público)                    (cualquiera)
```

## Estructura del repo

```
scripts/
  dr_core.py     núcleo compartido (carga, validación, seguridad, parcheo)
  builder.py     PROGRAMA 1 — genera los artefactos desde el Sheet (solo mantenedor)
  patcher.py     PROGRAMA 2 — baja del repo y parcha el juego (se reparte)
dist/
  chapter1/
    manifest.json              índice de assets del capítulo + sha256
    texts/lang_cl.json         la traducción publicada
    texts/lang_cl.json.sha256  hash de integridad
    images/  fonts/  data/     (a futuro: sprites, fuentes, config del data.win)
original_lang/
  lang_en.json   texto original en inglés (referencia para validar claves)
```

Cada capítulo se describe con un `manifest.json`. Hoy solo está implementado el
tipo `text`; `image` / `font` / `data` se agregarán sin rehacer el flujo.

## Para USAR la traducción (jugadores)

### Opción A — GUI (recomendado)
1. Descarga `patcher.py` (o el `.exe` en *Releases*, si está disponible) y ábrelo.
2. Intenta **auto-detectar** el juego; si no lo halla, botón **Ubicar juego...**.
3. Un solo botón: **♥ PARCHAR AL ESPAÑOL**.
4. Para volver al inglés: link **restaurar original** (abajo).

### Opción B — línea de comandos
```bash
python scripts/patcher.py patch --repo Exesito/deltarune-chile-traduccion@main --game "RUTA/DELTARUNE"
python scripts/patcher.py restore --game "RUTA/DELTARUNE"
```

El parchador respalda tu `lang_en.json` original como `lang_en.json.orig.bak`
antes de tocar nada, verifica el **SHA-256** y el esquema del archivo descargado,
y solo baja desde `raw.githubusercontent.com` por HTTPS.

## Para GENERAR/actualizar la traducción (mantenedor)

Requiere que el Google Sheet esté compartido como **"cualquiera con el link: lector"**.

```bash
cd scripts
python builder.py --sheet "https://docs.google.com/spreadsheets/d/XXXX/edit" --chapter 1
# revisa los avisos de códigos de control, luego publica:
git add ../dist/chapter1 && git commit -m "traduccion cap1" && git push
#   ...o directo:  python builder.py --sheet XXXX --publish
```

El builder **no** guarda credenciales de Google: baja el Sheet como CSV público.
Alternativa sin conectar: `--input archivo.xlsx` (Sheet descargado a mano).

## Columnas del Sheet

`id` · `en` (original) · `cl` (traducción; si está vacío cae al inglés) · `comment`

**Códigos de control** que deben conservarse idénticos entre `en` y `cl`
(el builder avisa si se rompen): `^6` (pausa), `\M0` (cara), `\cY` (color),
`&` (salto de línea), `%` (fin de texto).

## Empaquetar el patcher para Windows (.exe)

```bash
pip install pyinstaller
cd scripts
pyinstaller --onefile --windowed --name patcher-deltarune-cl patcher.py
```
PyInstaller detecta e incluye `dr_core.py` automáticamente (es un import local).
tkinter viene con Python en Windows; no requiere nada extra.

## Requisitos

- Python 3.9+
- `openpyxl` (solo si lees `.xlsx`): `pip install openpyxl`
- El resto usa la librería estándar.
