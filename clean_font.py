import argparse
import re

def clean_file(input_path, output_path):
    # Regex compilate (velocissime)
    pattern_index = re.compile(r"^\s*\[\d+\]")
    pattern_char = re.compile(r"^\s*(\d+\s+)?char data =")

    with open(input_path, "r", encoding="utf-8", errors="replace") as f_in, \
         open(output_path, "w", encoding="utf-8") as f_out:

        for line in f_in:
            # Elimina righe tipo [123]
            if pattern_index.match(line):
                continue

            # Elimina righe tipo char data = 0
            if pattern_char.match(line):
                continue

            # Mantieni tutto il resto
            f_out.write(line)

    print(f"Pulizia completata. File salvato in: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Rimuove righe con [numero] e righe che iniziano con 'char data ='"
    )

    parser.add_argument("input", help="Percorso del file di input")
    parser.add_argument("output", help="Percorso del file di output")

    args = parser.parse_args()

    clean_file(args.input, args.output)


if __name__ == "__main__":
    main()
