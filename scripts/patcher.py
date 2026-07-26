#!/usr/bin/env python3
"""
patcher.py  --  Programa 2. Se reparte a cualquiera.

Baja los artefactos de traduccion PUBLICADOS en el repo de GitHub (via
manifest.json), verifica su integridad (SHA-256, esquema, host permitido) y
parcha el juego. Por defecto parcha TODOS los capitulos publicados de una;
los que aun no estan disponibles se omiten y uno que falle no detiene al resto.

Nunca ve el Google Sheet ni credenciales: solo consume dist/chapterN/ del repo.

GUI (por defecto):
    python patcher.py

CLI:
    python patcher.py patch --game "C:\\...\\DELTARUNE"              # todos
    python patcher.py patch --chapter 1 --game "C:\\...\\DELTARUNE"  # uno solo
    python patcher.py patch --file lang_cl.json --game "C:\\...\\DELTARUNE"
    python patcher.py restore --game "C:\\...\\DELTARUNE"
    python patcher.py check --game "C:\\...\\DELTARUNE"
"""

import argparse
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError

import dr_core as core

# --- Configuracion del repo (el mantenedor edita estos valores) ------------ #
REPO_OWNER = "Exesito"
REPO_NAME = "deltarune-chile-traduccion"
REPO_BRANCH = "main"

# Version de ESTE patcher. El mantenedor la sube al publicar un .exe nuevo y la
# refleja en dist/latest.json para que las copias viejas avisen que hay update.
PATCHER_VERSION = "1.1.0"

# Rutas tipicas de instalacion (para auto-detectar el juego) ---------------- #
WIN_GUESSES = [
    r"C:\Program Files (x86)\Steam\steamapps\common\DELTARUNE",
    r"C:\Program Files\Steam\steamapps\common\DELTARUNE",
    r"C:\Program Files (x86)\Steam\steamapps\common\DELTARUNEdemo",
]
LINUX_GUESSES = [
    "~/.steam/steam/steamapps/common/DELTARUNE",
    "~/.local/share/Steam/steamapps/common/DELTARUNE",
]


def autodetect_game():
    for g in WIN_GUESSES + [os.path.expanduser(p) for p in LINUX_GUESSES]:
        p = Path(g)
        # Cap.1 usa lang_en.json; Cap.2+ vive en data.win
        if p.is_dir() and (list(p.rglob("data.win")) or list(p.rglob("lang_en.json"))):
            return str(p)
    return ""


# Capitulos que el patcher intenta cubrir. Los que aun no esten publicados en el
# repo se omiten solos (manifest 404); el mantenedor no toca nada aca al publicar.
AVAILABLE_CHAPTERS = [1, 2, 3, 4, 5]


def repo_base_url(owner, repo, branch, chapter):
    return core.github_raw_base(owner, repo, branch, f"dist/chapter{chapter}")


def dist_base_url(owner, repo, branch):
    return core.github_raw_base(owner, repo, branch, "dist")


# --------------------------------------------------------------------------- #
# Chequeo de actualizaciones (patcher + traduccion de cada capitulo publicado)
# --------------------------------------------------------------------------- #
def check_updates_all(owner, repo, branch, game, chapters=None):
    """
    Revisa (tolerante a fallos de red) si hay patcher nuevo y, para cada capitulo
    publicado, si hay traduccion nueva. Los capitulos no publicados (404) se
    ignoran en silencio. Devuelve (patcher, [trans...], errores).
    """
    chapters = chapters or AVAILABLE_CHAPTERS
    patcher = None
    trans_list = []
    errors = []
    try:
        patcher = core.check_patcher_update(
            dist_base_url(owner, repo, branch), PATCHER_VERSION)
    except Exception as e:
        errors.append(f"patcher: {e}")
    if game and Path(game).exists():
        for ch in chapters:
            try:
                trans_list.append(core.check_translation_update(
                    repo_base_url(owner, repo, branch, ch), game, ch))
            except HTTPError as e:
                if e.code != 404:  # 404 = capitulo aun no publicado; se ignora
                    errors.append(f"cap {ch}: {e}")
            except Exception as e:
                errors.append(f"cap {ch}: {e}")
    return patcher, trans_list, errors


# --------------------------------------------------------------------------- #
# Operaciones (compartidas por CLI y GUI)
# --------------------------------------------------------------------------- #
def patch_from_repo(owner, repo, branch, chapter, game, log=print):
    """Parcha UN capitulo. Propaga excepciones (lo usa el modo --chapter)."""
    base = repo_base_url(owner, repo, branch, chapter)
    log(f"* Bajando manifest de {owner}/{repo}@{branch} (cap {chapter}) ...")
    manifest = core.fetch_manifest(base)
    log(f"* Version: {manifest.get('version')}  |  assets: {len(manifest.get('assets', []))}")
    results = core.apply_manifest(base, manifest, Path(game), log=log)
    core.write_state_entry(game, chapter, core.manifest_signature(manifest),
                           manifest.get("version"))
    log("* Listo. Aplicados: " + ", ".join(f"{t}" for t, _ in results))
    return results


def patch_all_chapters(owner, repo, branch, game, chapters=None, log=print):
    """
    Parcha TODOS los capitulos publicados de una. Salta los que aun no estan
    disponibles en el repo (manifest 404) y aisla los fallos: si un capitulo no
    se puede aplicar (p.ej. tu data.win es de otra version), los demas igual se
    parchan. Devuelve dict {chapter: estado} con estados:
    ok | no_publicado | seguridad | error.
    """
    chapters = chapters or AVAILABLE_CHAPTERS
    summary = {}
    for ch in chapters:
        base = repo_base_url(owner, repo, branch, ch)
        try:
            manifest = core.fetch_manifest(base)
        except HTTPError as e:
            summary[ch] = "no_publicado" if e.code == 404 else "error"
            log(f"* Cap. {ch}: " + ("aun no disponible, se omite."
                                    if e.code == 404 else f"error de red ({e.code})."))
            continue
        except (URLError, core.SecurityError, OSError) as e:
            summary[ch] = "error"
            log(f"* Cap. {ch}: no se pudo bajar el manifest ({e}).")
            continue
        try:
            log(f"* Cap. {ch}: version {manifest.get('version')} — aplicando ...")
            core.apply_manifest(base, manifest, Path(game), log=log)
            core.write_state_entry(game, ch, core.manifest_signature(manifest),
                                   manifest.get("version"))
            summary[ch] = "ok"
            log(f"* Cap. {ch}: listo.")
        except core.SecurityError as e:
            summary[ch] = "seguridad"
            log(f"* Cap. {ch}: no aplicado — {e}")
        except Exception as e:
            summary[ch] = "error"
            log(f"* Cap. {ch}: error al aplicar — {e}")
    return summary


def patch_from_file(path, game, log=print):
    table = core.load_translation(Path(path))
    for line in core.format_validation(core.validate_codes(table)):
        log("* " + line)
    lang = core.build_lang(table)
    for w in core.validate_lang_schema(lang):
        log("* aviso: " + w)
    target, backup, backed = core.patch_game(Path(game), lang)
    if backed:
        log(f"* Respaldo creado: {backup}")
    log(f"* Juego parchado: {target}  ({len(lang)} entradas)")


def summarize(summary):
    """dict {chapter: estado}  ->  lineas legibles."""
    ok = [c for c, s in summary.items() if s == "ok"]
    skip = [c for c, s in summary.items() if s == "no_publicado"]
    bad = [(c, s) for c, s in summary.items() if s in ("error", "seguridad")]
    lines = []
    if ok:
        lines.append("Parchados: " + ", ".join(f"Cap.{c}" for c in ok))
    if skip:
        lines.append("Aun no disponibles: " + ", ".join(f"Cap.{c}" for c in skip))
    if bad:
        lines.append("Con problemas: " + ", ".join(f"Cap.{c} ({s})" for c, s in bad))
    return lines or ["Nada que hacer."]


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _parse_repo(spec):
    """usuario/repo@branch  ->  (owner, repo, branch)."""
    branch = REPO_BRANCH
    if "@" in spec:
        spec, branch = spec.split("@", 1)
    owner, repo = spec.split("/", 1)
    return owner, repo, branch


def cli_patch(args):
    if args.file:
        patch_from_file(args.file, args.game)
        return
    owner, repo, branch = _parse_repo(args.repo) if args.repo else (
        REPO_OWNER, REPO_NAME, REPO_BRANCH)
    if args.chapter:  # un capitulo puntual
        try:
            patch_from_repo(owner, repo, branch, args.chapter, args.game)
        except HTTPError as e:
            sys.exit(f"Cap. {args.chapter}: aun no disponible en el repo."
                     if e.code == 404 else f"Cap. {args.chapter}: error de red ({e}).")
    else:  # por defecto: todos los publicados
        summary = patch_all_chapters(owner, repo, branch, args.game)
        print("\n" + "\n".join(summarize(summary)))


def cli_restore(args):
    restored = core.restore_all_backups(Path(args.game))
    for t in restored:
        print(f"Restaurado el original: {t}")


def cli_check(args):
    owner, repo, branch = _parse_repo(args.repo) if args.repo else (
        REPO_OWNER, REPO_NAME, REPO_BRANCH)
    patcher, trans_list, errors = check_updates_all(
        owner, repo, branch, args.game,
        chapters=[args.chapter] if args.chapter else None)

    print(f"Patcher instalado: v{PATCHER_VERSION}")
    if patcher:
        if patcher["update_available"]:
            print(f"  ¡Hay patcher nuevo! v{patcher['latest']}  ->  {patcher.get('url') or '(sin url)'}")
        else:
            print(f"  Patcher al dia (ultimo publicado: v{patcher.get('latest')}).")

    print("\nTraduccion por capitulo:")
    if not trans_list:
        print("  (no pude revisar; ¿indicaste --game y hay red?)")
    for t in trans_list:
        if not t["applied"]:
            print(f"  Cap.{t['chapter']}: no aplicada aun (publicada: {t['repo_version']}).")
        elif t["update_available"]:
            print(f"  Cap.{t['chapter']}: ¡hay nueva!  aplicada {t['applied_version']}  ->  "
                  f"publicada {t['repo_version']}")
        else:
            print(f"  Cap.{t['chapter']}: al dia (version {t['repo_version']}).")

    for e in errors:
        print(f"  aviso: {e}")


def build_parser():
    p = argparse.ArgumentParser(description="Parchador de traduccion Deltarune ES-CL")
    sub = p.add_subparsers(dest="cmd")

    pa = sub.add_parser("patch", help="Baja del repo (o usa archivo) y parcha")
    pa.add_argument("--repo", help="usuario/repo[@branch] en GitHub")
    pa.add_argument("--chapter", type=int, default=None,
                    help="Parchar solo ese capitulo. Por defecto: todos los publicados.")
    pa.add_argument("--file", help="Alternativa: parchar desde archivo local (.json/.xlsx/.csv)")
    pa.add_argument("--game", required=True, help="Carpeta del juego o ruta a lang_en.json")
    pa.set_defaults(func=cli_patch)

    r = sub.add_parser("restore", help="Restaura el/los original(es) desde los backups")
    r.add_argument("--game", required=True)
    r.set_defaults(func=cli_restore)

    c = sub.add_parser("check", help="Revisa si hay traduccion o patcher nuevos")
    c.add_argument("--repo", help="usuario/repo[@branch] en GitHub")
    c.add_argument("--chapter", type=int, default=None,
                   help="Revisar solo ese capitulo. Por defecto: todos.")
    c.add_argument("--game", help="Carpeta del juego (para saber que version tienes aplicada)")
    c.set_defaults(func=cli_check)
    return p


# --------------------------------------------------------------------------- #
# GUI estilo Deltarune (tkinter, stdlib)
# --------------------------------------------------------------------------- #
BG = "#000000"
FG = "#FFFFFF"
YELLOW = "#FFF23F"
HEART = "#FF3B3B"
MONO = ("Courier New", 11)
MONO_B = ("Courier New", 11, "bold")
TITLE_FONT = ("Courier New", 20, "bold")


def _dr_button(parent, text, cmd):
    import tkinter as tk
    b = tk.Button(
        parent, text="  " + text, command=cmd, anchor="w",
        bg=BG, fg=FG, activebackground=BG, activeforeground=YELLOW,
        font=MONO_B, bd=0, highlightthickness=2,
        highlightbackground="#555", highlightcolor=YELLOW,
        relief="flat", padx=6, pady=4, cursor="heart",
    )
    base = text

    def on(_=None):
        b.config(text="♥ " + base, fg=YELLOW, highlightbackground=YELLOW)

    def off(_=None):
        b.config(text="  " + base, fg=FG, highlightbackground="#555")

    for ev in ("<Enter>", "<FocusIn>"):
        b.bind(ev, on)
    for ev in ("<Leave>", "<FocusOut>"):
        b.bind(ev, off)
    return b


def launch_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox

    root = tk.Tk()
    root.title("DELTARUNE  -  Parche ES-CL")
    root.configure(bg=BG)
    root.geometry("560x430")
    root.minsize(520, 410)

    game_v = tk.StringVar(value=autodetect_game())
    status_v = tk.StringVar()

    def set_status(msg):
        status_v.set(msg)
        root.update_idletasks()

    # --- titulo ---
    tk.Label(root, text="♥  DELTARUNE", bg=BG, fg=YELLOW, font=TITLE_FONT).pack(pady=(22, 0))
    tk.Label(root, text="PARCHE  ·  ESPANOL CHILENO",
             bg=BG, fg=FG, font=MONO_B).pack(pady=(2, 4))
    tk.Label(root, text="parcha todos los capitulos de una",
             bg=BG, fg="#AAAAAA", font=MONO).pack(pady=(0, 12))

    # --- ubicar juego (caja tipo textbox) ---
    box = tk.Frame(root, bg=BG, highlightbackground=FG, highlightthickness=3)
    box.pack(fill="x", padx=22)
    tk.Label(box, text="Carpeta del juego:", bg=BG, fg=FG, font=MONO).grid(
        row=0, column=0, sticky="w", padx=8, pady=(8, 2))
    game_lbl = tk.Label(box, textvariable=game_v, bg=BG, fg=YELLOW, font=MONO,
                        anchor="w", wraplength=470, justify="left")
    game_lbl.grid(row=1, column=0, sticky="we", padx=8, pady=(0, 8))
    box.columnconfigure(0, weight=1)

    def locate():
        d = filedialog.askdirectory(title="Ubica la carpeta de Deltarune")
        if d:
            game_v.set(d)
            set_status("Juego seleccionado.")
            refresh_updates()

    _dr_button(box, "Ubicar juego...", locate).grid(row=0, column=1, rowspan=2, padx=8)

    # --- boton unico grande: parcha TODOS los capitulos ---
    def _do_patch():
        game = game_v.get()
        if not game or not Path(game).exists():
            locate()
            game = game_v.get()
            if not game:
                return
        big.config(state="disabled")
        set_status("Descargando y parchando todos los capitulos ...")
        try:
            summary = patch_all_chapters(REPO_OWNER, REPO_NAME, REPO_BRANCH,
                                         game, log=set_status)
            ok = [c for c, s in summary.items() if s == "ok"]
            bad = [c for c, s in summary.items() if s in ("error", "seguridad")]
            lines = summarize(summary)
            if ok:
                set_status("Listo. " + lines[0])
                cuerpo = "\n".join(lines) + "\n\nAbre Deltarune para jugar en espanol."
                (messagebox.showwarning if bad else messagebox.showinfo)(
                    "Listo ♥" if not bad else "Listo (con avisos)", cuerpo)
            else:
                set_status("No se parcho ningun capitulo.")
                messagebox.showwarning("Aviso", "\n".join(lines))
            refresh_updates()
        except core.SecurityError as e:
            set_status("Bloqueado por seguridad.")
            messagebox.showerror("Seguridad", str(e))
        except Exception as e:
            set_status("Error.")
            messagebox.showerror("Error", str(e))
        finally:
            big.config(state="normal")

    big = tk.Button(root, text="♥  PARCHAR TODO AL ESPANOL", command=_do_patch,
                    bg=BG, fg=YELLOW, activebackground=BG, activeforeground="#FFFFFF",
                    font=("Courier New", 16, "bold"), bd=0, highlightthickness=3,
                    highlightbackground=FG, highlightcolor=YELLOW, relief="flat",
                    padx=10, pady=14, cursor="heart")
    big.pack(fill="x", padx=22, pady=(18, 12))

    # --- estado ---
    tk.Label(root, textvariable=status_v, bg=BG, fg="#AAAAAA", font=MONO,
             wraplength=500).pack(pady=(0, 6))

    # --- aviso de actualizaciones ---
    import threading
    upd_v = tk.StringVar()
    tk.Label(root, textvariable=upd_v, bg=BG, fg=YELLOW, font=MONO,
             wraplength=500, justify="center").pack(pady=(0, 4))

    def _apply_update_ui(patcher, trans_list, errors):
        msgs = []
        if patcher and patcher["update_available"]:
            msgs.append(f"⬆ Patcher nuevo disponible: v{patcher['latest']}")
            if patcher.get("url"):
                root.title(f"DELTARUNE - Parche ES-CL  (hay v{patcher['latest']})")
        nuevas = [t for t in trans_list if t["update_available"]]
        aldia = [t for t in trans_list if t["applied"] and t["up_to_date"]]
        sinaplicar = [t for t in trans_list if not t["applied"]]
        if nuevas:
            msgs.append("⬆ Traduccion nueva: "
                        + ", ".join(f"Cap.{t['chapter']}" for t in nuevas))
        if aldia:
            msgs.append("✓ Al dia: " + ", ".join(f"Cap.{t['chapter']}" for t in aldia))
        if sinaplicar:
            msgs.append("· Sin parchar: "
                        + ", ".join(f"Cap.{t['chapter']}" for t in sinaplicar))
        upd_v.set("\n".join(msgs))

    def refresh_updates():
        upd_v.set("Revisando actualizaciones ...")

        def work():
            res = check_updates_all(REPO_OWNER, REPO_NAME, REPO_BRANCH, game_v.get())
            root.after(0, lambda: _apply_update_ui(*res))

        threading.Thread(target=work, daemon=True).start()

    def _do_restore():
        try:
            restored = core.restore_all_backups(Path(game_v.get()))
            set_status(f"Restaurado el original ({len(restored)} archivo/s).")
            messagebox.showinfo("Listo", f"Se restauro el original ({len(restored)} archivo/s).")
            refresh_updates()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    restore = tk.Label(root, text="restaurar original", bg=BG, fg="#777",
                       font=("Courier New", 10, "underline"), cursor="hand2")
    restore.pack(side="bottom", pady=10)
    restore.bind("<Button-1>", lambda _: _do_restore())

    if game_v.get():
        set_status("Juego detectado. Dale a PARCHAR TODO.")
    else:
        set_status("Ubica la carpeta del juego y dale a PARCHAR TODO.")
    root.after(400, refresh_updates)
    root.mainloop()


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "cmd", None):
        launch_gui()
        return
    args.func(args)


if __name__ == "__main__":
    main()
