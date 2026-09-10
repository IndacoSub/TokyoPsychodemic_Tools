#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path


def escape_unity_string(text: str) -> str:
    """
    Converte il contenuto del file estratto con il plugin
    nel formato usato da UABEA Export Dump.
    """

    # Prima raddoppiamo i backslash già presenti nel testo.
    text = text.replace("\\", "\\\\")

    # Normalizziamo i newline reali.
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # I newline reali diventano \n nel dump Unity.
    text = text.replace("\n", "\\n")

    return text


def convert(input_file: Path, output_file: Path, asset_name: str) -> None:
    # newline="" è importante per non far modificare i newline a Python.
    with input_file.open("r", encoding="utf-8", newline="") as f:
        source = f.read()

    escaped_script = escape_unity_string(source)

    # UABEA usa CRLF nel dump.
    result = (
        "0 TextAsset Base\r\n"
        f' 1 string m_Name = "{asset_name}"\r\n'
        f' 1 string m_Script = "{escaped_script}"\r\n'
    )

    with output_file.open("w", encoding="utf-8", newline="") as f:
        f.write(result)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Converte un TextAsset estratto con il plugin "
            "nel formato Export Dump di UABEA."
        )
    )

    parser.add_argument(
        "input",
        type=Path,
        help="File estratto con il plugin"
    )

    parser.add_argument(
        "output",
        type=Path,
        help="File di output in formato UABEA Export Dump"
    )

    parser.add_argument(
        "name",
        nargs="?",
        default=None,
        help="Nome del TextAsset"
    )

    args = parser.parse_args()

    if not args.input.is_file():
        print(f"ERRORE: file di input non trovato: {args.input}")
        raise SystemExit(1)

    # Se il nome non viene specificato, usa il nome del file senza estensione.
    asset_name = args.name if args.name is not None else args.input.stem

    try:
        convert(args.input, args.output, asset_name)
    except Exception as e:
        print(f"ERRORE durante la conversione: {e}")
        raise SystemExit(1)

    print(f"Creato: {args.output}")
    print(f'TextAsset: "{asset_name}"')


if __name__ == "__main__":
    main()