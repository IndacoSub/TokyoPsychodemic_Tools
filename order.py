import sys
import os
from PyQt6 import QtWidgets, QtCore, QtGui


class TextEntry:
    def __init__(self, path, text, line_index):
        self.path = path
        self.text = text
        self.line_index = line_index


def find_m_text_in_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        with open(path, "r", encoding="cp1252", errors="replace") as f:
            lines = f.readlines()

    for idx, line in enumerate(lines):
        s = line.strip()
        if s.startswith("1 string m_text ="):
            start = s.find('"')
            end = s.rfind('"')
            if start != -1 and end != -1 and end > start:
                return s[start + 1:end], idx
    return None, None


def update_m_text_in_file(entry: TextEntry):
    try:
        with open(entry.path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        with open(entry.path, "r", encoding="cp1252", errors="replace") as f:
            lines = f.readlines()

    if entry.line_index < 0 or entry.line_index >= len(lines):
        return

    old_line = lines[entry.line_index].rstrip("\n")
    prefix = '1 string m_text = "'
    suffix = '"'
    new_line = prefix + entry.text + suffix

    leading = ""
    for ch in old_line:
        if ch.isspace():
            leading += ch
        else:
            break

    lines[entry.line_index] = leading + new_line + "\n"

    with open(entry.path, "w", encoding="utf-8") as f:
        f.writelines(lines)


class LetterWidget(QtWidgets.QWidget):
    """
    Un widget che mostra una lettera con outline e due frecce per spostarla.
    """
    move_left = QtCore.pyqtSignal(int)
    move_right = QtCore.pyqtSignal(int)
    edit_letter = QtCore.pyqtSignal(int)

    def __init__(self, index, entry: TextEntry):
        super().__init__()
        self.index = index
        self.entry = entry

        layout = QtWidgets.QVBoxLayout(self)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        # Label della lettera
        self.label = QtWidgets.QLabel(entry.text)
        font = QtGui.QFont()
        font.setPointSize(32)
        font.setBold(True)
        self.label.setFont(font)
        self.label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        # Outline
        self.label.setStyleSheet("""
            QLabel {
                border: 2px solid #AAAAAA;
                padding: 10px;
                background-color: #303030;
                color: white;
            }
        """)

        self.label.mouseDoubleClickEvent = self.on_double_click

        layout.addWidget(self.label)

        # Pulsanti ← →
        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_left = QtWidgets.QPushButton("←")
        self.btn_right = QtWidgets.QPushButton("→")

        self.btn_left.clicked.connect(lambda: self.move_left.emit(self.index))
        self.btn_right.clicked.connect(lambda: self.move_right.emit(self.index))

        btn_layout.addWidget(self.btn_left)
        btn_layout.addWidget(self.btn_right)

        layout.addLayout(btn_layout)

    def on_double_click(self, event):
        self.edit_letter.emit(self.index)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TMP Letter Editor (Stable Version)")
        self.folder = None
        self.entries = []

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_layout = QtWidgets.QVBoxLayout(central)

        # Top bar
        top_layout = QtWidgets.QHBoxLayout()
        self.folder_label = QtWidgets.QLabel("No folder selected")
        self.btn_choose = QtWidgets.QPushButton("Choose folder")
        top_layout.addWidget(self.folder_label)
        top_layout.addWidget(self.btn_choose)
        main_layout.addLayout(top_layout)

        self.btn_choose.clicked.connect(self.choose_folder)

        # Scroll area for letters
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        main_layout.addWidget(self.scroll)

        self.letters_container = QtWidgets.QWidget()
        self.letters_layout = QtWidgets.QHBoxLayout(self.letters_container)
        self.letters_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self.scroll.setWidget(self.letters_container)

        # Bottom buttons
        bottom_layout = QtWidgets.QHBoxLayout()
        self.btn_reload = QtWidgets.QPushButton("Reload")
        self.btn_save = QtWidgets.QPushButton("Save")
        bottom_layout.addWidget(self.btn_reload)
        bottom_layout.addWidget(self.btn_save)
        main_layout.addLayout(bottom_layout)

        self.btn_reload.clicked.connect(self.reload_folder)
        self.btn_save.clicked.connect(self.save_changes)

        QtCore.QTimer.singleShot(0, self.showMaximized)

    def choose_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select folder with TMP txt files")
        if folder:
            self.folder = folder
            self.folder_label.setText(folder)
            self.load_folder()

    def reload_folder(self):
        if not self.folder:
            QtWidgets.QMessageBox.warning(self, "No folder", "Select a folder first.")
            return
        self.load_folder()

    def load_folder(self):
        self.entries = []
        self.clear_letters()

        # 1) Leggi l'ordine salvato
        saved_order = self.load_order_file()

        # 2) Leggi tutti i file .txt
        found = {}
        for name in os.listdir(self.folder):
            if not name.lower().endswith(".txt"):
                continue
            path = os.path.join(self.folder, name)
            text, idx = find_m_text_in_file(path)
            if text is not None:
                found[name] = TextEntry(path, text, idx)

        # 3) Se esiste order.txt, usa quell’ordine
        if saved_order:
            for name in saved_order:
                if name in found:
                    self.entries.append(found[name])

            # Aggiungi eventuali file nuovi non presenti in order.txt
            for name, entry in found.items():
                if entry not in self.entries:
                    self.entries.append(entry)
        else:
            # Nessun order.txt → ordine alfabetico
            for name in sorted(found.keys()):
                self.entries.append(found[name])

        self.rebuild_letters()

    def clear_letters(self):
        while self.letters_layout.count():
            item = self.letters_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def rebuild_letters(self):
        self.clear_letters()
        for i, entry in enumerate(self.entries):
            w = LetterWidget(i, entry)
            w.move_left.connect(self.move_left)
            w.move_right.connect(self.move_right)
            w.edit_letter.connect(self.edit_letter)
            self.letters_layout.addWidget(w)

    def move_left(self, index):
        if index > 0:
            self.entries[index - 1], self.entries[index] = self.entries[index], self.entries[index - 1]
            self.rebuild_letters()

    def move_right(self, index):
        if index < len(self.entries) - 1:
            self.entries[index + 1], self.entries[index] = self.entries[index], self.entries[index + 1]
            self.rebuild_letters()

    def edit_letter(self, index):
        entry = self.entries[index]
        new_text, ok = QtWidgets.QInputDialog.getText(
            self,
            "Edit letter",
            f"New text for {os.path.basename(entry.path)}:",
            text=entry.text
        )
        if ok and new_text.strip():
            entry.text = new_text.strip()
            self.rebuild_letters()

    def save_changes(self):
        for entry in self.entries:
            update_m_text_in_file(entry)

        order_path = os.path.join(self.folder, "order.txt")
        with open(order_path, "w", encoding="utf-8") as f:
            for idx, entry in enumerate(self.entries):
                f.write(f"{idx}\t{os.path.basename(entry.path)}\t{entry.text}\n")

        QtWidgets.QMessageBox.information(self, "Saved", "Files and order.txt saved.")

    def load_order_file(self):
        order_path = os.path.join(self.folder, "order.txt")
        if not os.path.exists(order_path):
            return None

        order = []
        with open(order_path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 2:
                    order.append(parts[1])  # nome file
        return order


def main():
    app = QtWidgets.QApplication(sys.argv)


    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
