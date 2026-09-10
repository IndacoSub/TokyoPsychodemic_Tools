#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import re
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk
from tkinter.font import Font


APP_TITLE = "Tokyo Psychodemic — Translation Editor v14"
DEFAULT_GEOMETRY = "1900x1050"

STATUS_FILENAME = ".translation_status.json"


# ============================================================
# MARKUP
# ============================================================

TOKEN_RE = re.compile(
    r"<[^>]+>|＜[^＞]+＞|\[[^\]\r\n]*\]"
)

COLOR_OPEN_RE = re.compile(
    r"^<color=#([0-9A-Fa-f]{3,8})>$"
)

SIZE_OPEN_RE = re.compile(
    r"^<(?:size|サイズ)=([^>]+)>$"
)

LINK_OPEN_RE = re.compile(
    r"^<(?:link|リンク)=([^>]+)>$"
)

BUTTON_GUIDE_RE = re.compile(
    r"^<ButtonGuide:([^>]+)>$"
)


OPEN_SIMPLE = {
    "<b>": "bold",
    "<strong>": "bold",
    "<u>": "underline",
    "＜強調＞": "bold",
}


CLOSE_SIMPLE = {
    "</b>": "bold",
    "</strong>": "bold",
    "</u>": "underline",
    "＜／強調＞": "bold",
    "＜/強調＞": "bold",
}


CLOSE_KIND = {
    "</color>": "color",
    "</size>": "size",
    "</サイズ>": "size",
    "</link>": "link",
    "</リンク>": "link",
}


BUTTON_GUIDE_PREVIEW = {
    "Circle": "◯",
    "Square": "□",
    "Triangle": "△",
    "Cross": "✕",
    "AdvFastForward": "»",
    "AdvAutoMessageSendOn": "AUTO",
    "Start": "START",
    "Select": "SELECT",
    "L1": "L1",
    "L2": "L2",
    "L3": "L3",
    "R1": "R1",
    "R2": "R2",
    "R3": "R3",
    "DPadUp": "↑",
    "DPadDown": "↓",
    "DPadLeft": "←",
    "DPadRight": "→",
}


# ============================================================
# FILE HELPERS
# ============================================================

def read_text(path: Path) -> str:
    last_error = None

    for encoding in (
        "utf-8-sig",
        "utf-8",
        "cp932",
    ):
        try:
            with path.open(
                "r",
                encoding=encoding,
                newline="",
            ) as f:
                return f.read()

        except UnicodeDecodeError as exc:
            last_error = exc

    raise ValueError(
        f"Impossibile leggere '{path}'. "
        "Provati UTF-8 BOM, UTF-8 e CP932."
    ) from last_error


def write_text(
    path: Path,
    text: str,
) -> None:

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        f.write(text)


# ============================================================
# ESCAPES
# ============================================================

def decode_game_escapes(
    text: str,
) -> str:

    out = []
    i = 0

    while i < len(text):

        if text[i] != "\\":
            out.append(text[i])
            i += 1
            continue

        if i + 1 >= len(text):
            out.append("\\")
            break

        nxt = text[i + 1]

        if nxt == "n":
            out.append("\n")

        elif nxt == "r":
            out.append("\r")

        elif nxt == "t":
            out.append("\t")

        elif nxt == "\\":
            out.append("\\")

        else:
            out.append("\\")
            out.append(nxt)

        i += 2

    return "".join(out)


# ============================================================
# UABEA EXPORT DUMP
# ============================================================

def parse_dump_quoted_string(
    value: str,
) -> str:

    value = value.strip()

    if (
        len(value) < 2
        or value[0] != '"'
        or value[-1] != '"'
    ):
        raise ValueError(
            "Stringa quotata UABEA non valida."
        )

    inner = value[1:-1]

    out = []
    i = 0

    while i < len(inner):

        ch = inner[i]

        if ch != "\\":
            out.append(ch)
            i += 1
            continue

        if i + 1 >= len(inner):
            out.append("\\")
            break

        nxt = inner[i + 1]

        if nxt == "n":
            out.append("\n")

        elif nxt == "r":
            out.append("\r")

        elif nxt == "t":
            out.append("\t")

        elif nxt == "\\":
            out.append("\\")

        elif nxt == '"':
            out.append('"')

        else:
            out.append("\\")
            out.append(nxt)

        i += 2

    return "".join(out)


def extract_script_from_uabea_dump(
    text: str,
) -> str | None:

    text = text.lstrip("\ufeff")

    if not text.startswith(
        "0 TextAsset Base"
    ):
        return None

    prefix = " 1 string m_Script = "

    found = None

    normalized = (
        text
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )

    for line in normalized.split("\n"):

        if line.startswith(prefix):

            if found is not None:
                raise ValueError(
                    "Il dump contiene più di un m_Script."
                )

            found = line[
                len(prefix):
            ].rstrip()

    if found is None:

        raise ValueError(
            "Export Dump rilevato, "
            "ma m_Script non trovato."
        )

    return parse_dump_quoted_string(
        found
    )


# ============================================================
# PARSER
# ============================================================

def split_plugin_line(
    line: str,
) -> tuple[str, str]:

    position = line.find("==")

    if position < 0:
        raise ValueError(
            "Separatore '==' mancante."
        )

    return (
        line[:position],
        line[position + 2:],
    )


def parse_entries(
    text: str,
) -> list[tuple[str, str]]:

    script = extract_script_from_uabea_dump(
        text
    )

    if script is None:
        script = text

    script = script.lstrip("\ufeff")

    script = (
        script
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )

    result = []

    for line_number, line in enumerate(
        script.split("\n"),
        1,
    ):

        if line == "":
            continue

        if "==" not in line:

            if line.strip() == "":
                continue

            raise ValueError(
                f"Riga {line_number}: "
                "separatore '==' mancante."
            )

        key, value = split_plugin_line(
            line
        )

        if not key:
            raise ValueError(
                f"Riga {line_number}: "
                "chiave vuota."
            )

        result.append(
            (
                key,
                value,
            )
        )

    return result


# ============================================================
# ENTRY ID
# ============================================================

def make_entry_id(
    key: str,
    occurrence: int,
) -> str:

    return (
        f"{key}\x00{occurrence}"
    )


# ============================================================
# APPLICATION
# ============================================================

class TranslationEditor(tk.Tk):

    def __init__(self):

        super().__init__()

        self.title(
            APP_TITLE
        )

        self.geometry(
            DEFAULT_GEOMETRY
        )

        self.minsize(
            1300,
            800,
        )

        # ----------------------------------------------------
        # Data
        # ----------------------------------------------------

        self.entries: list[dict] = []

        self.original_entries: dict[
            str,
            str,
        ] = {}

        self.manual_translated_ids: set[
            str
        ] = set()

        # ----------------------------------------------------
        # Selection
        # ----------------------------------------------------

        self.current_index = -1

        # ----------------------------------------------------
        # Files
        # ----------------------------------------------------

        self.loaded_folder: Path | None = None

        self.translation_path: Path | None = None

        self.original_path: Path | None = None

        self.status_path: Path | None = None

        # ----------------------------------------------------
        # Internal state
        # ----------------------------------------------------

        self._updating = False

        self._dirty = False

        self._closing = False

        self._context_menu_index = -1

        # ----------------------------------------------------
        # Filter
        # ----------------------------------------------------

        self.list_filter = tk.StringVar(
            value="Mostra tutto"
        )

        # ----------------------------------------------------
        # Preview
        # ----------------------------------------------------

        self.preview_bg = "#ffffff"

        self.preview_fg = "#000000"

        self.preview_base_size = 14

        self.preview_size_scale = 0.50

        self._font_cache: dict[
            tuple[int, bool, bool],
            Font,
        ] = {}

        # ----------------------------------------------------
        # Fonts
        # ----------------------------------------------------

        self.list_font = Font(
            family="Segoe UI",
            size=11,
            weight="normal",
        )

        self.list_font_bold = Font(
            family="Segoe UI",
            size=11,
            weight="bold",
        )

        self.source_font = Font(
            family="Consolas",
            size=11,
        )

        self.source_placeholder_font = Font(
            family="Consolas",
            size=11,
            weight="bold",
        )

        # ----------------------------------------------------
        # Build
        # ----------------------------------------------------

        self._build_ui()

        self._bind_events()

        self._maximize_window()

        self._update_title()

    # ========================================================
    # WINDOW
    # ========================================================

    def _maximize_window(self):

        try:

            self.state(
                "zoomed"
            )

            return

        except tk.TclError:
            pass

        width = self.winfo_screenwidth()

        height = self.winfo_screenheight()

        self.geometry(
            f"{max(1300, width - 20)}x"
            f"{max(800, height - 60)}"
        )

    def toggle_fullscreen(self):

        try:

            self.state(
                "normal"
                if self.state() == "zoomed"
                else "zoomed"
            )

        except tk.TclError:
            pass

    # ========================================================
    # UI
    # ========================================================

    def _build_ui(self):

        # ----------------------------------------------------
        # TOOLBAR
        # ----------------------------------------------------

        toolbar = ttk.Frame(
            self,
            padding=10,
        )

        toolbar.pack(
            fill="x"
        )

        ttk.Button(
            toolbar,
            text="Apri cartella…",
            command=self.open_folder,
        ).pack(
            side="left"
        )

        ttk.Button(
            toolbar,
            text="Salva",
            command=self.save_file,
        ).pack(
            side="left",
            padx=(6, 0),
        )

        ttk.Separator(
            toolbar,
            orient="vertical",
        ).pack(
            side="left",
            fill="y",
            padx=12,
        )

        ttk.Button(
            toolbar,
            text="Sfondo preview…",
            command=self.choose_preview_background,
        ).pack(
            side="left"
        )

        ttk.Label(
            toolbar,
            text="Base:",
        ).pack(
            side="left",
            padx=(12, 4),
        )

        self.base_size_var = tk.StringVar(
            value=str(
                self.preview_base_size
            )
        )

        self.base_size_spin = tk.Spinbox(
            toolbar,
            from_=6,
            to=48,
            width=5,
            textvariable=self.base_size_var,
            command=self._preview_settings_changed,
        )

        self.base_size_spin.pack(
            side="left"
        )

        self.base_size_spin.bind(
            "<KeyRelease>",
            self._preview_settings_changed,
        )

        ttk.Label(
            toolbar,
            text="<size> ×",
        ).pack(
            side="left",
            padx=(10, 4),
        )

        self.size_scale_var = tk.StringVar(
            value=f"{self.preview_size_scale:.2f}"
        )

        self.size_scale_spin = tk.Spinbox(
            toolbar,
            from_=0.10,
            to=3.00,
            increment=0.05,
            width=6,
            textvariable=self.size_scale_var,
            command=self._preview_settings_changed,
        )

        self.size_scale_spin.pack(
            side="left"
        )

        self.size_scale_spin.bind(
            "<KeyRelease>",
            self._preview_settings_changed,
        )

        ttk.Label(
            toolbar,
            text="es. <size=24> × 0.50 → 12px",
        ).pack(
            side="left",
            padx=(8, 0),
        )

        ttk.Button(
            toolbar,
            text="Fullscreen",
            command=self.toggle_fullscreen,
        ).pack(
            side="left",
            padx=(12, 0),
        )

        ttk.Separator(
            toolbar,
            orient="vertical",
        ).pack(
            side="left",
            fill="y",
            padx=12,
        )

        ttk.Label(
            toolbar,
            text="Cerca:",
        ).pack(
            side="left"
        )

        self.search_var = tk.StringVar()

        self.search = ttk.Entry(
            toolbar,
            textvariable=self.search_var,
            width=40,
        )

        self.search.pack(
            side="left",
            padx=(6, 0),
        )

        ttk.Button(
            toolbar,
            text="Trova",
            command=self.find_next,
        ).pack(
            side="left",
            padx=(6, 0),
        )

        self.status_var = tk.StringVar(
            value="Apri la cartella del progetto"
        )

        ttk.Label(
            toolbar,
            textvariable=self.status_var,
        ).pack(
            side="right"
        )

        # ----------------------------------------------------
        # MAIN PANES
        # ----------------------------------------------------

        main = ttk.Panedwindow(
            self,
            orient="horizontal",
        )

        main.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=(0, 10),
        )

        left = ttk.Frame(
            main,
            padding=6,
        )

        center = ttk.Frame(
            main,
            padding=6,
        )

        right = ttk.Frame(
            main,
            padding=6,
        )

        main.add(
            left,
            weight=4,
        )

        main.add(
            center,
            weight=5,
        )

        main.add(
            right,
            weight=4,
        )

        # ====================================================
        # LEFT / LIST
        # ====================================================

        left_header = ttk.Frame(
            left
        )

        left_header.pack(
            fill="x",
            pady=(0, 6),
        )

        ttk.Label(
            left_header,
            text="KEY",
            font=(
                "Segoe UI",
                10,
                "bold",
            ),
        ).pack(
            side="left"
        )

        ttk.Label(
            left_header,
            text="Grassetto = non ancora tradotta",
        ).pack(
            side="left",
            padx=(10, 0),
        )

        filter_frame = ttk.Frame(
            left
        )

        filter_frame.pack(
            fill="x",
            pady=(0, 6),
        )

        ttk.Label(
            filter_frame,
            text="Visualizza:",
        ).pack(
            side="left"
        )

        self.filter_combo = ttk.Combobox(
            filter_frame,
            textvariable=self.list_filter,
            values=(
                "Mostra tutto",
                "Mostra non tradotti",
                "Mostra tradotti",
            ),
            state="readonly",
            width=22,
        )

        self.filter_combo.pack(
            side="left",
            padx=(8, 0),
        )

        list_wrap = ttk.Frame(
            left
        )

        list_wrap.pack(
            fill="both",
            expand=True,
        )

        self.listbox = ttk.Treeview(
            list_wrap,
            columns=("key",),
            show="headings",
            selectmode="browse",
        )

        self.listbox.heading(
            "key",
            text="KEY",
        )

        self.listbox.column(
            "key",
            width=500,
            minwidth=300,
            anchor="w",
            stretch=True,
        )

        self.listbox.tag_configure(
            "translated",
            font=(
                "Segoe UI",
                11,
                "normal",
            ),
        )

        self.listbox.tag_configure(
            "untranslated",
            font=(
                "Segoe UI",
                11,
                "bold",
            ),
        )

        self.listbox.tag_configure(
            "manual",
            font=(
                "Segoe UI",
                11,
                "normal",
            ),
        )

        list_scroll = ttk.Scrollbar(
            list_wrap,
            orient="vertical",
            command=self.listbox.yview,
        )

        self.listbox.configure(
            yscrollcommand=list_scroll.set,
        )

        self.listbox.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        list_scroll.grid(
            row=0,
            column=1,
            sticky="ns",
        )

        list_wrap.rowconfigure(
            0,
            weight=1,
        )

        list_wrap.columnconfigure(
            0,
            weight=1,
        )

        # ====================================================
        # CENTER / SOURCE
        # ====================================================

        source_header = ttk.Frame(
            center
        )

        source_header.pack(
            fill="x",
            pady=(0, 6),
        )

        ttk.Label(
            source_header,
            text=(
                "VERO TESTO — "
                "SORGENTE MODIFICABILE"
            ),
            font=(
                "Segoe UI",
                10,
                "bold",
            ),
        ).pack(
            side="left"
        )

        ttk.Label(
            source_header,
            text=(
                "Tag e \\n "
                "rimangono visibili."
            ),
        ).pack(
            side="right"
        )

        source_wrap = ttk.Frame(
            center
        )

        source_wrap.pack(
            fill="both",
            expand=True,
        )

        self.source = tk.Text(
            source_wrap,
            wrap="word",
            undo=True,
            maxundo=-1,
            font=self.source_font,
            padx=12,
            pady=12,
            relief="solid",
            borderwidth=1,
            background="#ffffff",
            foreground="#111111",
            insertbackground="#111111",
            selectbackground="#cfe8ff",
        )

        source_scroll = ttk.Scrollbar(
            source_wrap,
            orient="vertical",
            command=self.source.yview,
        )

        self.source.configure(
            yscrollcommand=source_scroll.set
        )

        self.source.pack(
            side="left",
            fill="both",
            expand=True,
        )

        source_scroll.pack(
            side="right",
            fill="y",
        )

        self.source.tag_configure(
            "src_tag",
            foreground="#7B2CBF",
        )

        self.source.tag_configure(
            "src_link",
            foreground="#0066CC",
            underline=True,
        )

        self.source.tag_configure(
            "src_color",
            foreground="#C0392B",
        )

        self.source.tag_configure(
            "src_size",
            foreground="#D68910",
        )

        self.source.tag_configure(
            "src_button",
            foreground="#008060",
            underline=True,
        )

        self.source.tag_configure(
            "src_placeholder",
            foreground="#7D3C98",
            font=self.source_placeholder_font,
        )

        self.source.tag_configure(
            "src_escape",
            foreground="#808080",
        )

        source_footer = ttk.Frame(
            center
        )

        source_footer.pack(
            fill="x",
            pady=(7, 0),
        )

        self.source_info_var = tk.StringVar()

        ttk.Label(
            source_footer,
            textvariable=self.source_info_var,
        ).pack(
            side="left"
        )

        self.valid_var = tk.StringVar()

        ttk.Label(
            source_footer,
            textvariable=self.valid_var,
        ).pack(
            side="right"
        )

        # ====================================================
        # RIGHT / PREVIEW
        # ====================================================

        preview_header = ttk.Frame(
            right
        )

        preview_header.pack(
            fill="x",
            pady=(0, 6),
        )

        ttk.Label(
            preview_header,
            text=(
                "TESTO VISIBILE — "
                "PREVIEW LIVE"
            ),
            font=(
                "Segoe UI",
                10,
                "bold",
            ),
        ).pack(
            side="left"
        )

        self.preview_color_label = tk.StringVar(
            value=(
                f"sfondo: "
                f"{self.preview_bg}"
            )
        )

        ttk.Label(
            preview_header,
            textvariable=self.preview_color_label,
        ).pack(
            side="right"
        )

        preview_wrap = ttk.Frame(
            right
        )

        preview_wrap.pack(
            fill="both",
            expand=True,
        )

        self.preview = tk.Text(
            preview_wrap,
            wrap="word",
            state="disabled",
            font=Font(
                family="Segoe UI",
                size=self.preview_base_size,
            ),
            padx=16,
            pady=16,
            relief="solid",
            borderwidth=1,
            background=self.preview_bg,
            foreground=self.preview_fg,
            cursor="arrow",
        )

        preview_scroll = ttk.Scrollbar(
            preview_wrap,
            orient="vertical",
            command=self.preview.yview,
        )

        self.preview.configure(
            yscrollcommand=preview_scroll.set
        )

        self.preview.pack(
            side="left",
            fill="both",
            expand=True,
        )

        preview_scroll.pack(
            side="right",
            fill="y",
        )

        self.preview.tag_configure(
            "preview_placeholder",
            foreground="#7D3C98",
        )

        self.preview.tag_configure(
            "preview_button",
            relief="raised",
            borderwidth=1,
        )

        ttk.Separator(
            right,
            orient="horizontal",
        ).pack(
            fill="x",
            pady=10,
        )

        ttk.Label(
            right,
            text="ELEMENTO SOTTO IL CURSORE",
            font=(
                "Segoe UI",
                9,
                "bold",
            ),
        ).pack(
            anchor="w"
        )

        self.inspector_var = tk.StringVar(
            value=(
                "Posiziona il cursore su "
                "tag, link, ButtonGuide "
                "o placeholder."
            )
        )

        ttk.Label(
            right,
            textvariable=self.inspector_var,
            justify="left",
            wraplength=520,
        ).pack(
            anchor="w",
            fill="x",
            pady=(4, 0),
        )

        # ====================================================
        # BOTTOM
        # ====================================================

        bottom = ttk.Frame(
            self,
            padding=(10, 0, 10, 10),
        )

        bottom.pack(
            fill="x"
        )

        ttk.Button(
            bottom,
            text="◀ Precedente",
            command=self.previous_entry,
        ).pack(
            side="left"
        )

        self.index_var = tk.StringVar(
            value="0 / 0"
        )

        ttk.Label(
            bottom,
            textvariable=self.index_var,
        ).pack(
            side="left",
            padx=12,
        )

        ttk.Button(
            bottom,
            text="Successiva ▶",
            command=self.next_entry,
        ).pack(
            side="left"
        )

        self.file_var = tk.StringVar()

        ttk.Label(
            bottom,
            textvariable=self.file_var,
        ).pack(
            side="right"
        )

    # ========================================================
    # EVENTS
    # ========================================================

    def _bind_events(self):

        self.listbox.bind(
            "<<TreeviewSelect>>",
            self._on_list_select,
        )

        self.listbox.bind(
            "<Button-3>",
            self._on_list_right_click,
        )

        self.filter_combo.bind(
            "<<ComboboxSelected>>",
            self._on_filter_changed,
        )

        self.source.bind(
            "<<Modified>>",
            self._on_source_modified,
        )

        self.source.bind(
            "<KeyRelease>",
            self._on_source_key_release,
            add="+",
        )

        self.source.bind(
            "<ButtonRelease-1>",
            self._update_inspector,
        )

        self.source.bind(
            "<Motion>",
            self._update_inspector,
        )

        self.bind(
            "<Control-s>",
            self._shortcut_save,
        )

        self.bind(
            "<Control-o>",
            self._shortcut_open,
        )

        self.bind(
            "<Control-f>",
            self._shortcut_find,
        )

        self.bind(
            "<F3>",
            self._shortcut_find_next,
        )

        self.bind(
            "<F11>",
            self._shortcut_fullscreen,
        )

        self.protocol(
            "WM_DELETE_WINDOW",
            self._close,
        )

    def _shortcut_save(
        self,
        _event=None,
    ):

        self.save_file()

        return "break"

    def _shortcut_open(
        self,
        _event=None,
    ):

        self.open_folder()

        return "break"

    def _shortcut_find(
        self,
        _event=None,
    ):

        self.search.focus_set()

        self.search.selection_range(
            0,
            "end",
        )

        return "break"

    def _shortcut_find_next(
        self,
        _event=None,
    ):

        self.find_next()

        return "break"

    def _shortcut_fullscreen(
        self,
        _event=None,
    ):

        self.toggle_fullscreen()

        return "break"

    # ========================================================
    # FILTER
    # ========================================================

    def _entry_matches_filter(
        self,
        entry: dict,
    ) -> bool:

        current_filter = (
            self.list_filter
            .get()
            .strip()
        )

        if current_filter == "Mostra non tradotti":

            return self._is_untranslated(
                entry
            )

        if current_filter == "Mostra tradotti":

            return not self._is_untranslated(
                entry
            )

        return True

    def _on_filter_changed(
        self,
        _event=None,
    ):

        self._commit_current()

        old_index = self.current_index

        self._populate_list()

        if not self.entries:
            return

        # Keep current entry selected when it still
        # exists in the filtered list.
        if (
            0 <= old_index < len(self.entries)
            and self._entry_matches_filter(
                self.entries[old_index]
            )
            and self.listbox.exists(
                str(old_index)
            )
        ):

            self.select_index(
                old_index
            )

            return

        # Current entry is hidden by the filter.
        visible_indices = (
            self._visible_indices()
        )

        if visible_indices:

            self.select_index(
                visible_indices[0]
            )

        else:

            self.current_index = -1

            self.source.delete(
                "1.0",
                "end",
            )

            self.preview.configure(
                state="normal"
            )

            self.preview.delete(
                "1.0",
                "end",
            )

            self.preview.configure(
                state="disabled"
            )

            self.index_var.set(
                "0 / 0"
            )

            self.source_info_var.set(
                "Nessuna entry corrisponde al filtro."
            )

    def _visible_indices(self) -> list[int]:

        result = []

        for item in self.listbox.get_children():

            try:

                result.append(
                    int(item)
                )

            except (
                TypeError,
                ValueError,
            ):

                continue

        return result

    def _next_visible_index(
        self,
    ) -> int | None:

        visible = self._visible_indices()

        if not visible:
            return None

        for index in visible:

            if index > self.current_index:
                return index

        # Wrap around.
        return visible[0]

    def _previous_visible_index(
        self,
    ) -> int | None:

        visible = self._visible_indices()

        if not visible:
            return None

        previous = None

        for index in visible:

            if index >= self.current_index:
                break

            previous = index

        if previous is not None:
            return previous

        # Wrap around to the last visible entry.
        return visible[-1]

    # ========================================================
    # CONTEXT MENU
    # ========================================================

    def _on_list_right_click(
        self,
        event,
    ):

        row = self.listbox.identify_row(
            event.y
        )

        if not row:
            return "break"

        try:

            index = int(
                row
            )

        except (
            TypeError,
            ValueError,
        ):

            return "break"

        if not (
            0 <= index
            < len(self.entries)
        ):

            return "break"

        self._commit_current()

        # Select right-clicked row.
        self.listbox.selection_set(
            row
        )

        self.listbox.focus(
            row
        )

        self.select_index(
            index
        )

        self._context_menu_index = index

        menu = tk.Menu(
            self,
            tearoff=False,
        )

        entry = self.entries[
            index
        ]

        if self._is_manually_translated(
            entry
        ):

            menu.add_command(
                label=(
                    "Segna come NON tradotta"
                ),
                command=lambda idx=index:
                    self._toggle_manual_translation(
                        idx
                    ),
            )

        else:

            menu.add_command(
                label=(
                    "Segna come tradotta"
                ),
                command=lambda idx=index:
                    self._toggle_manual_translation(
                        idx
                    ),
            )

        menu.add_separator()

        if self._is_manually_translated(
            entry
        ):

            menu.add_command(
                label=(
                    "Stato: tradotta manualmente"
                ),
                state="disabled",
            )

        elif self._is_untranslated(
            entry
        ):

            menu.add_command(
                label=(
                    "Stato: non tradotta "
                    "(uguale all'originale)"
                ),
                state="disabled",
            )

        else:

            menu.add_command(
                label=(
                    "Stato: tradotta"
                ),
                state="disabled",
            )

        try:

            menu.tk_popup(
                event.x_root,
                event.y_root,
            )

        finally:

            menu.grab_release()

        return "break"

    def _toggle_manual_translation(
        self,
        index: int,
    ):

        if not (
            0 <= index
            < len(self.entries)
        ):
            return

        entry = self.entries[
            index
        ]

        entry_id = entry[
            "id"
        ]

        if (
            entry_id
            in self.manual_translated_ids
        ):

            self.manual_translated_ids.remove(
                entry_id
            )

            action_text = (
                "Segnata come NON tradotta"
            )

        else:

            self.manual_translated_ids.add(
                entry_id
            )

            action_text = (
                "Segnata come tradotta"
            )

        self._save_manual_translation_state()

        self._refresh_list_item(
            index
        )

        self._update_status_counts()

        self.status_var.set(
            self.status_var.get()
            + f"  •  {action_text}"
        )

    # ========================================================
    # PREVIEW SETTINGS
    # ========================================================

    def _preview_settings_changed(
        self,
        _event=None,
    ):

        try:

            base = int(
                self.base_size_var.get()
            )

            scale = float(
                self.size_scale_var.get()
            )

        except (
            ValueError,
            tk.TclError,
        ):

            return

        base = max(
            6,
            min(
                48,
                base,
            ),
        )

        scale = max(
            0.10,
            min(
                3.00,
                scale,
            ),
        )

        self.preview_base_size = base

        self.preview_size_scale = scale

        self.base_size_var.set(
            str(base)
        )

        self.size_scale_var.set(
            f"{scale:.2f}"
        )

        self._font_cache.clear()

        self._render_preview()

    # ========================================================
    # FOLDER
    # ========================================================

    def open_folder(self):

        if self._dirty:

            answer = messagebox.askyesnocancel(
                "Modifiche non salvate",
                (
                    "Ci sono modifiche non salvate.\n\n"
                    "Salvare prima di cambiare cartella?"
                ),
            )

            if answer is None:
                return

            if answer:

                self.save_file()

                if self._dirty:
                    return

        folder = filedialog.askdirectory(
            title=(
                "Seleziona la cartella contenente "
                "English.txt e English_original.txt"
            )
        )

        if not folder:
            return

        folder_path = Path(
            folder
        )

        translation_path = (
            folder_path
            / "English.txt"
        )

        original_path = (
            folder_path
            / "English_original.txt"
        )

        status_path = (
            folder_path
            / STATUS_FILENAME
        )

        missing = []

        if not translation_path.is_file():

            missing.append(
                "English.txt"
            )

        if not original_path.is_file():

            missing.append(
                "English_original.txt"
            )

        if missing:

            messagebox.showerror(
                "File mancanti",
                (
                    "Nella cartella manca:\n\n"
                    + "\n".join(
                        f"• {name}"
                        for name in missing
                    )
                ),
            )

            return

        try:

            translation_pairs = parse_entries(
                read_text(
                    translation_path
                )
            )

            original_pairs = parse_entries(
                read_text(
                    original_path
                )
            )

        except Exception as exc:

            messagebox.showerror(
                "Errore di lettura",
                (
                    "Non riesco a leggere "
                    "i file:\n\n"
                    f"{exc}"
                ),
            )

            return

        if not translation_pairs:

            messagebox.showerror(
                "English.txt vuoto",
                "Nessuna stringa trovata.",
            )

            return

        # ----------------------------------------------------
        # Translation occurrences
        # ----------------------------------------------------

        translation_occurrences = {}

        self.entries = []

        for key, value in translation_pairs:

            occurrence = (
                translation_occurrences.get(
                    key,
                    0,
                )
                + 1
            )

            translation_occurrences[
                key
            ] = occurrence

            entry_id = make_entry_id(
                key,
                occurrence,
            )

            self.entries.append(
                {
                    "id": entry_id,
                    "key": key,
                    "value": value,
                    "occurrence": occurrence,
                }
            )

        # ----------------------------------------------------
        # Original occurrences
        # ----------------------------------------------------

        original_occurrences = {}

        self.original_entries.clear()

        for key, value in original_pairs:

            occurrence = (
                original_occurrences.get(
                    key,
                    0,
                )
                + 1
            )

            original_occurrences[
                key
            ] = occurrence

            entry_id = make_entry_id(
                key,
                occurrence,
            )

            self.original_entries[
                entry_id
            ] = value

        self.loaded_folder = (
            folder_path
        )

        self.translation_path = (
            translation_path
        )

        self.original_path = (
            original_path
        )

        self.status_path = (
            status_path
        )

        self._load_manual_translation_state()

        self.current_index = -1

        self._dirty = False

        self._populate_list()

        self._update_status_counts()

        visible = self._visible_indices()

        if visible:

            self.select_index(
                visible[0]
            )

        else:

            self.index_var.set(
                "0 / 0"
            )

        self.file_var.set(
            str(
                self.loaded_folder
            )
        )

        self._update_title()

    # ========================================================
    # MANUAL STATUS PERSISTENCE
    # ========================================================

    def _load_manual_translation_state(self):

        self.manual_translated_ids.clear()

        if self.status_path is None:
            return

        if not self.status_path.is_file():
            return

        try:

            raw = read_text(
                self.status_path
            )

            data = json.loads(
                raw
            )

        except (
            OSError,
            ValueError,
            json.JSONDecodeError,
        ):

            return

        saved_ids = []

        old_keys = []

        if isinstance(
            data,
            dict,
        ):

            saved_ids = data.get(
                "manual_translated_ids",
                [],
            )

            # Compatibility with v12.
            old_keys = data.get(
                "manual_translated_keys",
                [],
            )

        elif isinstance(
            data,
            list,
        ):

            old_keys = data

        valid_ids = {
            entry["id"]
            for entry in self.entries
        }

        if isinstance(
            saved_ids,
            list,
        ):

            for entry_id in saved_ids:

                if (
                    isinstance(
                        entry_id,
                        str,
                    )
                    and entry_id
                    in valid_ids
                ):

                    self.manual_translated_ids.add(
                        entry_id
                    )

        # Convert old key-only format into
        # all matching occurrences.
        if isinstance(
            old_keys,
            list,
        ):

            for key in old_keys:

                if not isinstance(
                    key,
                    str,
                ):
                    continue

                for entry in self.entries:

                    if entry["key"] == key:

                        self.manual_translated_ids.add(
                            entry["id"]
                        )

    def _save_manual_translation_state(self):

        if self.status_path is None:
            return

        data = {
            "version": 3,
            "manual_translated_ids": sorted(
                self.manual_translated_ids
            ),
        }

        temp_path = self.status_path.with_suffix(
            self.status_path.suffix
            + ".tmp"
        )

        try:

            write_text(
                temp_path,
                json.dumps(
                    data,
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
            )

            temp_path.replace(
                self.status_path
            )

        except OSError as exc:

            try:

                if temp_path.exists():
                    temp_path.unlink()

            except OSError:
                pass

            messagebox.showerror(
                "Errore",
                (
                    "Non riesco a salvare "
                    "lo stato delle traduzioni:\n\n"
                    f"{exc}"
                ),
            )

    # ========================================================
    # STATUS
    # ========================================================

    def _is_manually_translated(
        self,
        entry: dict,
    ) -> bool:

        return (
            entry["id"]
            in self.manual_translated_ids
        )

    def _is_untranslated(
        self,
        entry: dict,
    ) -> bool:

        if self._is_manually_translated(
            entry
        ):

            return False

        original = self.original_entries.get(
            entry["id"]
        )

        if original is None:

            return False

        return (
            entry["value"]
            == original
        )

    def _update_status_counts(self):

        total = len(
            self.entries
        )

        untranslated = 0

        manual = 0

        translated = 0

        no_original = 0

        for entry in self.entries:

            if self._is_manually_translated(
                entry
            ):

                manual += 1

            elif (
                entry["id"]
                not in self.original_entries
            ):

                no_original += 1

            elif self._is_untranslated(
                entry
            ):

                untranslated += 1

            else:

                translated += 1

        total_translated = (
            translated
            + manual
        )

        extra = ""

        if no_original:

            extra = (
                f"  •  {no_original:,} "
                f"senza originale"
            )

        self.status_var.set(
            f"{total:,} stringhe  •  "
            f"{total_translated:,} tradotte  •  "
            f"{untranslated:,} da tradurre"
            f"{extra}"
        )

    # ========================================================
    # LIST
    # ========================================================

    def _populate_list(self):

        for item in self.listbox.get_children():

            self.listbox.delete(
                item
            )

        for index, entry in enumerate(
            self.entries
        ):

            if not self._entry_matches_filter(
                entry
            ):
                continue

            self.listbox.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    entry["key"],
                ),
                tags=(
                    self._row_tag(
                        entry
                    ),
                ),
            )

    def _row_tag(
        self,
        entry: dict,
    ) -> str:

        if self._is_manually_translated(
            entry
        ):

            return "manual"

        if self._is_untranslated(
            entry
        ):

            return "untranslated"

        return "translated"

    def _refresh_all_list_fonts(self):

        for index, entry in enumerate(
            self.entries
        ):

            iid = str(
                index
            )

            if not self.listbox.exists(
                iid
            ):
                continue

            self.listbox.item(
                iid,
                tags=(
                    self._row_tag(
                        entry
                    ),
                ),
            )

    def _refresh_list_item(
        self,
        index: int,
    ):

        if not (
            0 <= index
            < len(self.entries)
        ):
            return

        iid = str(
            index
        )

        if not self.listbox.exists(
            iid
        ):
            return

        self.listbox.item(
            iid,
            tags=(
                self._row_tag(
                    self.entries[index]
                ),
            ),
        )

    # ========================================================
    # SELECTION
    # ========================================================

    def _on_list_select(
        self,
        _event=None,
    ):

        if self._updating:
            return

        selected = (
            self.listbox.selection()
        )

        if not selected:
            return

        try:

            index = int(
                selected[0]
            )

        except (
            TypeError,
            ValueError,
        ):

            return

        if index == self.current_index:
            return

        self._commit_current()

        self.select_index(
            index
        )

    def select_index(
        self,
        index: int,
    ):

        if not self.entries:
            return

        if not (
            0 <= index
            < len(self.entries)
        ):
            return

        # If programmatically called with an entry hidden
        # by the current filter, refuse it.
        if not self._entry_matches_filter(
            self.entries[index]
        ):

            return

        self.current_index = index

        self._updating = True

        try:

            self.listbox.selection_set(
                str(index)
            )

            self.listbox.focus(
                str(index)
            )

            self.listbox.see(
                str(index)
            )

            self.source.delete(
                "1.0",
                "end",
            )

            self.source.insert(
                "1.0",
                self.entries[index]["value"],
            )

            self.source.edit_modified(
                False
            )

        finally:

            self._updating = False

        entry = self.entries[
            index
        ]

        occurrence_text = ""

        if entry["occurrence"] > 1:

            occurrence_text = (
                f"  •  occorrenza "
                f"#{entry['occurrence']}"
            )

        self.index_var.set(
            f"{self._visible_position(index)} / "
            f"{len(self._visible_indices())}"
        )

        self.source_info_var.set(
            f"Key: {entry['key']}"
            f"{occurrence_text}"
            f"    Caratteri: "
            f"{len(entry['value']):,}"
        )

        self._highlight_source()

        self._render_preview()

        self._update_validation()

        self._update_inspector()

    def _visible_position(
        self,
        index: int,
    ) -> int:

        visible = self._visible_indices()

        try:

            return (
                visible.index(index)
                + 1
            )

        except ValueError:

            return 0

    # ========================================================
    # EDITING
    # ========================================================

    def _on_source_modified(
        self,
        _event=None,
    ):

        if self._updating:

            self.source.edit_modified(
                False
            )

            return

        if not self.source.edit_modified():

            return

        self.source.edit_modified(
            False
        )

        self._commit_current()

        self._render_preview()

        self._highlight_source()

        self._update_validation()

        self._update_inspector()

    def _on_source_key_release(
        self,
        _event=None,
    ):

        if self._updating:
            return

        self._commit_current()

        self._render_preview()

        self._highlight_source()

        self._update_validation()

        self._update_inspector()

    def _commit_current(self):

        if not self.entries:
            return

        if not (
            0 <= self.current_index
            < len(self.entries)
        ):
            return

        value = self.source.get(
            "1.0",
            "end-1c",
        )

        entry = self.entries[
            self.current_index
        ]

        if value == entry["value"]:
            return

        entry["value"] = value

        self._dirty = True

        self._update_title()

        self._refresh_list_item(
            self.current_index
        )

        self._update_status_counts()

    # ========================================================
    # SOURCE HIGHLIGHTING
    # ========================================================

    def _highlight_source(self):

        content = self.source.get(
            "1.0",
            "end-1c",
        )

        for tag_name in (
            "src_tag",
            "src_link",
            "src_color",
            "src_size",
            "src_button",
            "src_placeholder",
            "src_escape",
        ):

            self.source.tag_remove(
                tag_name,
                "1.0",
                "end",
            )

        for match in TOKEN_RE.finditer(
            content
        ):

            token = match.group(
                0
            )

            if (
                token.startswith("[")
                and token.endswith("]")
            ):

                tag_name = (
                    "src_placeholder"
                )

            elif BUTTON_GUIDE_RE.match(
                token
            ):

                tag_name = (
                    "src_button"
                )

            elif LINK_OPEN_RE.match(
                token
            ):

                tag_name = (
                    "src_link"
                )

            elif (
                token.startswith("<color=")
                or token == "</color>"
            ):

                tag_name = (
                    "src_color"
                )

            elif (
                token.startswith("<size=")
                or token.startswith("<サイズ=")
                or token == "</size>"
                or token == "</サイズ>"
            ):

                tag_name = (
                    "src_size"
                )

            else:

                tag_name = (
                    "src_tag"
                )

            start = (
                f"1.0 + "
                f"{match.start()} chars"
            )

            end = (
                f"1.0 + "
                f"{match.end()} chars"
            )

            self.source.tag_add(
                tag_name,
                start,
                end,
            )

        for match in re.finditer(
            r"\\[nrt]",
            content,
        ):

            start = (
                f"1.0 + "
                f"{match.start()} chars"
            )

            end = (
                f"1.0 + "
                f"{match.end()} chars"
            )

            self.source.tag_add(
                "src_escape",
                start,
                end,
            )

    # ========================================================
    # PREVIEW
    # ========================================================

    def _render_preview(self):

        if self.current_index < 0:
            return

        raw = self.source.get(
            "1.0",
            "end-1c",
        )

        self._render_source_as_preview(
            raw
        )

    def _render_source_as_preview(
        self,
        raw: str,
    ):

        self.preview.configure(
            state="normal",
            background=self.preview_bg,
            foreground=self.preview_fg,
        )

        self.preview.delete(
            "1.0",
            "end",
        )

        active = []

        cursor = 0

        for match in TOKEN_RE.finditer(
            raw
        ):

            segment = raw[
                cursor:
                match.start()
            ]

            self._insert_rendered_segment(
                segment,
                active,
            )

            token = match.group(
                0
            )

            cursor = match.end()

            m = COLOR_OPEN_RE.match(
                token
            )

            if m:

                active.append(
                    {
                        "kind": "color",
                        "value": m.group(1),
                    }
                )

                continue

            m = SIZE_OPEN_RE.match(
                token
            )

            if m:

                active.append(
                    {
                        "kind": "size",
                        "value": m.group(1),
                    }
                )

                continue

            m = LINK_OPEN_RE.match(
                token
            )

            if m:

                active.append(
                    {
                        "kind": "link",
                        "value": m.group(1),
                    }
                )

                continue

            m = BUTTON_GUIDE_RE.match(
                token
            )

            if m:

                self._insert_button_guide(
                    m.group(1),
                    active,
                )

                continue

            if token in OPEN_SIMPLE:

                active.append(
                    {
                        "kind": OPEN_SIMPLE[token],
                        "value": "",
                    }
                )

                continue

            if token in CLOSE_SIMPLE:

                self._close_active(
                    active,
                    CLOSE_SIMPLE[token],
                )

                continue

            if token in CLOSE_KIND:

                self._close_active(
                    active,
                    CLOSE_KIND[token],
                )

                continue

            if (
                token.startswith("[")
                and token.endswith("]")
            ):

                self._insert_placeholder(
                    token,
                    active,
                )

                continue

        self._insert_rendered_segment(
            raw[cursor:],
            active,
        )

        self.preview.configure(
            state="disabled"
        )

        self.preview.see(
            "1.0"
        )

    @staticmethod
    def _close_active(
        active,
        kind,
    ):

        for i in range(
            len(active) - 1,
            -1,
            -1,
        ):

            if (
                active[i]["kind"]
                == kind
            ):

                del active[i]

                return

    # ========================================================
    # PREVIEW SEGMENTS
    # ========================================================

    def _insert_rendered_segment(
        self,
        raw_segment: str,
        active,
    ):

        if not raw_segment:
            return

        visible = decode_game_escapes(
            raw_segment
        )

        placeholder_re = re.compile(
            r"\[[^\]\r\n]*\]"
        )

        last = 0

        for match in placeholder_re.finditer(
            visible
        ):

            if match.start() > last:

                self._insert_piece(
                    visible[
                        last:
                        match.start()
                    ],
                    active,
                )

            self._insert_placeholder(
                match.group(0),
                active,
            )

            last = match.end()

        if last < len(visible):

            self._insert_piece(
                visible[last:],
                active,
            )

    def _insert_piece(
        self,
        text: str,
        active,
    ):

        if not text:
            return

        self.preview.insert(
            "end",
            text,
            self._preview_tags(
                active
            ),
        )

    def _insert_placeholder(
        self,
        text: str,
        active,
    ):

        tags = list(
            self._preview_tags(
                active
            )
        )

        tags.append(
            "preview_placeholder"
        )

        self.preview.insert(
            "end",
            text,
            tuple(tags),
        )

    def _insert_button_guide(
        self,
        name: str,
        active,
    ):

        display = BUTTON_GUIDE_PREVIEW.get(
            name,
            f"[{name}]",
        )

        tags = list(
            self._preview_tags(
                active
            )
        )

        tags.append(
            "preview_button"
        )

        self.preview.insert(
            "end",
            display,
            tuple(tags),
        )

    # ========================================================
    # PREVIEW FONT
    # ========================================================

    def _get_preview_font(
        self,
        size: int,
        bold: bool,
        underline: bool,
    ) -> Font:

        key = (
            int(size),
            bool(bold),
            bool(underline),
        )

        existing = self._font_cache.get(
            key
        )

        if existing is not None:
            return existing

        font = Font(
            family="Segoe UI",
            size=int(size),
            weight=(
                "bold"
                if bold
                else "normal"
            ),
            underline=underline,
        )

        self._font_cache[
            key
        ] = font

        return font

    def _preview_tags(
        self,
        active,
    ):

        tags = []

        bold = False

        underline = False

        size = int(
            self.preview_base_size
        )

        color = None

        link = None

        for item in active:

            kind = item["kind"]

            if kind == "bold":

                bold = True

            elif kind == "underline":

                underline = True

            elif kind == "color":

                color = item["value"]

            elif kind == "link":

                link = item["value"]

            elif kind == "size":

                raw_value = str(
                    item["value"]
                ).strip()

                try:

                    if raw_value.endswith("%"):

                        percentage = float(
                            raw_value[:-1]
                        )

                        size = max(
                            6,
                            min(
                                96,
                                round(
                                    self.preview_base_size
                                    * percentage
                                    / 100
                                ),
                            ),
                        )

                    else:

                        numeric = float(
                            raw_value
                        )

                        size = max(
                            6,
                            min(
                                96,
                                round(
                                    numeric
                                    * self.preview_size_scale
                                ),
                            ),
                        )

                except ValueError:

                    pass

        font = self._get_preview_font(
            size,
            bold,
            underline,
        )

        font_tag = (
            f"preview_font_"
            f"{size}_"
            f"{int(bold)}_"
            f"{int(underline)}"
        )

        try:

            exists = self.preview.tag_cget(
                font_tag,
                "font",
            )

        except tk.TclError:

            exists = ""

        if not exists:

            self.preview.tag_configure(
                font_tag,
                font=font,
            )

        tags.append(
            font_tag
        )

        if color:

            normalized = color

            if len(normalized) == 3:

                normalized = "".join(
                    c * 2
                    for c in normalized
                )

            color_tag = (
                "preview_color_"
                + normalized.lower()
            )

            try:

                exists = self.preview.tag_cget(
                    color_tag,
                    "foreground",
                )

            except tk.TclError:

                exists = ""

            if not exists:

                self.preview.tag_configure(
                    color_tag,
                    foreground=(
                        f"#{normalized}"
                    ),
                )

            tags.append(
                color_tag
            )

        if link:

            safe = re.sub(
                r"[^A-Za-z0-9_]+",
                "_",
                link,
            )

            link_tag = (
                "preview_link_"
                + safe
            )

            try:

                exists = self.preview.tag_cget(
                    link_tag,
                    "foreground",
                )

            except tk.TclError:

                exists = ""

            if not exists:

                self.preview.tag_configure(
                    link_tag,
                    foreground="#2467A8",
                    underline=True,
                )

            tags.append(
                link_tag
            )

        return tuple(tags)

    # ========================================================
    # BACKGROUND
    # ========================================================

    def choose_preview_background(
        self,
    ):

        result = colorchooser.askcolor(
            initialcolor=self.preview_bg,
            title="Colore sfondo preview",
            parent=self,
        )

        if (
            not result
            or not result[1]
        ):
            return

        self.preview_bg = result[1]

        self.preview_color_label.set(
            f"sfondo: {self.preview_bg}"
        )

        self.preview.configure(
            state="normal",
            background=self.preview_bg,
        )

        self._render_preview()

    # ========================================================
    # VALIDATION
    # ========================================================

    def _update_validation(self):

        raw = self.source.get(
            "1.0",
            "end-1c",
        )

        stack = []

        problems = []

        for match in TOKEN_RE.finditer(
            raw
        ):

            token = match.group(
                0
            )

            if COLOR_OPEN_RE.match(
                token
            ):

                stack.append(
                    "color"
                )

                continue

            if SIZE_OPEN_RE.match(
                token
            ):

                stack.append(
                    "size"
                )

                continue

            if LINK_OPEN_RE.match(
                token
            ):

                stack.append(
                    "link"
                )

                continue

            if BUTTON_GUIDE_RE.match(
                token
            ):

                continue

            if token in OPEN_SIMPLE:

                stack.append(
                    OPEN_SIMPLE[token]
                )

                continue

            if token in CLOSE_SIMPLE:

                self._validate_close(
                    stack,
                    CLOSE_SIMPLE[token],
                    token,
                    problems,
                )

                continue

            if token in CLOSE_KIND:

                self._validate_close(
                    stack,
                    CLOSE_KIND[token],
                    token,
                    problems,
                )

        if stack:

            problems.append(
                "tag non chiusi: "
                + ", ".join(
                    stack
                )
            )

        if problems:

            self.valid_var.set(
                "⚠ "
                + " | ".join(
                    problems[:3]
                )
            )

        else:

            self.valid_var.set(
                "✓ markup bilanciato"
            )

    @staticmethod
    def _validate_close(
        stack,
        kind,
        token,
        problems,
    ):

        if kind not in stack:

            problems.append(
                f"chiusura senza apertura: {token}"
            )

            return

        if stack[-1] != kind:

            problems.append(
                f"ordine tag sospetto: {token}"
            )

            for i in range(
                len(stack) - 1,
                -1,
                -1,
            ):

                if stack[i] == kind:

                    del stack[i]

                    return

        else:

            stack.pop()

    # ========================================================
    # INSPECTOR
    # ========================================================

    def _update_inspector(
        self,
        _event=None,
    ):

        if self.current_index < 0:
            return

        try:

            index = self.source.index(
                "insert"
            )

            line_no, column_no = (
                index.split(".")
            )

            line = self.source.get(
                f"{line_no}.0",
                f"{line_no}.end",
            )

            column = int(
                column_no
            )

            for match in TOKEN_RE.finditer(
                line
            ):

                if (
                    match.start()
                    <= column
                    <= match.end()
                ):

                    token = match.group(
                        0
                    )

                    self.inspector_var.set(
                        (
                            self._describe_token(
                                token
                            )
                            + "\n\n"
                            + f"Riga: {line_no}\n"
                            + f"Colonna: "
                            f"{match.start() + 1}"
                            f"–"
                            f"{match.end()}"
                        )
                    )

                    return

            self.inspector_var.set(
                "Testo normale.\n\n"
                "Posiziona il cursore su "
                "tag, link, ButtonGuide "
                "o placeholder."
            )

        except tk.TclError:
            pass

    @staticmethod
    def _describe_token(
        token: str,
    ) -> str:

        m = COLOR_OPEN_RE.match(
            token
        )

        if m:

            return (
                "COLORE\n"
                f"#{m.group(1)}"
            )

        m = SIZE_OPEN_RE.match(
            token
        )

        if m:

            return (
                "DIMENSIONE TESTO\n"
                f"Valore Unity: {m.group(1)}"
            )

        m = LINK_OPEN_RE.match(
            token
        )

        if m:

            return (
                "LINK / FOCUS\n"
                f"{m.group(1)}"
            )

        m = BUTTON_GUIDE_RE.match(
            token
        )

        if m:

            display = BUTTON_GUIDE_PREVIEW.get(
                m.group(1),
                f"[{m.group(1)}]",
            )

            return (
                "BUTTON GUIDE\n"
                f"ID: {m.group(1)}\n"
                f"Preview: {display}"
            )

        if (
            token.startswith("[")
            and token.endswith("]")
        ):

            return (
                "PLACEHOLDER\n"
                f"{token}"
            )

        if token in OPEN_SIMPLE:

            return (
                "FORMATTAZIONE\n"
                f"{OPEN_SIMPLE[token]}"
            )

        if token in CLOSE_SIMPLE:

            return "CHIUSURA FORMATTAZIONE"

        if token in CLOSE_KIND:

            return (
                "CHIUSURA\n"
                f"{CLOSE_KIND[token]}"
            )

        return (
            "TAG\n"
            f"{token}"
        )

    # ========================================================
    # SEARCH
    # ========================================================

    def find_next(self):

        query = (
            self.search_var
            .get()
            .strip()
        )

        if (
            not query
            or not self.entries
        ):
            return

        folded = query.casefold()

        visible = self._visible_indices()

        if not visible:
            return

        # Search starting after the current visible entry.
        ordered = []

        for index in visible:

            ordered.append(
                index
            )

        try:

            current_position = ordered.index(
                self.current_index
            )

            ordered = (
                ordered[
                    current_position + 1:
                ]
                + ordered[
                    :current_position + 1
                ]
            )

        except ValueError:

            pass

        for index in ordered:

            entry = self.entries[
                index
            ]

            visible_text = decode_game_escapes(
                entry["value"]
            )

            if (
                folded
                in entry["key"].casefold()
                or folded
                in entry["value"].casefold()
                or folded
                in visible_text.casefold()
            ):

                self.select_index(
                    index
                )

                return

        messagebox.showinfo(
            "Trova",
            f"Nessun risultato per:\n{query}",
        )

    # ========================================================
    # NAVIGATION
    # ========================================================

    def previous_entry(self):

        self._commit_current()

        index = self._previous_visible_index()

        if index is not None:

            self.select_index(
                index
            )

    def next_entry(self):

        self._commit_current()

        index = self._next_visible_index()

        if index is not None:

            self.select_index(
                index
            )

    # ========================================================
    # SAVE
    # ========================================================

    def save_file(self):

        if not self.entries:
            return

        self._commit_current()

        if self.translation_path is None:

            messagebox.showwarning(
                "Nessun file",
                "Apri prima una cartella.",
            )

            return

        # Preserve exact entry order.
        # Duplicate keys remain duplicate keys.
        lines = [
            (
                f'{entry["key"]}=='
                f'{entry["value"]}'
            )
            for entry in self.entries
        ]

        try:

            write_text(
                self.translation_path,
                "\n".join(lines)
                + "\n",
            )

        except Exception as exc:

            messagebox.showerror(
                "Errore di salvataggio",
                (
                    "Impossibile salvare:\n\n"
                    f"{exc}"
                ),
            )

            return

        self._dirty = False

        self._update_title()

        self._update_status_counts()

        self.status_var.set(
            self.status_var.get()
            + "  •  salvato"
        )

    # ========================================================
    # TITLE / CLOSE
    # ========================================================

    def _update_title(self):

        if self.loaded_folder is None:

            name = "nessuna cartella"

        else:

            name = str(
                self.loaded_folder
            )

        dirty = (
            " *"
            if self._dirty
            else ""
        )

        self.title(
            f"{APP_TITLE} — "
            f"{name}{dirty}"
        )

    def _close(self):

        if self._closing:
            return

        if self._dirty:

            answer = messagebox.askyesnocancel(
                "Modifiche non salvate",
                (
                    "Ci sono modifiche non salvate.\n\n"
                    "Vuoi salvarle prima di uscire?"
                ),
            )

            if answer is None:
                return

            if answer:

                self.save_file()

                if self._dirty:
                    return

        self._closing = True

        self.destroy()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    app = TranslationEditor()

    app.mainloop()