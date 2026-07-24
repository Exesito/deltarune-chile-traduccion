#!/usr/bin/env python3
"""
builder.py  --  Programa 1. Lo corre SOLO el mantenedor, en su maquina.

Se conecta al Google Sheet (link publico solo-lectura), lo transforma y deja los
artefactos listos en el repositorio:

    dist/chapter1/
        texts/lang_cl.json          <- lo que baja el parchador
        texts/lang_cl.json.sha256   <- hash de integridad
        manifest.json               <- indice de assets del capitulo

Las credenciales / permisos del Sheet NUNCA salen de tu maquina: al repo solo
sube el resultado. El programa 2 (patcher) jamas ve el Sheet.

Uso (conectando al Sheet):
    python builder.py --sheet "https://docs.google.com/spreadsheets/d/XXXX/edit"
    python builder.py --sheet XXXX --gid 0 --chapter 1 --publish

Uso (con archivo descargado a mano, sin conectar):
    python builder.py --input ~/Descargas/traduccion.xlsx
"""

import argparse
import sys
from pathlib import Path

import dr_core as core


def get_table(args):
    if args.sheet:
        print(f"[1/5] Conectando al Sheet (CSV, gid={args.gid}) ...")
        table = core.fetch_sheet_table(args.sheet, gid=args.gid)
    elif args.input:
        print(f"[1/5] Leyendo archivo local {args.input} ...")
        table = core.load_translation(Path(args.input))
    else:
        sys.exit("Debes pasar --sheet <url|id> o --input <archivo>.")
    print(f"      {len(table)} filas.")
    return table


def main():
    ap = argparse.ArgumentParser(description="Genera artefactos de traduccion para el repo.")
    src = ap.add_argument_group("fuente")
    src.add_argument("--sheet", help="URL o ID del Google Sheet (link publico solo-lectura)")
    src.add_argument("--gid", default="0", help="gid de la pestana del Sheet (default 0)")
    src.add_argument("--input", help="Alternativa: archivo descargado a mano (.xlsx/.csv/.json)")

    ap.add_argument("--chapter", type=int, default=1)
    ap.add_argument("--version", default="", help="Etiqueta de version (default: fecha de hoy)")
    ap.add_argument("--out-dir", default="../dist", help="Raiz de dist (default: ../dist)")
    ap.add_argument("--reference", default="../original_lang/lang_en.json")
    ap.add_argument("--strict", action="store_true",
                    help="Falla si hay filas con codigos de control rotos")
    ap.add_argument("--publish", action="store_true", help="git add/commit/push de dist/")
    args = ap.parse_args()

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
    payload = core.dumps_lang(lang)            # serializacion canonica (hash estable)
    digest = core.sha256_bytes(payload)
    lang_path = texts_dir / "lang_cl.json"
    lang_path.write_bytes(payload)
    (texts_dir / "lang_cl.json.sha256").write_text(
        digest + "  lang_cl.json\n", encoding="utf-8"
    )

    manifest = core.build_manifest(
        chapter=args.chapter,
        version=args.version,
        assets=[{
            "type": "text",
            "src": "texts/lang_cl.json",
            "sha256": digest,
            "target": "lang/lang_en.json",
            "bytes": len(payload),
        }],
    )
    import json
    (ch_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"[5/5] Listo:")
    print(f"      {lang_path}  ({len(lang)} entradas)")
    print(f"      sha256={digest}")
    print(f"      {ch_dir / 'manifest.json'}")

    if args.publish:
        _publish(ch_dir, digest)
    else:
        print("\nPara publicar:")
        print(f"  git add {ch_dir} && git commit -m 'traduccion cap{args.chapter}' && git push")


def _publish(ch_dir, digest):
    import subprocess
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


if __name__ == "__main__":
    main()
