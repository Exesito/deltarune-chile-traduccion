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
    from tkinter import filedialog, messagebox, scrolledtext

    root = tk.Tk()
    root.title("DELTARUNE  -  Parche ES-CL")
    root.configure(bg=BG)
    root.geometry("780x600")

    src_mode = tk.StringVar(value="repo")
    owner_v = tk.StringVar(value=REPO_OWNER)
    repo_v = tk.StringVar(value=REPO_NAME)
    branch_v = tk.StringVar(value=REPO_BRANCH)
    chapter_v = tk.StringVar(value=str(DEFAULT_CHAPTER))
    file_v = tk.StringVar()
    game_v = tk.StringVar(value=autodetect_game())

    def L(parent, text, **kw):
        return tk.Label(parent, text=text, bg=BG, fg=FG, font=MONO, **kw)

    def E(parent, var, width=24):
        return tk.Entry(parent, textvariable=var, width=width, bg="#0a0a0a", fg=FG,
                        insertbackground=YELLOW, font=MONO, relief="flat",
                        highlightthickness=1, highlightbackground="#555",
                        highlightcolor=YELLOW)

    def log(msg):
        out.configure(state="normal")
        out.insert("end", str(msg) + "\n")
        out.see("end")
        out.configure(state="disabled")

    # --- titulo ---
    tk.Label(root, text="♥  DELTARUNE  —  PARCHE ES-CL", bg=BG, fg=YELLOW,
             font=TITLE_FONT).pack(pady=(14, 2))
    L(root, "Traduccion al espanol chileno  ·  Capitulo 1").pack()

    # --- caja de dialogo (borde blanco tipo textbox) ---
    box = tk.Frame(root, bg=BG, highlightbackground=FG, highlightthickness=3)
    box.pack(fill="x", padx=16, pady=12)

    # fuente
    tk.Radiobutton(box, text="Desde el repo (GitHub)", variable=src_mode, value="repo",
                   bg=BG, fg=FG, selectcolor=BG, activebackground=BG, activeforeground=YELLOW,
                   font=MONO_B).grid(row=0, column=0, sticky="w", padx=6, pady=(6, 0))
    repo_row = tk.Frame(box, bg=BG)
    repo_row.grid(row=1, column=0, columnspan=4, sticky="w", padx=24)
    L(repo_row, "usuario:").grid(row=0, column=0, sticky="w")
    E(repo_row, owner_v, 16).grid(row=0, column=1, padx=(2, 10))
    L(repo_row, "repo:").grid(row=0, column=2, sticky="w")
    E(repo_row, repo_v, 16).grid(row=0, column=3, padx=(2, 10))
    L(repo_row, "rama:").grid(row=0, column=4, sticky="w")
    E(repo_row, branch_v, 10).grid(row=0, column=5, padx=(2, 10))
    L(repo_row, "cap:").grid(row=0, column=6, sticky="w")
    E(repo_row, chapter_v, 4).grid(row=0, column=7, padx=2)

    tk.Radiobutton(box, text="Archivo local (json/xlsx/csv)", variable=src_mode, value="file",
                   bg=BG, fg=FG, selectcolor=BG, activebackground=BG, activeforeground=YELLOW,
                   font=MONO_B).grid(row=2, column=0, sticky="w", padx=6, pady=(8, 0))
    file_row = tk.Frame(box, bg=BG)
    file_row.grid(row=3, column=0, columnspan=4, sticky="we", padx=24, pady=(0, 6))
    E(file_row, file_v, 44).grid(row=0, column=0, sticky="we")
    _dr_button(file_row, "Examinar...",
               lambda: file_v.set(filedialog.askopenfilename(
                   filetypes=[("Traduccion", "*.json *.xlsx *.csv")]) or file_v.get())
               ).grid(row=0, column=1, padx=6)

    # juego
    game_box = tk.Frame(root, bg=BG, highlightbackground=FG, highlightthickness=3)
    game_box.pack(fill="x", padx=16, pady=(0, 12))
    L(game_box, "Carpeta del juego:").grid(row=0, column=0, sticky="w", padx=6, pady=6)
    E(game_box, game_v, 44).grid(row=0, column=1, sticky="we", pady=6)
    game_box.columnconfigure(1, weight=1)
    _dr_button(game_box, "Examinar...",
               lambda: game_v.set(filedialog.askdirectory() or game_v.get())
               ).grid(row=0, column=2, padx=4)
    _dr_button(game_box, "Auto-detectar",
               lambda: (game_v.set(autodetect_game() or game_v.get()),
                        log("* Auto-deteccion: " + (game_v.get() or "no encontrado")))
               ).grid(row=0, column=3, padx=4)

    # --- acciones ---
    def _do_patch():
        if not game_v.get():
            messagebox.showwarning("Falta juego", "Selecciona la carpeta del juego.")
            return
        try:
            if src_mode.get() == "repo":
                patch_from_repo(owner_v.get(), repo_v.get(), branch_v.get(),
                                int(chapter_v.get() or 1), game_v.get(), log=log)
            else:
                if not file_v.get():
                    messagebox.showwarning("Falta archivo", "Selecciona el archivo local.")
                    return
                patch_from_file(file_v.get(), game_v.get(), log=log)
            messagebox.showinfo("Listo", "Juego parchado. Abre Deltarune para probar.")
        except core.SecurityError as e:
            log("* SEGURIDAD: " + str(e))
            messagebox.showerror("Seguridad", str(e))
        except Exception as e:
            log("* ERROR: " + str(e))
            messagebox.showerror("Error", str(e))

    def _do_restore():
        try:
            t = core.restore_game(Path(game_v.get()))
            log("* Restaurado el original: " + str(t))
            messagebox.showinfo("Listo", "Se restauro el lang_en.json original.")
        except Exception as e:
            log("* ERROR: " + str(e))
            messagebox.showerror("Error", str(e))

    def _do_check():
        try:
            base = repo_base_url(owner_v.get(), repo_v.get(), branch_v.get(),
                                 int(chapter_v.get() or 1))
            man = core.fetch_manifest(base)
            log(f"* manifest OK  version={man.get('version')}  assets={len(man.get('assets', []))}")
            for a in man.get("assets", []):
                log(f"    - {a.get('type')}: {a.get('src')}  sha={str(a.get('sha256'))[:12]}...")
        except Exception as e:
            log("* ERROR verificando: " + str(e))

    btns = tk.Frame(root, bg=BG)
    btns.pack(fill="x", padx=16)
    _dr_button(btns, "Verificar repo", _do_check).pack(side="left", padx=4)
    _dr_button(btns, "Descargar y parchar", _do_patch).pack(side="left", padx=4)
    _dr_button(btns, "Restaurar original", _do_restore).pack(side="left", padx=4)

    L(root, "* Registro:").pack(anchor="w", padx=18, pady=(10, 0))
    out = scrolledtext.ScrolledText(root, state="disabled", height=13, bg="#050505",
                                    fg=FG, insertbackground=YELLOW, font=MONO,
                                    highlightbackground=FG, highlightthickness=2)
    out.pack(fill="both", expand=True, padx=16, pady=(2, 14))

    log("* Bienvenid@. Elige la fuente, la carpeta del juego, y dale a parchar.")
    log("* El lang_en.json original se respalda como lang_en.json" + core.BACKUP_SUFFIX)
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
