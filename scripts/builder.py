#!/usr/bin/env python3
"""
builder.py  --  Programa 1. Lo corre SOLO el mantenedor, en su maquina.

Toma la traduccion del Google Sheet (link publico solo-lectura) y deja los
artefactos listos en el repositorio para que el patcher los aplique.

Subcomandos:
  text     Cap.1 (texto externo lang_en.json):  Sheet -> dist/chapterN/texts/lang_cl.json + manifest
  extract  Cap.2+ (texto dentro de data.win):   data.win --[UTMT]--> semilla CSV/xlsx para el Sheet
  data     Cap.2+:  Sheet --[UTMT: reinyecta]--> data.win traducido -> parche binario + manifest

Ejemplos:
  # Cap.1 (como siempre)
  python builder.py text --sheet "https://docs.google.com/spreadsheets/d/XXXX/edit" --publish

  # Cap.2: sacar los strings del juego para sembrar el Sheet
  python builder.py extract --datawin ~/.../DELTARUNE/chapter2_windows/data.win --chapter 2

  # Cap.2: construir el parche desde el Sheet (pestaña gid=123456)
  python builder.py data --sheet XXXX --gid 123456 --chapter 2 \
                    --datawin ~/.../DELTARUNE/chapter2_windows/data.win --publish

Requiere UndertaleModCli para extract/data (se busca en --utmt, $UTMT_CLI, PATH,
o ~/tools/utmt-cli/extracted/UndertaleModCli).
Las credenciales del Sheet NUNCA salen de tu maquina; al repo solo sube el output.
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from shutil import which

import dr_core as core

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

# Sheet por defecto (no se hardcodea el link en el repo): exporta DR_SHEET=<url|id>
# en tu shell y podras omitir --sheet.  Ej: export DR_SHEET="https://docs.google.com/..."
DEFAULT_SHEET = os.environ.get("DR_SHEET", "")
EXPORT_CSX = SCRIPT_DIR / "utmt" / "export_strings.csx"
IMPORT_CSX = SCRIPT_DIR / "utmt" / "import_strings.csx"
UTMT_GUESS = Path.home() / "tools" / "utmt-cli" / "extracted" / "UndertaleModCli"


# --------------------------------------------------------------------------- #
# UndertaleModCli (runner headless)
# --------------------------------------------------------------------------- #
def find_utmt_cli(explicit=None):
    for cand in (explicit, os.environ.get("UTMT_CLI")):
        if cand and Path(cand).exists():
            return str(Path(cand))
    on_path = which("UndertaleModCli")
    if on_path:
        return on_path
    if UTMT_GUESS.exists():
        return str(UTMT_GUESS)
    sys.exit(
        "No encontre UndertaleModCli. Pasa la ruta con --utmt, define UTMT_CLI=..., "
        "o instalalo en ~/tools/utmt-cli/extracted/UndertaleModCli"
    )


def run_utmt(cli, datafile, scripts, output=None, env=None):
    cmd = [cli, "load", str(datafile), "--scripts", *[str(s) for s in scripts]]
    if output:
        cmd += ["--output", str(output)]
    full_env = dict(os.environ)
    full_env.update(env or {})
    try:
        subprocess.run(cmd, env=full_env, check=True)
    except subprocess.CalledProcessError as e:
        sys.exit(f"UndertaleModCli fallo (codigo {e.returncode}). Revisa el data.win/scripts.")


# --------------------------------------------------------------------------- #
# Fuente de traduccion (Sheet o archivo)
# --------------------------------------------------------------------------- #
def get_table(args):
    sheet = args.sheet or (DEFAULT_SHEET if not args.input else "")
    if sheet:
        args.sheet = sheet
        name = args.sheet_name
        gid = args.gid
        # Por defecto (sin --gid ni --sheet-name): pestana segun el subcomando.
        if not name and gid is None:
            dt = getattr(args, "default_tab", "")
            name = dt.format(chapter=getattr(args, "chapter", "")) if dt else None
        selector = f"pestana '{name}'" if name else f"gid={gid}"
        print(f"  Conectando al Sheet ({selector}) ...")
        table = core.fetch_sheet_table(args.sheet, gid=gid, sheet_name=name)
    elif args.input:
        print(f"  Leyendo archivo local {args.input} ...")
        table = core.load_translation(Path(args.input))
    else:
        sys.exit("Debes pasar --sheet <url|id> o --input <archivo>.")
    print(f"  {len(table)} filas.")
    return table


def write_manifest(ch_dir, manifest):
    (ch_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# --------------------------------------------------------------------------- #
# Subcomando: text  (Cap.1, texto externo lang_en.json)
# --------------------------------------------------------------------------- #
def cmd_text(args):
    table = get_table(args)

    print("[2/5] Validando codigos de control ...")
    issues = core.validate_codes(table)
    for line in core.format_validation(issues):
        print("     ", line)
    if issues and args.strict:
        sys.exit(f"Abortado por --strict: {len(issues)} fila(s) con codigos rotos.")

    print("[3/5] Construyendo lang_cl.json ...")
    lang = core.build_lang(table)
    ref = Path(args.reference)
    ref_keys = core.load_reference_keys(ref) if ref.exists() else None
    for w in core.validate_lang_schema(lang, reference_keys=ref_keys):
        print("      aviso:", w)

    ch_dir = Path(args.out_dir) / f"chapter{args.chapter}"
    texts_dir = ch_dir / "texts"
    texts_dir.mkdir(parents=True, exist_ok=True)

    print("[4/5] Escribiendo artefactos ...")
    payload = core.dumps_lang(lang)
    digest = core.sha256_bytes(payload)
    lang_path = texts_dir / "lang_cl.json"
    lang_path.write_bytes(payload)
    (texts_dir / "lang_cl.json.sha256").write_text(
        digest + "  lang_cl.json\n", encoding="utf-8"
    )
    write_manifest(ch_dir, core.build_manifest(
        chapter=args.chapter, version=args.version,
        assets=[{
            "type": "text", "src": "texts/lang_cl.json", "sha256": digest,
            "target": "lang/lang_en.json", "bytes": len(payload),
        }],
    ))
    print(f"[5/5] Listo:  {lang_path} ({len(lang)} entradas)  sha256={digest[:12]}...")
    _maybe_publish(args, ch_dir, digest)


# --------------------------------------------------------------------------- #
# Subcomando: extract  (data.win -> semilla CSV/xlsx para el Sheet)
# --------------------------------------------------------------------------- #
def cmd_extract(args):
    cli = find_utmt_cli(args.utmt)
    datawin = Path(args.datawin)
    if not datawin.is_file():
        sys.exit(f"No existe el data.win: {datawin}")

    print(f"[1/3] Exportando strings de {datawin.name} con UTMT ...")
    with tempfile.TemporaryDirectory() as td:
        out_json = Path(td) / "strings_en.json"
        run_utmt(cli, datawin, [EXPORT_CSX], env={"DR_OUT": str(out_json)})
        data = json.loads(out_json.read_text(encoding="utf-8"))

    strings = data.get("strings", {})
    sha = core.sha256_bytes(datawin.read_bytes())
    print(f"      pool total={data.get('count')}  candidatos a dialogo={len(strings)}")
    print(f"      data.win sha256={sha}")

    rows = sorted(((int(k), v) for k, v in strings.items()), key=lambda x: x[0])
    out = Path(args.out) if args.out else (REPO_ROOT / "sheets" / f"chapter{args.chapter}_seed.csv")
    out.parent.mkdir(parents=True, exist_ok=True)

    print(f"[2/3] Escribiendo semilla ({out.suffix or '.csv'}) ...")
    if out.suffix.lower() in (".xlsx", ".xlsm"):
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(["id", "en", "cl"])
        for idx, en in rows:
            ws.append([idx, en, ""])
        wb.save(out)
    else:
        with open(out, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id", "en", "cl"])
            for idx, en in rows:
                w.writerow([idx, en, ""])

    print(f"[3/3] Semilla lista -> {out}  ({len(rows)} filas)")
    print("      Subela como pestana nueva del Google Sheet (columnas id, en, cl)")
    print("      y anota este sha256 del data.win para no mezclar versiones:")
    print(f"        {sha}")


# --------------------------------------------------------------------------- #
# Subcomando: data  (Cap.2+, Sheet -> data.win parchado -> parche binario)
# --------------------------------------------------------------------------- #
def cmd_data(args):
    cli = find_utmt_cli(args.utmt)
    datawin = Path(args.datawin)
    if not datawin.is_file():
        sys.exit(f"No existe el data.win: {datawin}")

    print("[1/6] Leyendo traduccion ...")
    table = get_table(args)

    print("[2/6] Validando codigos de control ...")
    issues = core.validate_codes(table)
    for line in core.format_validation(issues):
        print("     ", line)
    if issues and args.strict:
        sys.exit(f"Abortado por --strict: {len(issues)} fila(s) con codigos rotos.")

    print("[3/6] Recolectando strings traducidos (id = indice del pool) ...")
    strings = {}
    skipped_nonnum = 0
    for key, val in table.items():
        cl = (val.get("cl") or "").strip()
        if not cl:
            continue
        k = str(key).strip()
        if not (k.lstrip("-").isdigit()):
            skipped_nonnum += 1
            continue
        strings[str(int(k))] = cl
    if skipped_nonnum:
        print(f"      aviso: {skipped_nonnum} fila(s) traducidas con id NO numerico (ignoradas).")
    if not strings:
        sys.exit("No hay filas traducidas con id numerico. Nada que construir.")
    print(f"      {len(strings)} strings traducidos.")

    ch_dir = Path(args.out_dir) / f"chapter{args.chapter}"
    data_dir = ch_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        cl_json = Path(td) / "strings_cl.json"
        cl_json.write_text(json.dumps({"strings": strings}, ensure_ascii=False), encoding="utf-8")
        cl_win = Path(td) / "data_cl.win"
        print("[4/6] Reinyectando en data.win con UTMT (headless) ...")
        run_utmt(cli, datawin, [IMPORT_CSX], output=cl_win, env={"DR_IN": str(cl_json)})
        old = datawin.read_bytes()
        new = cl_win.read_bytes()

    print("[5/6] Generando parche binario (detools) ...")
    patch = core.create_binary_patch(old, new)
    base_sha = core.sha256_bytes(old)
    result_sha = core.sha256_bytes(new)
    patch_sha = core.sha256_bytes(patch)
    patch_name = f"chapter{args.chapter}.patch"
    (data_dir / patch_name).write_bytes(patch)

    target = args.target or f"chapter{args.chapter}_windows/data.win"
    if args.release:
        src = (f"https://github.com/{args.owner}/{args.repo}"
               f"/releases/download/{args.release}/{patch_name}")
    else:
        src = f"data/{patch_name}"

    write_manifest(ch_dir, core.build_manifest(
        chapter=args.chapter, version=args.version,
        assets=[{
            "type": "data", "src": src, "sha256": patch_sha,
            "target": target, "base_sha256": base_sha,
            "result_sha256": result_sha, "bytes": len(patch),
        }],
    ))

    print("[6/6] Listo:")
    print(f"      parche:   {data_dir / patch_name}  ({len(patch):,} bytes)")
    print(f"      target:   {target}")
    print(f"      base_sha: {base_sha}   (version de data.win que exige el parche)")
    print(f"      manifest: {ch_dir / 'manifest.json'}")
    if args.release:
        print(f"\n      Sube el parche al release '{args.release}':")
        print(f"        gh release upload {args.release} '{data_dir / patch_name}'")
    _maybe_publish(args, ch_dir, patch_sha, extra=None if args.release else data_dir / patch_name)


# --------------------------------------------------------------------------- #
# Subcomando: latest  (dist/latest.json -> version del patcher para auto-aviso)
# --------------------------------------------------------------------------- #
def cmd_latest(args):
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    url = args.patcher_url or (
        f"https://github.com/{args.owner}/{args.repo}/releases/latest")
    info = {"patcher_version": args.patcher_version, "patcher_url": url}
    (out_dir / "latest.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Escrito {out_dir / 'latest.json'}  ->  patcher v{args.patcher_version}")
    if args.publish:
        _maybe_publish(args, out_dir / "latest.json", args.patcher_version)
    else:
        print(f"\nPara publicar:\n  git add {out_dir/'latest.json'} && "
              f"git commit -m 'patcher v{args.patcher_version}' && git push")


# --------------------------------------------------------------------------- #
# Publicacion (git)
# --------------------------------------------------------------------------- #
def _maybe_publish(args, ch_dir, digest, extra=None):
    if not args.publish:
        print("\nPara publicar:")
        print(f"  git add {ch_dir} && git commit -m 'traduccion {ch_dir.name}' && git push")
        return
    print("\nPublicando en el repo (git) ...")
    try:
        subprocess.run(["git", "add", str(ch_dir)], check=True)
        subprocess.run(
            ["git", "commit", "-m", f"traduccion: actualizar {ch_dir.name} ({digest[:10]})"],
            check=True,
        )
        subprocess.run(["git", "push"], check=True)
        print("Publicado.")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        sys.exit(f"Fallo git publish: {e}\nHazlo a mano con git add/commit/push.")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _add_source_args(p):
    g = p.add_argument_group("fuente")
    g.add_argument("--sheet", help="URL o ID del Google Sheet (link publico solo-lectura)")
    g.add_argument("--sheet-name", help="Nombre de la pestana (ej. 'Cap2'). Default: 'Cap<chapter>'")
    g.add_argument("--gid", default=None, help="gid de la pestana (alternativa a --sheet-name)")
    g.add_argument("--input", help="Alternativa: archivo descargado a mano (.xlsx/.csv/.json)")


def build_parser():
    ap = argparse.ArgumentParser(description="Genera artefactos de traduccion para el repo.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # text
    t = sub.add_parser("text", help="Cap.1: Sheet -> lang_cl.json + manifest")
    _add_source_args(t)
    t.add_argument("--chapter", type=int, default=1)
    t.add_argument("--version", default="")
    t.add_argument("--out-dir", default=str(REPO_ROOT / "dist"))
    t.add_argument("--reference", default=str(REPO_ROOT / "original_lang" / "lang_en.json"))
    t.add_argument("--strict", action="store_true")
    t.add_argument("--publish", action="store_true", help="git add/commit/push de dist/")
    t.set_defaults(func=cmd_text, default_tab="Translations")

    # extract
    e = sub.add_parser("extract", help="Cap.2+: data.win -> semilla CSV/xlsx para el Sheet")
    e.add_argument("--datawin", required=True, help="Ruta al data.win del capitulo")
    e.add_argument("--chapter", type=int, required=True)
    e.add_argument("--out", help="Archivo de salida (.csv o .xlsx). Default: sheets/chapterN_seed.csv")
    e.add_argument("--utmt", help="Ruta a UndertaleModCli")
    e.set_defaults(func=cmd_extract)

    # data
    d = sub.add_parser("data", help="Cap.2+: Sheet -> data.win parchado -> parche binario + manifest")
    _add_source_args(d)
    d.add_argument("--datawin", required=True, help="data.win ORIGINAL (ingles) del capitulo")
    d.add_argument("--chapter", type=int, required=True)
    d.add_argument("--version", default="")
    d.add_argument("--out-dir", default=str(REPO_ROOT / "dist"))
    d.add_argument("--target", help="Ruta del data.win dentro del juego (default chapterN_windows/data.win)")
    d.add_argument("--utmt", help="Ruta a UndertaleModCli")
    d.add_argument("--strict", action="store_true")
    d.add_argument("--release", help="Tag del GitHub Release donde hospedar el parche (en vez del repo)")
    d.add_argument("--owner", default="Exesito", help="owner del repo (para --release)")
    d.add_argument("--repo", default="deltarune-chile-traduccion", help="nombre del repo (para --release)")
    d.add_argument("--publish", action="store_true", help="git add/commit/push de dist/")
    d.set_defaults(func=cmd_data, default_tab="chapter{chapter}_seed")

    # latest
    la = sub.add_parser("latest", help="Actualiza dist/latest.json (version del patcher)")
    la.add_argument("--patcher-version", required=True, help="ej. 1.0.1")
    la.add_argument("--patcher-url", help="URL de descarga (default: releases/latest del repo)")
    la.add_argument("--out-dir", default=str(REPO_ROOT / "dist"))
    la.add_argument("--owner", default="Exesito")
    la.add_argument("--repo", default="deltarune-chile-traduccion")
    la.add_argument("--publish", action="store_true")
    la.set_defaults(func=cmd_latest)
    return ap


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
