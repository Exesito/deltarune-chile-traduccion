#!/usr/bin/env python3
"""
patcher.py  --  Programa 2. Se reparte a cualquiera.

Baja los artefactos de traduccion PUBLICADOS en el repo de GitHub (via
manifest.json), verifica su integridad (SHA-256, esquema, host permitido) y
parcha el juego (Deltarune Cap.1, solo texto por ahora).

Nunca ve el Google Sheet ni credenciales: solo consume dist/chapterN/ del repo.

GUI (por defecto):
    python patcher.py

CLI:
    python patcher.py patch --repo usuario/deltarune-cl@main --chapter 1 --game "C:\\...\\DELTARUNE"
    python patcher.py patch --file lang_cl.json --game "C:\\...\\DELTARUNE"
    python patcher.py restore --game "C:\\...\\DELTARUNE"
"""

import argparse
import os
import sys
from pathlib import Path

import dr_core as core

# --- Configuracion del repo (el mantenedor edita estos valores) ------------ #
REPO_OWNER = "Exesito"
REPO_NAME = "deltarune-chile-traduccion"
REPO_BRANCH = "main"
DEFAULT_CHAPTER = 1

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
        if p.is_dir() and list(p.rglob("lang_en.json")):
            return str(p)
    return ""


def repo_base_url(owner, repo, branch, chapter):
    return core.github_raw_base(owner, repo, branch, f"dist/chapter{chapter}")


# --------------------------------------------------------------------------- #
# Operaciones (compartidas por CLI y GUI)
# --------------------------------------------------------------------------- #
def patch_from_repo(owner, repo, branch, chapter, game, log=print):
    base = repo_base_url(owner, repo, branch, chapter)
    log(f"* Bajando manifest de {owner}/{repo}@{branch} (cap {chapter}) ...")
    manifest = core.fetch_manifest(base)
    log(f"* Version: {manifest.get('version')}  |  assets: {len(manifest.get('assets', []))}")
    results = core.apply_manifest(base, manifest, Path(game), log=log)
    log("* Listo. Aplicados: " + ", ".join(f"{t}" for t, _ in results))
    return results


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
    else:
        owner, repo, branch = _parse_repo(args.repo) if args.repo else (
            REPO_OWNER, REPO_NAME, REPO_BRANCH)
        patch_from_repo(owner, repo, branch, args.chapter, args.game)


def cli_restore(args):
    target = core.restore_game(Path(args.game))
    print(f"Restaurado el original: {target}")


def build_parser():
    p = argparse.ArgumentParser(description="Parchador de traduccion Deltarune Cap.1")
    sub = p.add_subparsers(dest="cmd")

    pa = sub.add_parser("patch", help="Baja del repo (o usa archivo) y parcha")
    pa.add_argument("--repo", help="usuario/repo[@branch] en GitHub")
    pa.add_argument("--chapter", type=int, default=DEFAULT_CHAPTER)
    pa.add_argument("--file", help="Alternativa: parchar desde archivo local (.json/.xlsx/.csv)")
    pa.add_argument("--game", required=True, help="Carpeta del juego o ruta a lang_en.json")
    pa.set_defaults(func=cli_patch)

    r = sub.add_parser("restore", help="Restaura el lang_en.json original")
    r.add_argument("--game", required=True)
    r.set_defaults(func=cli_restore)
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
    root.geometry("560x420")
    root.minsize(520, 400)

    game_v = tk.StringVar(value=autodetect_game())
    status_v = tk.StringVar()

    def set_status(msg):
        status_v.set(msg)
        root.update_idletasks()

    # --- titulo ---
    tk.Label(root, text="♥  DELTARUNE", bg=BG, fg=YELLOW, font=TITLE_FONT).pack(pady=(22, 0))
    tk.Label(root, text="PARCHE  ·  ESPANOL CHILENO  ·  CAP. 1",
             bg=BG, fg=FG, font=MONO_B).pack(pady=(2, 18))

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

    _dr_button(box, "Ubicar juego...", locate).grid(row=0, column=1, rowspan=2, padx=8)

    # --- boton unico grande ---
    def _do_patch():
        game = game_v.get()
        if not game or not Path(game).exists():
            locate()
            game = game_v.get()
            if not game:
                return
        big.config(state="disabled")
        set_status("Descargando y parchando...")
        try:
            patch_from_repo(REPO_OWNER, REPO_NAME, REPO_BRANCH, DEFAULT_CHAPTER,
                            game, log=set_status)
            set_status("Listo. Abre Deltarune para jugar en espanol.")
            messagebox.showinfo("Listo ♥", "Juego parchado.\nAbre Deltarune para probar.")
        except core.SecurityError as e:
            set_status("Bloqueado por seguridad.")
            messagebox.showerror("Seguridad", str(e))
        except Exception as e:
            set_status("Error.")
            messagebox.showerror("Error", str(e))
        finally:
            big.config(state="normal")

    big = tk.Button(root, text="♥  PARCHAR AL ESPANOL", command=_do_patch,
                    bg=BG, fg=YELLOW, activebackground=BG, activeforeground="#FFFFFF",
                    font=("Courier New", 16, "bold"), bd=0, highlightthickness=3,
                    highlightbackground=FG, highlightcolor=YELLOW, relief="flat",
                    padx=10, pady=14, cursor="heart")
    big.pack(fill="x", padx=22, pady=20)

    # --- estado + restaurar (chico) ---
    tk.Label(root, textvariable=status_v, bg=BG, fg="#AAAAAA", font=MONO,
             wraplength=500).pack(pady=(0, 6))

    def _do_restore():
        try:
            core.restore_game(Path(game_v.get()))
            set_status("Restaurado el ingles original.")
            messagebox.showinfo("Listo", "Se restauro el original.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    restore = tk.Label(root, text="restaurar original", bg=BG, fg="#777",
                       font=("Courier New", 10, "underline"), cursor="hand2")
    restore.pack(side="bottom", pady=10)
    restore.bind("<Button-1>", lambda _: _do_restore())

    if game_v.get():
        set_status("Juego detectado. Dale a PARCHAR.")
    else:
        set_status("Ubica la carpeta del juego y dale a PARCHAR.")
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
