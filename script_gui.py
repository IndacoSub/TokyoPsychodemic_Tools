import sys
import os
import subprocess
import time

from PyQt6 import QtWidgets, QtCore, QtGui


# ============================================================
# DIRECTORY BASE DEL PROGRAMMA
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

TXT_PATH = os.path.join(
    BASE_DIR,
    "script_base.txt"
)

SCRIPT_PATH = os.path.join(
    BASE_DIR,
    "script.py"
)

LAUNCH_PATH = os.path.join(
    BASE_DIR,
    "BUILD.bat"
)

AUTOGEN_START = "# === AUTOGEN START ==="
AUTOGEN_END = "# === AUTOGEN END ==="


# ============================================================
# PARSER
# ============================================================

def decode_entry(raw):
    line = raw.replace("\n", " ").strip()
    data = {"raw": raw.strip()}

    def extract(tag):
        key = f"{tag}("

        if key not in line:
            return None

        start = line.index(key) + len(key)

        if start >= len(line):
            return None

        if line[start] in ['"', "'"]:
            quote = line[start]
            start += 1

            try:
                end = line.index(
                    quote,
                    start
                )
            except ValueError:
                return None

        else:
            try:
                end = line.index(
                    ")",
                    start
                )
            except ValueError:
                return None

        return line[start:end]

    data["ga"] = extract("ga")
    data["txt"] = extract("txt")
    data["png"] = extract("png")
    data["pid"] = extract("pid")
    data["fid"] = extract("fid")
    data["kind"] = extract("kind")

    # ========================================================
    # NOME VISUALIZZATO
    # ========================================================

    if data["txt"]:
        data["name"] = data["txt"]

    elif data["png"]:
        data["name"] = data["png"]

    elif data["ga"]:
        ga_value = (
            data["ga"]
            .replace("\\", "/")
            .rstrip("/")
        )

        data["name"] = os.path.basename(
            ga_value
        )

        if not data["name"]:
            data["name"] = ga_value

    else:
        data["name"] = "Unknown"

    return data


def parse_config_txt(path):
    roots = {}
    current_root = None
    current_section = None

    if not os.path.isfile(path):
        return roots

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        buffer = None

        for raw in f:
            line = raw.strip()

            if not line:
                continue

            if (
                line.startswith("-")
                or line.startswith("_")
                or line.startswith("/")
            ):
                continue

            # ====================================================
            # ROOT
            # ====================================================

            if line.startswith("@ROOT:"):
                current_root = line[len("@ROOT:"):].strip()

                if current_root not in roots:
                    roots[current_root] = {}

                current_section = None
                buffer = None

                continue

            # ====================================================
            # SECTION
            # ====================================================

            if line.startswith("#"):
                current_section = line[1:].strip()

                if current_root is None:
                    current_root = "Default"

                    if current_root not in roots:
                        roots[current_root] = {}

                if current_section not in roots[current_root]:
                    roots[current_root][current_section] = []

                buffer = None

                continue

            # ====================================================
            # ENTRY
            # ====================================================

            if line.startswith("[ga("):
                buffer = raw

                if (
                    "]," in line
                    or line.endswith("]")
                ):
                    entry = decode_entry(buffer)

                    if current_root is None:
                        current_root = "Default"

                        if current_root not in roots:
                            roots[current_root] = {}

                    if current_section is None:
                        current_section = "Misc"

                        if current_section not in roots[current_root]:
                            roots[current_root][current_section] = []

                    roots[current_root][current_section].append(
                        entry
                    )

                    buffer = None

                continue

            # ====================================================
            # ENTRY MULTILINE
            # ====================================================

            if buffer is not None:
                buffer += raw

                if (
                    "]," in line
                    or line.endswith("]")
                ):
                    entry = decode_entry(buffer)

                    if current_root is None:
                        current_root = "Default"

                        if current_root not in roots:
                            roots[current_root] = {}

                    if current_section is None:
                        current_section = "Misc"

                        if current_section not in roots[current_root]:
                            roots[current_root][current_section] = []

                    roots[current_root][current_section].append(
                        entry
                    )

                    buffer = None

    return roots


# ============================================================
# TREE ITEM
# ============================================================

class TreeItem(QtWidgets.QTreeWidgetItem):

    def __init__(
        self,
        *args,
        item_type="root",
        entry=None
    ):
        super().__init__(*args)

        self.item_type = item_type
        self.entry = entry

        self.setFlags(
            self.flags()
            | QtCore.Qt.ItemFlag.ItemIsUserCheckable
        )

        self.setCheckState(
            0,
            QtCore.Qt.CheckState.Unchecked
        )


# ============================================================
# LOG WINDOW
# ============================================================

class LogWindow(QtWidgets.QWidget):

    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            "Script Output"
        )

        self.resize(
            800,
            600
        )

        layout = QtWidgets.QVBoxLayout(
            self
        )

        self.text = QtWidgets.QTextEdit()
        self.text.setReadOnly(True)

        layout.addWidget(
            self.text
        )

    def append(self, msg: str):
        self.text.append(msg)


# ============================================================
# MAIN WINDOW
# ============================================================

class MainWindow(QtWidgets.QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            "Config GUI"
        )

        self.roots = parse_config_txt(
            TXT_PATH
        )

        central = QtWidgets.QWidget()

        self.setCentralWidget(
            central
        )

        layout = QtWidgets.QVBoxLayout(
            central
        )

        # ========================================================
        # TREE
        # ========================================================

        self.tree = QtWidgets.QTreeWidget()

        self.tree.setHeaderLabels(
            ["Sections / Files"]
        )

        self.tree.setColumnCount(
            1
        )

        self.tree.itemChanged.connect(
            self.on_item_changed
        )

        layout.addWidget(
            self.tree
        )

        # ========================================================
        # BUTTONS
        # ========================================================

        btns = QtWidgets.QHBoxLayout()

        layout.addLayout(
            btns
        )

        self.btn_reload = QtWidgets.QPushButton(
            "Reload TXT"
        )

        self.btn_enable_all = QtWidgets.QPushButton(
            "Enable All"
        )

        self.btn_disable_all = QtWidgets.QPushButton(
            "Disable All"
        )

        self.btn_generate = QtWidgets.QPushButton(
            "Generate script.py"
        )

        self.btn_run = QtWidgets.QPushButton(
            "Run BUILD.bat"
        )

        btns.addWidget(
            self.btn_reload
        )

        btns.addWidget(
            self.btn_enable_all
        )

        btns.addWidget(
            self.btn_disable_all
        )

        btns.addWidget(
            self.btn_generate
        )

        btns.addWidget(
            self.btn_run
        )

        self.btn_reload.clicked.connect(
            self.reload_txt
        )

        self.btn_enable_all.clicked.connect(
            lambda:
            self.set_all(
                QtCore.Qt.CheckState.Checked
            )
        )

        self.btn_disable_all.clicked.connect(
            lambda:
            self.set_all(
                QtCore.Qt.CheckState.Unchecked
            )
        )

        self.btn_generate.clicked.connect(
            self.generate_script
        )

        self.btn_run.clicked.connect(
            self.run_script
        )

        self.populate_tree()

        QtCore.QTimer.singleShot(
            0,
            self.showMaximized
        )

    # ============================================================
    # POPULATE TREE
    # ============================================================

    def populate_tree(self):
        self.tree.clear()

        for root_name, sections in self.roots.items():

            root_item = TreeItem(
                [root_name],
                item_type="root"
            )

            self.tree.addTopLevelItem(
                root_item
            )

            for section_name, entries in sections.items():

                section_item = TreeItem(
                    [section_name],
                    item_type="section"
                )

                root_item.addChild(
                    section_item
                )

                for entry in entries:

                    label = (
                        f"{entry['name']}  "
                        f"(PID: {entry['pid']})"
                    )

                    entry_item = TreeItem(
                        [label],
                        item_type="entry",
                        entry=entry
                    )

                    section_item.addChild(
                        entry_item
                    )

        self.tree.setItemsExpandable(
            True
        )

        self.tree.setExpandsOnDoubleClick(
            True
        )

        self.tree.collapseAll()

        self.set_all(
            QtCore.Qt.CheckState.Unchecked
        )

    # ============================================================
    # RELOAD
    # ============================================================

    def reload_txt(self):
        self.roots = parse_config_txt(
            TXT_PATH
        )

        self.populate_tree()

    # ============================================================
    # TREE CHANGE
    # ============================================================

    def on_item_changed(
        self,
        item,
        column
    ):
        if column != 0:
            return

        state = item.checkState(
            0
        )

        self.propagate_down(
            item,
            state
        )

        self.update_parents(
            item
        )

    # ============================================================
    # PROPAGATE DOWN
    # ============================================================

    def propagate_down(
        self,
        item,
        state
    ):
        self.tree.blockSignals(
            True
        )

        try:
            for i in range(
                item.childCount()
            ):
                child = item.child(i)

                child.setCheckState(
                    0,
                    state
                )

                self.propagate_down(
                    child,
                    state
                )

        finally:
            self.tree.blockSignals(
                False
            )

    # ============================================================
    # UPDATE PARENTS
    # ============================================================

    def update_parents(
        self,
        item
    ):
        parent = item.parent()

        while parent is not None:

            states = {
                parent.child(i).checkState(0)
                for i in range(parent.childCount())
            }

            self.tree.blockSignals(
                True
            )

            try:
                if len(states) == 1:

                    parent.setCheckState(
                        0,
                        states.pop()
                    )

                else:

                    parent.setCheckState(
                        0,
                        QtCore.Qt.CheckState.PartiallyChecked
                    )

            finally:
                self.tree.blockSignals(
                    False
                )

            parent = parent.parent()

    # ============================================================
    # SET ALL
    # ============================================================

    def set_all(
        self,
        state
    ):
        self.tree.blockSignals(
            True
        )

        try:
            for i in range(
                self.tree.topLevelItemCount()
            ):

                root = self.tree.topLevelItem(
                    i
                )

                root.setCheckState(
                    0,
                    state
                )

                self.propagate_down(
                    root,
                    state
                )

        finally:
            self.tree.blockSignals(
                False
            )

    # ============================================================
    # COLLECT ENABLED
    # ============================================================

    def collect_enabled(self):

        enabled = []

        for i in range(
            self.tree.topLevelItemCount()
        ):

            root = self.tree.topLevelItem(
                i
            )

            if (
                root.checkState(0)
                == QtCore.Qt.CheckState.Unchecked
            ):
                continue

            for j in range(
                root.childCount()
            ):

                section = root.child(
                    j
                )

                if (
                    section.checkState(0)
                    == QtCore.Qt.CheckState.Unchecked
                ):
                    continue

                for k in range(
                    section.childCount()
                ):

                    entry_item = section.child(
                        k
                    )

                    if (
                        entry_item.checkState(0)
                        == QtCore.Qt.CheckState.Checked
                        and entry_item.entry
                    ):
                        enabled.append(
                            entry_item.entry
                        )

        return enabled

    # ============================================================
    # GENERATE SCRIPT
    # ============================================================

    def generate_script(self):

        enabled = self.collect_enabled()

        if not os.path.isfile(
            SCRIPT_PATH
        ):
            QtWidgets.QMessageBox.warning(
                self,
                "Error",
                f"script.py non trovato:\n\n{SCRIPT_PATH}"
            )

            return

        try:
            with open(
                SCRIPT_PATH,
                "r",
                encoding="utf-8"
            ) as f:
                content = f.read()

        except OSError as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Errore apertura",
                f"Impossibile leggere script.py:\n\n{e}"
            )

            return

        start = content.find(
            AUTOGEN_START
        )

        end = content.find(
            AUTOGEN_END
        )

        if (
            start == -1
            or end == -1
            or end < start
        ):
            QtWidgets.QMessageBox.warning(
                self,
                "Error",
                "Markers AUTOGEN mancanti "
                "o in ordine sbagliato."
            )

            return

        before = content[
            :start + len(AUTOGEN_START)
        ]

        after = content[
            end:
        ]

        block = self.build_autogen_block(
            enabled
        )

        new_content = (
            before
            + "\n\n"
            + block
            + "\n\n"
            + after
        )

        try:
            with open(
                SCRIPT_PATH,
                "w",
                encoding="utf-8"
            ) as f:
                f.write(
                    new_content
                )

        except OSError as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Errore scrittura",
                f"Impossibile scrivere script.py:\n\n{e}"
            )

            return

        QtWidgets.QMessageBox.information(
            self,
            "OK",
            "script.py rigenerato."
        )

    # ============================================================
    # AUTOGEN
    # ============================================================

    def build_autogen_block(
        self,
        enabled
    ):
        lines = []

        lines.append(
            "# AUTOGEN main + run_program "
            "(generated by GUI)"
        )

        lines.append(
            "    files = ["
        )

        for e in enabled:

            # ====================================================
            # RICOSTRUZIONE ENTRY
            # ====================================================
            #
            # L'ordine degli argomenti generati è SEMPRE:
            #
            #     GA
            #     PNG/TXT
            #     PID
            #     FID
            #     KIND
            #
            # Se FID non è presente nella configurazione,
            # viene inserito automaticamente:
            #
            #     fid("-")
            #
            # "-" significa:
            #     FileID non specificato.
            #
            # Questo segnaposto serve esclusivamente a mantenere
            # la posizione corretta di FileKind negli argomenti
            # della CLI di NewUAFGJ.
            # ====================================================

            parts = []

            if e.get("ga"):
                parts.append(
                    f'ga("{e["ga"]}")'
                )

            if e.get("txt"):
                parts.append(
                    f'txt("{e["txt"]}")'
                )

            if e.get("png"):
                parts.append(
                    f'png("{e["png"]}")'
                )

            if e.get("pid"):
                parts.append(
                    f'pid("{e["pid"]}")'
                )

                # ====================================================
                # FILEID
                # ====================================================
                #
                # Se il FileID è presente, lo manteniamo.
                #
                # Se manca, inseriamo automaticamente "-".
                #
                # NON usiamo fid("0") come default.
                # "0" è un vero FileID.
                # "-" significa invece "non specificato".
                # ====================================================

                if e.get("fid") is not None and str(e["fid"]).strip() != "":
                    parts.append(
                        f'fid("{e["fid"]}")'
                    )
                else:
                    parts.append(
                        'fid("-")'
                    )

            if e.get("kind"):
                parts.append(
                    f'kind("{e["kind"]}")'
                )

            entry_text = (
                "        ["
                + ", ".join(parts)
                + "],"
            )

            lines.append(
                entry_text
            )

        lines.append(
            "    ]"
        )

        lines.append("")

        return "\n".join(
            lines
        )

    # ============================================================
    # RUN BUILD.BAT
    # ============================================================

    def run_script(self):

        # --------------------------------------------------------
        # Controllo esistenza BUILD.bat
        # --------------------------------------------------------

        if not os.path.isfile(
            LAUNCH_PATH
        ):

            QtWidgets.QMessageBox.warning(
                self,
                "Errore",
                "BUILD.bat non trovato:\n\n"
                f"{LAUNCH_PATH}"
            )

            return

        # --------------------------------------------------------
        # Directory corretta
        # --------------------------------------------------------

        launch = os.path.abspath(
            LAUNCH_PATH
        )

        launch_dir = os.path.dirname(
            launch
        )

        # --------------------------------------------------------
        # Log window
        # --------------------------------------------------------

        self.log_window = LogWindow()

        self.log_window.append(
            f"BUILD: {launch}"
        )

        self.log_window.append(
            f"CWD: {launch_dir}"
        )

        self.log_window.show()

        # ========================================================
        # WORKER
        # ========================================================

        class Worker(QtCore.QObject):

            finished = QtCore.pyqtSignal()
            output = QtCore.pyqtSignal(str)

            def run(self):

                try:
                    # ------------------------------------------------
                    # COMANDO
                    # ------------------------------------------------

                    cmd = [
                        "cmd.exe",
                        "/d",
                        "/c",
                        "call",
                        launch
                    ]

                    self.output.emit(
                        "Avvio BUILD.bat..."
                    )

                    self.output.emit(
                        "Comando: "
                        + subprocess.list2cmdline(
                            cmd
                        )
                    )

                    # ------------------------------------------------
                    # START TIMER
                    # ------------------------------------------------
                    #
                    # Il timer parte immediatamente prima dell'avvio
                    # effettivo di BUILD.bat.
                    #

                    start_time = time.perf_counter()

                    # ------------------------------------------------
                    # CREATE NEW CONSOLE
                    # ------------------------------------------------

                    process = subprocess.Popen(
                        cmd,
                        cwd=launch_dir,
                        creationflags=subprocess.CREATE_NEW_CONSOLE
                    )

                    # ------------------------------------------------
                    # WAIT
                    # ------------------------------------------------

                    return_code = process.wait()

                    # ------------------------------------------------
                    # STOP TIMER
                    # ------------------------------------------------
                    #
                    # Il tempo comprende tutto ciò che BUILD.bat
                    # esegue, compreso run_program() e quindi
                    # tutte le compilazioni.
                    #

                    elapsed_seconds = (
                        time.perf_counter()
                        - start_time
                    )

                    # ------------------------------------------------
                    # CONVERSIONE TEMPO
                    # ------------------------------------------------

                    total_seconds = int(
                        elapsed_seconds
                    )

                    minutes = (
                        total_seconds // 60
                    )

                    seconds = (
                        total_seconds % 60
                    )

                    milliseconds = int(
                        (
                            elapsed_seconds
                            - total_seconds
                        ) * 1000
                    )

                    # ------------------------------------------------
                    # OUTPUT
                    # ------------------------------------------------

                    self.output.emit(
                        f"BUILD.bat terminato. "
                        f"Exit code: {return_code}"
                    )

                    self.output.emit(
                        f"Tempo totale compilazione: "
                        f"{minutes} minuti e "
                        f"{seconds} secondi."
                    )

                    self.output.emit(
                        f"Tempo preciso: "
                        f"{minutes:02d}:{seconds:02d}."
                        f"{milliseconds:03d}"
                    )

                except Exception as e:

                    self.output.emit(
                        "ERRORE avvio BUILD.bat:"
                    )

                    self.output.emit(
                        str(e)
                    )

                finally:
                    self.finished.emit()

        # ========================================================
        # THREAD
        # ========================================================

        self.worker = Worker()

        self.thread = QtCore.QThread()

        self.worker.output.connect(
            self.log_window.append
        )

        self.worker.finished.connect(
            self.thread.quit
        )

        self.worker.moveToThread(
            self.thread
        )

        self.thread.started.connect(
            self.worker.run
        )

        self.thread.start()


# ============================================================
# MAIN
# ============================================================

def main():

    app = QtWidgets.QApplication(
        sys.argv
    )

    w = MainWindow()

    w.show()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":
    main()
