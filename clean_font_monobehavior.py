#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import re
from pathlib import Path
from shutil import copy2

def leading_spaces(s: str) -> int:
    return len(s) - len(s.lstrip(' '))

def process_lines(lines):
    out = []
    i = 0
    n = len(lines)

    # Regex per array
    header_re = re.compile(r'^(\s*\d+\s+Array Array\s*\()\s*\d+\s*items\)\s*$')
    size_re = re.compile(r'^(\s*0\s+int\s+size\s*=\s*)\d+\s*$')

    # Regex per characterSequence
    charseq_re = re.compile(r'^(\s*\d+\s+string\s+characterSequence\s*=\s*).*$')

    # Whitelist: se la riga precedente contiene uno di questi, NON toccare l'array
    whitelist = [
        "vector m_AtlasTextures",
        "TMP_FontWeightPair m_FontWeightTable"
    ]

    while i < n:
        line = lines[i]

        # --- RESET characterSequence ---
        m_char = charseq_re.match(line)
        if m_char:
            out.append(m_char.group(1) + '""\n')
            i += 1
            continue

        # --- ARRAY HEADER ---
        m = header_re.match(line)
        if not m:
            out.append(line)
            i += 1
            continue

        # Controllo whitelist: guardo la riga precedente
        prev_line = lines[i-1] if i > 0 else ""

        if any(w in prev_line for w in whitelist):
            # Array whitelisted → NON toccare
            out.append(line)
            i += 1
            continue

        # Array NON whitelisted → svuotare
        indent = leading_spaces(line)

        # Sostituisco items con 0
        new_header = re.sub(r'\(\s*\d+\s*items\)', '(0 items)', line)
        out.append(new_header.rstrip('\n') + '\n')

        # Cerco la riga size
        j = i + 1
        size_written = False

        while j < n and leading_spaces(lines[j]) > indent:
            ms = size_re.match(lines[j])
            if ms and not size_written:
                out.append(ms.group(1) + '0\n')
                size_written = True
            j += 1

        # Salto tutto il contenuto dell’array
        i = j

    return out

def main():
    if len(sys.argv) < 3:
        print("Uso: python rimuovi_array.py input.txt output.txt")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    if not input_path.exists():
        print(f"File non trovato: {input_path}")
        sys.exit(1)

    backup_path = input_path.with_suffix(input_path.suffix + '.bak')
    copy2(input_path, backup_path)
    print(f"Backup creato: {backup_path}")

    with input_path.open('r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = process_lines(lines)

    with output_path.open('w', encoding='utf-8') as f:
        f.writelines(new_lines)

    print(f"File processato salvato in: {output_path}")

if __name__ == '__main__':
    main()
