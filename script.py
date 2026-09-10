import subprocess
import os
import re
import sys
import shutil
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================================================
# PATH CONFIGURATION
# ============================================================

script_dir = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
gameloc = "F:/SteamLibrary/steamapps/common/東京サイコデミック/TOKYO_PSYCHODEMIC_Data"
program = "C:/Users/Volca/Documents/GitHub/NewUAFGJ/NewUAFGJ/bin/Release/net8.0/NewUAFGJ.exe"
compressor_program = "C:/Users/Volca/Documents/GitHub/UnityBundleCompressor/UnityBundleCompressor/bin/Release/net8.0/UnityBundleCompressor.exe"
dll_patcher_program = "C:/Users/Volca/Documents/GitHub/UnityDLLPatcher/DllPatcher/bin/Release/net10.0/DllPatcher.exe"
targeted_image_patcher_program = "C:/Users/Volca/Documents/GitHub/FontReplacementHunter/bin/Release/net10.0/FontReplacementHunter.exe"
before_dir = os.path.join(script_dir, "before").replace("\\", "/")
after_dir = os.path.join(script_dir, "after").replace("\\", "/")

ENABLE_COMPRESSION = True
NEEDS_DLL_PATCHES = True
NEEDS_FRH = True

# ============================================================
# DLL CONFIGURATION
# ============================================================

DLL_RELATIVE_PATH = "Managed/Assembly-CSharp.dll"
DLL_PATCHED_RELATIVE_PATH = "Managed/Assembly-CSharp.ENGLISHONLY.dll"
DLL_ORIGINAL_RELATIVE_PATH = "Managed/Assembly-CSharp.dll.ORIGINAL"

# ============================================================
# FORCE UTF-8 OUTPUT ON WINDOWS
# ============================================================

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass


# ============================================================
# OPTIONAL TQDM
# ============================================================

USE_TQDM = True

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None
    if USE_TQDM:
        print("[TQDM] tqdm non installato. Falling back to normal NewUAFGJ output.")
        USE_TQDM = False


# ============================================================
# COMPRESSION CONFIGURATION
# ============================================================

MAX_CONCURRENT_COMPRESSION = 8

CONDITIONAL_SAME_FILE_PAUSE = 1.0
SAVE_FULL_COMPRESSION_LOGS = True
COMPRESSION_LOG_DIR = os.path.join(script_dir, "compress_logs").replace("\\", "/")
PRINT_FULL_COMPRESSOR_LOG = False
REQUIRE_FULL_VALIDATION_MARKERS = True
FAILED_LOG_TAIL_LINES = 80
COMPRESSION_CONSOLE_LOCK = threading.Lock()

# ============================================================
# REGISTRIES
# ============================================================

GA_FILES = set()
DLL_PATCH_REQUESTS = set()


# ============================================================
# ARGUMENT HELPERS
# ============================================================

def is_path_id(arg):
    return bool(re.fullmatch(r"-?\d+", str(arg).strip()))


def is_kind(arg):
    known_kinds = {
        "MONOBEHAVIOUR_TEXT",
        "MONOBEHAVIOUR_TEXT_CHECKED",
        "MONOBEHAVIOUR_FONT",
        "MONOBEHAVIOUR_FONT_CHECKED",
        "MONOBEHAVIOUR_FULL",
        "MONOBEHAVIOUR_FULL_CHECKED",
        "FONT",
        "FONT_CHECKED",
        "GAMEOBJECT_FULL",
        "GAMEOBJECT_FULL_CHECKED",
        "DLL_PATCH",
    }
    return str(arg).strip().upper() in known_kinds


def kind(arg):
    return str(arg).strip()


def is_dll_patch_operation(args):
    if not isinstance(args, (list, tuple)):
        return False
    return any(str(item).strip().upper() == "DLL_PATCH" for item in args)


# ============================================================
# PATH HELPERS
# ============================================================

def gameasset(arg):
    return os.path.join(gameloc, arg).replace("\\", "/")


def ga(arg):
    path = gameasset(arg)
    GA_FILES.add(os.path.abspath(path))
    return path


def png(arg):
    return os.path.join(script_dir, arg + ".png").replace("\\", "/")


def txt(arg):
    return os.path.join(script_dir, arg + ".txt").replace("\\", "/")


def pid(arg):
    return str(arg)


def fid(arg):
    return str(arg)


def dll_path(relative_path):
    return os.path.abspath(os.path.join(gameloc, relative_path))


# ============================================================
# FILE LOCK CHECK
# ============================================================

def wait_for_file_idle(file_path, attempts=20, delay=0.25):
    file_path = os.path.abspath(file_path)
    for attempt in range(1, attempts + 1):
        try:
            with open(file_path, "rb+") as f:
                f.flush()
            return True
        except (PermissionError, OSError):
            if attempt >= attempts:
                return False
            time.sleep(delay)
    return False


# ============================================================
# DLL STATE INITIALIZATION
# ============================================================

def initialize_dll_state():
    current = dll_path(DLL_RELATIVE_PATH)
    original = dll_path(DLL_ORIGINAL_RELATIVE_PATH)
    patched = dll_path(DLL_PATCHED_RELATIVE_PATH)

    if not os.path.isfile(current):
        raise FileNotFoundError(f"Assembly-CSharp.dll non trovato:\n{current}")

    if not os.path.isfile(original):
        if os.path.isfile(patched):
            raise RuntimeError("Manca Assembly-CSharp.dll.ORIGINAL ma esiste già Assembly-CSharp.ENGLISHONLY.dll.")
        print("[DLL] ORIGINAL backup not found.")
        print("[DLL] Creating ORIGINAL backup from current DLL...")
        shutil.copy2(current, original)
        print("[DLL] ORIGINAL backup created:")
        print(f"    {original}")
    else:
        print("[DLL] ORIGINAL backup found:")
        print(f"    {original}")

    print("[DLL] Restoring clean Assembly-CSharp.dll...")
    shutil.copy2(original, current)
    print("[DLL] Clean DLL restored.")


# ============================================================
# DLL PATCHER
# ============================================================

def run_dll_patcher():
    patcher = os.path.abspath(dll_patcher_program)
    current = dll_path(DLL_RELATIVE_PATH)
    original = dll_path(DLL_ORIGINAL_RELATIVE_PATH)
    patched = dll_path(DLL_PATCHED_RELATIVE_PATH)

    if not os.path.isfile(patcher):
        raise FileNotFoundError(f"DllPatcher.exe non trovato:\n{patcher}")

    if not os.path.isfile(current):
        raise FileNotFoundError(f"Assembly-CSharp.dll non trovato:\n{current}")

    if not os.path.isfile(original):
        raise FileNotFoundError(f"Assembly-CSharp.dll.ORIGINAL non trovato:\n{original}")

    if os.path.isfile(patched):
        print("[DLL] Removing previous patch output...")
        os.remove(patched)

    print("[DLL] ==========================================")
    print("[DLL] Running DllPatcher...")
    print(f"[DLL] {patcher}")

    result = subprocess.run([patcher], cwd=os.path.dirname(patcher), check=False)

    if result.returncode != 0:
        raise RuntimeError(f"DllPatcher.exe ha restituito exit code {result.returncode}.")

    if not os.path.isfile(patched):
        raise RuntimeError("DllPatcher.exe è terminato senza errori, ma Assembly-CSharp.ENGLISHONLY.dll non è stato creato.")

    patched_size = os.path.getsize(patched)

    if patched_size <= 0:
        raise RuntimeError("Assembly-CSharp.ENGLISHONLY.dll è vuoto.")

    print("[DLL] Installing patched Assembly-CSharp.dll...")
    shutil.copy2(patched, current)

    installed_size = os.path.getsize(current)

    if installed_size != patched_size:
        raise RuntimeError("Dimensione del DLL installato diversa dal DLL patchato.")

    print("[DLL] English-only DLL installed.")
    print(f"[DLL] SIZE: {installed_size:,} bytes")
    print("[DLL] Removing intermediate patch file...")
    os.remove(patched)
    print("[DLL] ==========================================")
    print("[DLL] DLL patch completed successfully.")


# ============================================================
# TARGETED IMAGE PATCHER
# ============================================================

def run_targeted_image_patcher(files, target_bundle_relative_path, target_pids):
    print("[TARGETED IMAGE] ==========================================")

    target_bundle_path = os.path.join(gameloc, target_bundle_relative_path).replace("\\", "/")

    print("[TARGETED IMAGE] Bundle:")
    print(f"    {target_bundle_path}")

    print("[TARGETED IMAGE] Required TMP PathIDs:")
    for pid in target_pids:
        print(f"    {pid}")

    if len(target_pids) < 1:
        print("[TARGETED IMAGE] ERROR: at least 1 TMP PathID is required.")
        print("[TARGETED IMAGE] Patcher will NOT run.")
        print("[TARGETED IMAGE] ==========================================")
        return False

    normalized_target_bundle = target_bundle_path.lower()
    normalized_target_pids = [str(pid) for pid in target_pids]

    found_pids = []

    for file_info in files:
        if not isinstance(file_info, (list, tuple)):
            continue

        if len(file_info) < 3:
            continue

        bundle_path = str(file_info[0]).replace("\\", "/").lower()
        path_id = str(file_info[2])

        if bundle_path != normalized_target_bundle:
            continue

        if path_id in normalized_target_pids and path_id not in found_pids:
            found_pids.append(path_id)

    print("[TARGETED IMAGE] Found TMP PathIDs:")
    for pid in found_pids:
        print(f"    {pid}")

    missing_pids = [pid for pid in normalized_target_pids if pid not in found_pids]

    if missing_pids:
        print("[TARGETED IMAGE] Condition NOT satisfied.")
        print("[TARGETED IMAGE] Missing TMP PathIDs:")
        for pid in missing_pids:
            print(f"    {pid}")
        print("[TARGETED IMAGE] Patcher will NOT run.")
        print("[TARGETED IMAGE] ==========================================")
        return True

    command = [targeted_image_patcher_program, target_bundle_path] + normalized_target_pids

    print("[TARGETED IMAGE] Condition satisfied.")
    print(f"[TARGETED IMAGE] TMP PathIDs to patch: {len(normalized_target_pids)}")
    print("[TARGETED IMAGE] Starting FontReplacementHunter.")
    print("[TARGETED IMAGE] ==========================================")

    result = subprocess.run(command, cwd=os.path.dirname(targeted_image_patcher_program), check=False)

    print("[TARGETED IMAGE] ==========================================")

    if result.returncode != 0:
        print(f"[TARGETED IMAGE] Patcher failed with exit code {result.returncode}.")
        print("[TARGETED IMAGE] ==========================================")
        return False

    if not os.path.isfile(target_bundle_path):
        print("[TARGETED IMAGE] ERROR: patched bundle does not exist.")
        print("[TARGETED IMAGE] ==========================================")
        return False

    print("[TARGETED IMAGE] Patcher completed successfully.")
    print(f"[TARGETED IMAGE] Patched TMP PathIDs: {len(normalized_target_pids)}")
    print("[TARGETED IMAGE] ==========================================")
    return True


# ============================================================
# SNAPSHOT
# ============================================================

def copy_ga_files(destination_root):
    game_root = os.path.abspath(gameloc)
    destination_root = os.path.abspath(destination_root)

    print(f"[RAYQUAZA] Creating snapshot: {destination_root}")

    os.makedirs(destination_root, exist_ok=True)

    for source_file in sorted(GA_FILES):
        source_file = os.path.abspath(source_file)

        if not os.path.isfile(source_file):
            raise FileNotFoundError(f"RAYQUAZA snapshot source file not found:\n{source_file}")

        relative_path = os.path.relpath(source_file, game_root)
        destination_file = os.path.join(destination_root, relative_path).replace("\\", "/")

        os.makedirs(os.path.dirname(destination_file), exist_ok=True)
        shutil.copy2(source_file, destination_file)

        print("[RAYQUAZA] Copied:")
        print(f"    SOURCE:      {source_file}")
        print(f"    DESTINATION: {destination_file}")


# ============================================================
# UNITYFS DETECTION
# ============================================================

def is_unityfs_bundle(file_path):
    try:
        with open(file_path, "rb") as f:
            signature = f.read(7)
        return signature == b"UnityFS"
    except Exception as e:
        print(f"[COMPRESS] ERROR reading {file_path}: {e}")
        return False


# ============================================================
# COMPRESSION LOG HELPERS
# ============================================================

def compression_console_print(text):
    with COMPRESSION_CONSOLE_LOCK:
        print(text, flush=True)


def sanitize_log_filename(file_path):
    name = os.path.basename(file_path)
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return name or "bundle"


def strip_ansi(text):
    return re.sub(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "", text)


def save_compression_raw_log(job_index, source_file, raw_output):
    if not SAVE_FULL_COMPRESSION_LOGS:
        return ""

    try:
        os.makedirs(COMPRESSION_LOG_DIR, exist_ok=True)
        base_name = sanitize_log_filename(source_file)
        log_path = os.path.join(COMPRESSION_LOG_DIR, f"{job_index:03d}_{base_name}.log")
        with open(log_path, "w", encoding="utf-8", errors="replace") as log_file:
            log_file.write(raw_output)
        return log_path
    except Exception as e:
        compression_console_print(f"[COMPRESS][{job_index:02d}] WARNING: unable to save raw log: {e}")
        return ""


def extract_last_line_value(text, label):
    value = ""
    pattern = re.compile(rf"(?i)\b{re.escape(label)}\s*(?::|=)\s*(.*?)\s*$")
    for line in text.splitlines():
        match = pattern.search(line)
        if match:
            candidate = match.group(1).strip()
            if candidate:
                value = candidate
    return value


def contains_marker(text, marker):
    return marker.lower() in text.lower()


def parse_compressor_log(raw_output):
    text = strip_ansi(raw_output)
    return {
        "input_size": extract_last_line_value(text, "Input size"),
        "output_size": extract_last_line_value(text, "Output size"),
        "physical_ratio": extract_last_line_value(text, "Physical ratio"),
        "physical_reduction": extract_last_line_value(text, "Physical reduction"),
        "payload_ratio": extract_last_line_value(text, "Payload ratio"),
        "payload_reduction": extract_last_line_value(text, "Payload reduction"),
        "data_area": extract_last_line_value(text, "Data area"),
        "compressed_bytes": extract_last_line_value(text, "Compressed bytes"),
        "decompressed_bytes": extract_last_line_value(text, "Decompressed bytes"),
        "compression_detected": extract_last_line_value(text, "Compression detected"),
        "source_sha256": extract_last_line_value(text, "Source SHA-256"),
        "roundtrip_sha256": extract_last_line_value(text, "Roundtrip SHA-256"),
        "full_validation": contains_marker(text, "FULL VALIDATION: PASSED"),
        "byte_exact": contains_marker(text, "Byte-for-byte comparison: EXACT MATCH"),
        "sha_match": contains_marker(text, "SHA-256: MATCH"),
    }


def print_log_tail(raw_output, lines_count=80):
    text = strip_ansi(raw_output).splitlines()
    if not text:
        print("    <no compressor output>")
        return
    tail = text[-lines_count:]
    print(f"    --- compressor log tail ({len(tail)} lines) ---")
    for line in tail:
        print(f"    {line}")
    print("    --- end compressor log tail ---")


def make_relative_game_path(path):
    try:
        return os.path.relpath(os.path.abspath(path), os.path.abspath(gameloc)).replace("\\", "/")
    except Exception:
        return os.path.abspath(path).replace("\\", "/")


def validate_compressor_success(return_code, temp_file, parsed_log):
    if return_code != 0:
        return False, f"compressor exit code {return_code}"

    if not os.path.isfile(temp_file):
        return False, "compressor did not create output"

    if os.path.getsize(temp_file) <= 0:
        return False, "compressed output is empty"

    if not is_unityfs_bundle(temp_file):
        return False, "compressed output is not UnityFS"

    if REQUIRE_FULL_VALIDATION_MARKERS:
        if not parsed_log["full_validation"]:
            return False, "missing FULL VALIDATION: PASSED marker"
        if not parsed_log["byte_exact"]:
            return False, "missing Byte-for-byte comparison: EXACT MATCH marker"
        if not parsed_log["sha_match"]:
            return False, "missing SHA-256: MATCH marker"

    return True, ""


def print_compression_job_result(result):
    width = 78
    lines = []
    status = result["status"].upper()
    job_label = f"[COMPRESS][{result['job_index']:02d}/{result['total_jobs']:02d}] {status}"
    lines.append("┌" + "─" * width + "┐")
    lines.append("│ " + job_label[:width - 1].ljust(width - 1) + "│")
    lines.append("├" + "─" * width + "┤")
    lines.append("│ " + f"Path: {result['relative_path']}"[:width - 1].ljust(width - 1) + "│")
    lines.append("│ " + f"Elapsed: {result['elapsed']:.2f}s".ljust(width - 1) + "│")

    if status == "SUCCESS":
        info = result["parsed"]
        fields = [
            f"Input size: {info['input_size'] or 'n/a'}",
            f"Output size: {info['output_size'] or 'n/a'}",
            f"Physical ratio: {info['physical_ratio'] or 'n/a'}",
            f"Physical reduction: {info['physical_reduction'] or 'n/a'}",
            f"Payload ratio: {info['payload_ratio'] or 'n/a'}",
            f"Payload reduction: {info['payload_reduction'] or 'n/a'}",
            f"Data area: {info['data_area'] or 'n/a'}",
            f"Compressed bytes: {info['compressed_bytes'] or 'n/a'}",
            f"Decompressed bytes: {info['decompressed_bytes'] or 'n/a'}",
            f"Compression detected: {info['compression_detected'] or 'n/a'}",
            f"Full validation: {'PASSED' if info['full_validation'] else 'NOT CONFIRMED'}",
            f"Byte-for-byte: {'EXACT MATCH' if info['byte_exact'] else 'NOT CONFIRMED'}",
            f"SHA-256: {'MATCH' if info['sha_match'] else 'NOT CONFIRMED'}",
            f"Source SHA-256: {info['source_sha256'] or 'n/a'}",
            f"Roundtrip SHA-256: {info['roundtrip_sha256'] or 'n/a'}",
            f"Replaced: {result['source_file']}",
            f"Raw log: {result['log_path'] or 'disabled'}",
        ]
    elif status == "SKIPPED":
        fields = [f"Reason: {result['reason']}"]
    else:
        fields = [f"Reason: {result['reason']}", f"Raw log: {result['log_path'] or 'disabled'}"]

    for field in fields:
        lines.append("│ " + field[:width - 1].ljust(width - 1) + "│")

    lines.append("└" + "─" * width + "┘")
    compression_console_print("\n".join(lines))

    if status == "FAILED" and result.get("raw_output"):
        compression_console_print("[COMPRESS][%02d/%02d] Failure log tail:" % (result["job_index"], result["total_jobs"]))
        with COMPRESSION_CONSOLE_LOCK:
            print_log_tail(result["raw_output"], FAILED_LOG_TAIL_LINES)

    if PRINT_FULL_COMPRESSOR_LOG and result.get("raw_output"):
        compression_console_print("[COMPRESS][%02d/%02d] Full compressor log:" % (result["job_index"], result["total_jobs"]))
        with COMPRESSION_CONSOLE_LOCK:
            print(strip_ansi(result["raw_output"]), end="" if result["raw_output"].endswith("\n") else "\n", flush=True)


# ============================================================
# UNITY BUNDLE COMPRESSION
# ============================================================

def compress_ga_files():
    COMPRESS_GA_FILES = True

    if not COMPRESS_GA_FILES:
        print("[COMPRESS] Compression disabled.")
        return True

    compressor_path = os.path.abspath(compressor_program)

    if not os.path.isfile(compressor_path):
        print("[COMPRESS] ERROR: UnityBundleCompressor.exe not found:")
        print(f"    {compressor_path}")
        return False

    ga_files = sorted(os.path.abspath(path) for path in GA_FILES)
    total_jobs = len(ga_files)

    print("[COMPRESS] ==========================================")
    print("[COMPRESS] Starting UnityFS LZMA compression...")
    print(f"[COMPRESS] Maximum concurrent GA compressions: {MAX_CONCURRENT_COMPRESSION}")
    print(f"[COMPRESS] Total GA files: {total_jobs}")
    print(f"[COMPRESS] Per-job logs: {'ON' if SAVE_FULL_COMPRESSION_LOGS else 'OFF'}")
    if SAVE_FULL_COMPRESSION_LOGS:
        os.makedirs(COMPRESSION_LOG_DIR, exist_ok=True)
        print(f"[COMPRESS] Log directory: {COMPRESSION_LOG_DIR}")
    print("[COMPRESS] Compressor stdout/stderr is captured per job to prevent interleaving.")
    print("[COMPRESS] ==========================================")

    def compress_single_ga(job_index, source_file):
        started_at = time.perf_counter()
        source_file = os.path.abspath(source_file)
        relative_path = make_relative_game_path(source_file)
        temp_file = source_file + ".lzma.tmp"
        raw_output = ""
        parsed_log = {}
        log_path = ""

        compression_console_print(f"[COMPRESS][{job_index:02d}/{total_jobs:02d}] START {relative_path}")

        if not os.path.isfile(source_file):
            result = {
                "job_index": job_index,
                "total_jobs": total_jobs,
                "source_file": source_file,
                "relative_path": relative_path,
                "status": "failed",
                "reason": "file not found",
                "elapsed": time.perf_counter() - started_at,
                "parsed": parsed_log,
                "log_path": log_path,
                "raw_output": raw_output,
            }
            print_compression_job_result(result)
            return result

        if not is_unityfs_bundle(source_file):
            result = {
                "job_index": job_index,
                "total_jobs": total_jobs,
                "source_file": source_file,
                "relative_path": relative_path,
                "status": "skipped",
                "reason": "not UnityFS",
                "elapsed": time.perf_counter() - started_at,
                "parsed": parsed_log,
                "log_path": log_path,
                "raw_output": raw_output,
            }
            print_compression_job_result(result)
            return result

        if not wait_for_file_idle(source_file):
            result = {
                "job_index": job_index,
                "total_jobs": total_jobs,
                "source_file": source_file,
                "relative_path": relative_path,
                "status": "failed",
                "reason": "source bundle is locked",
                "elapsed": time.perf_counter() - started_at,
                "parsed": parsed_log,
                "log_path": log_path,
                "raw_output": raw_output,
            }
            print_compression_job_result(result)
            return result

        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except Exception as e:
            result = {
                "job_index": job_index,
                "total_jobs": total_jobs,
                "source_file": source_file,
                "relative_path": relative_path,
                "status": "failed",
                "reason": f"unable to remove old temp file: {e}",
                "elapsed": time.perf_counter() - started_at,
                "parsed": parsed_log,
                "log_path": log_path,
                "raw_output": raw_output,
            }
            print_compression_job_result(result)
            return result

        command = [compressor_path, "--input", source_file, "--output", temp_file, "--compression", "lzma"]

        try:
            completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", check=False)
            raw_output = completed.stdout or ""
            parsed_log = parse_compressor_log(raw_output)
            log_path = save_compression_raw_log(job_index, source_file, raw_output)

            valid, validation_reason = validate_compressor_success(completed.returncode, temp_file, parsed_log)

            if not valid:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except Exception:
                    pass
                result = {
                    "job_index": job_index,
                    "total_jobs": total_jobs,
                    "source_file": source_file,
                    "relative_path": relative_path,
                    "status": "failed",
                    "reason": validation_reason,
                    "elapsed": time.perf_counter() - started_at,
                    "parsed": parsed_log,
                    "log_path": log_path,
                    "raw_output": raw_output,
                }
                print_compression_job_result(result)
                return result

            if not wait_for_file_idle(source_file):
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except Exception:
                    pass
                result = {
                    "job_index": job_index,
                    "total_jobs": total_jobs,
                    "source_file": source_file,
                    "relative_path": relative_path,
                    "status": "failed",
                    "reason": "source bundle still locked before replacement",
                    "elapsed": time.perf_counter() - started_at,
                    "parsed": parsed_log,
                    "log_path": log_path,
                    "raw_output": raw_output,
                }
                print_compression_job_result(result)
                return result

            temp_size = os.path.getsize(temp_file)
            os.replace(temp_file, source_file)

            if not os.path.isfile(source_file):
                result = {
                    "job_index": job_index,
                    "total_jobs": total_jobs,
                    "source_file": source_file,
                    "relative_path": relative_path,
                    "status": "failed",
                    "reason": "final file missing after replacement",
                    "elapsed": time.perf_counter() - started_at,
                    "parsed": parsed_log,
                    "log_path": log_path,
                    "raw_output": raw_output,
                }
                print_compression_job_result(result)
                return result

            if os.path.getsize(source_file) <= 0:
                result = {
                    "job_index": job_index,
                    "total_jobs": total_jobs,
                    "source_file": source_file,
                    "relative_path": relative_path,
                    "status": "failed",
                    "reason": "final file is empty after replacement",
                    "elapsed": time.perf_counter() - started_at,
                    "parsed": parsed_log,
                    "log_path": log_path,
                    "raw_output": raw_output,
                }
                print_compression_job_result(result)
                return result

            if not is_unityfs_bundle(source_file):
                result = {
                    "job_index": job_index,
                    "total_jobs": total_jobs,
                    "source_file": source_file,
                    "relative_path": relative_path,
                    "status": "failed",
                    "reason": "final file is not UnityFS after replacement",
                    "elapsed": time.perf_counter() - started_at,
                    "parsed": parsed_log,
                    "log_path": log_path,
                    "raw_output": raw_output,
                }
                print_compression_job_result(result)
                return result

            result = {
                "job_index": job_index,
                "total_jobs": total_jobs,
                "source_file": source_file,
                "relative_path": relative_path,
                "status": "success",
                "reason": "",
                "elapsed": time.perf_counter() - started_at,
                "parsed": parsed_log,
                "log_path": log_path,
                "raw_output": raw_output,
                "output_size_bytes": temp_size,
            }
            print_compression_job_result(result)
            return result

        except Exception as e:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception:
                pass

            result = {
                "job_index": job_index,
                "total_jobs": total_jobs,
                "source_file": source_file,
                "relative_path": relative_path,
                "status": "failed",
                "reason": str(e),
                "elapsed": time.perf_counter() - started_at,
                "parsed": parsed_log,
                "log_path": log_path,
                "raw_output": raw_output,
            }
            print_compression_job_result(result)
            return result

    results = []

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_COMPRESSION, thread_name_prefix="RayquazaCompress") as executor:
        future_to_job = {}
        for job_index, source_file in enumerate(ga_files, start=1):
            future = executor.submit(compress_single_ga, job_index, source_file)
            future_to_job[future] = job_index

        for future in as_completed(future_to_job):
            job_index = future_to_job[future]
            try:
                results.append(future.result())
            except Exception as e:
                compression_console_print(f"[COMPRESS][{job_index:02d}/{total_jobs:02d}] WORKER CRASHED: {e}")
                results.append({
                    "job_index": job_index,
                    "total_jobs": total_jobs,
                    "source_file": "<unknown>",
                    "relative_path": "<unknown>",
                    "status": "failed",
                    "reason": f"worker crashed: {e}",
                    "elapsed": 0.0,
                    "parsed": {},
                    "log_path": "",
                    "raw_output": "",
                })

    results.sort(key=lambda item: item["job_index"])

    total_compressed = sum(1 for item in results if item["status"] == "success")
    total_skipped = sum(1 for item in results if item["status"] == "skipped")
    total_failed = sum(1 for item in results if item["status"] == "failed")

    print("[COMPRESS] ==========================================")
    print("[COMPRESS] Final compression summary:")
    print(f"[COMPRESS] Compressed: {total_compressed}")
    print(f"[COMPRESS] Skipped:    {total_skipped}")
    print(f"[COMPRESS] Failed:     {total_failed}")
    print("[COMPRESS] ==========================================")

    for item in results:
        status = item["status"].upper()
        info = item.get("parsed", {})
        ratio = info.get("payload_ratio") or "n/a"
        print(f"[COMPRESS][{item['job_index']:02d}/{total_jobs:02d}] {status} | {item['relative_path']} | payload ratio: {ratio} | elapsed: {item['elapsed']:.2f}s")

    return total_failed == 0


# ============================================================
# FILE / ARGUMENT CHECKING
# ============================================================

def check_program_exists(program):
    program_path = os.path.abspath(program)

    if not os.path.isfile(program_path):
        raise FileNotFoundError(f"The program '{program}' does not exist.")

    print(f"The program '{program}' exists")

    if not os.access(program_path, os.X_OK):
        raise PermissionError(f"The program '{program}' is not executable.")

    return program_path


def check_arguments_exist(args):
    for arg in args:
        arg = str(arg).strip()

        if arg == "-":
            yield arg
            continue

        if is_path_id(arg):
            yield arg
            continue

        if is_kind(arg):
            yield arg
            continue

        arg_path = os.path.abspath(arg)

        if not os.path.isfile(arg_path):
            print(f"The argument '{arg}' does not exist.")

        yield arg_path


# ============================================================
# NEWUAFGJ OUTPUT
# ============================================================

def run_newuafgj_process(program_path, args_paths, operation_index, total_operations, progress_bar=None):
    if not USE_TQDM:
        process = subprocess.run([program_path] + args_paths, check=False)
        return process.returncode

    try:
        process = subprocess.Popen([program_path] + args_paths, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
    except Exception as e:
        print("[BUILD] ERROR starting NewUAFGJ:")
        print(f"[BUILD] {e}")
        return -1

    if progress_bar is not None:
        progress_bar.set_description(f"UAFGJ {operation_index}/{total_operations}")

    try:
        if process.stdout is not None:
            for line in process.stdout:
                stripped = line.rstrip()
                upper = stripped.upper()

                is_fatal = "FATAL" in upper

                is_unchecked_error = (
                    "UNCHECKED" in upper
                    and (
                        "[ERROR]" in upper
                        or "ERROR:" in upper
                        or "EXCEPTION" in upper
                        or "FAILED" in upper
                        or "FAILURE" in upper
                    )
                )

                if is_fatal or is_unchecked_error:
                    print(stripped)

                    print("[BUILD] ==========================================")
                    print("[BUILD] NewUAFGJ fatal error detected.")
                    print(f"[BUILD] Operation: {operation_index}/{total_operations}")
                    print(f"[BUILD] Arguments: {args_paths}")
                    print(f"[BUILD] Error line: {stripped}")
                    print("[BUILD] Terminating NewUAFGJ immediately.")
                    print("[BUILD] Script execution will stop.")
                    print("[BUILD] ==========================================")

                    try:
                        process.kill()
                    except Exception:
                        pass

                    try:
                        process.wait()
                    except Exception:
                        pass

                    return -2

        return_code = process.wait()

    except Exception as e:
        print("[BUILD] ERROR while reading NewUAFGJ output:")
        print(f"[BUILD] {e}")

        try:
            process.kill()
        except Exception:
            pass

        try:
            return_code = process.wait()
        except Exception:
            return_code = -1

    return return_code

# ============================================================
# NEWUAFGJ EXECUTION
# ============================================================

def run_program(program, args_list):
    program_path = check_program_exists(program)
    normal_operations = []

    for args in args_list:
        if not isinstance(args, (list, tuple)):
            continue

        if NEEDS_DLL_PATCHES:
            if is_dll_patch_operation(args):
                continue

        normal_operations.append(list(args))

    if not normal_operations:
        print("[BUILD] No NewUAFGJ operations.")
        return True

    total_operations = len(normal_operations)

    print("[BUILD] ==========================================")
    print("[BUILD] Starting NewUAFGJ.")
    print("[BUILD] Mode: SEQUENTIAL")
    print("[BUILD] Concurrent NewUAFGJ processes: 1")
    print(f"[BUILD] Total operations: {total_operations}")
    print(f"[BUILD] TQDM output filtering: {'ON' if USE_TQDM else 'OFF'}")
    print(f"[BUILD] Conditional same-file pause: {CONDITIONAL_SAME_FILE_PAUSE:.2f}s")

    if USE_TQDM:
        print("[BUILD] Visible UAFGJ lines: FATAL / UNCHECKED only.")

    print("[BUILD] ==========================================")

    if USE_TQDM:
        progress = tqdm(total=total_operations, unit="op", dynamic_ncols=True, desc="NewUAFGJ", leave=True)
    else:
        progress = None

    completed = 0
    previous_asset_path = None

    try:
        for index, args in enumerate(normal_operations, start=1):
            args_paths = list(check_arguments_exist(args))
            print(str(args_paths))

            current_asset_path = None

            if args_paths:
                current_asset_path = os.path.abspath(str(args_paths[0])).lower()

            if current_asset_path and current_asset_path == previous_asset_path:
                print("[BUILD] ==========================================")
                print("[BUILD] Same asset file as previous operation detected.")
                print(f"[BUILD] Asset: {current_asset_path}")
                print(f"[BUILD] Waiting {CONDITIONAL_SAME_FILE_PAUSE:.2f}s before next NewUAFGJ start...")
                time.sleep(CONDITIONAL_SAME_FILE_PAUSE)

                if os.path.isfile(current_asset_path):
                    if not wait_for_file_idle(current_asset_path):
                        print("[BUILD] ERROR: asset file is still locked after conditional pause.")
                        print(f"[BUILD] Asset: {current_asset_path}")
                        print("[BUILD] Remaining operations will NOT run.")
                        print("[BUILD] Compression will NOT run.")
                        print("[BUILD] AFTER snapshot will NOT run.")
                        print("[BUILD] ==========================================")
                        return False

                print("[BUILD] Asset file is idle. Continuing.")
                print("[BUILD] ==========================================")

            if progress is None:
                print(f"[BUILD] Operation {index}/{total_operations}")
                print(f"[BUILD] Running {program_path}")
                print(f"[BUILD] Arguments: {args_paths}")
            else:
                progress.set_description(f"NewUAFGJ {index}/{total_operations}")

            return_code = run_newuafgj_process(program_path, args_paths, index, total_operations, progress)

            if return_code != 0:
                print("[BUILD] ==========================================")
                print("[BUILD] FAILED.")
                print(f"[BUILD] Operation: {index}/{total_operations}")
                print(f"[BUILD] Exit code: {return_code}")
                print(f"[BUILD] Arguments: {args_paths}")
                print("[BUILD] Remaining operations will NOT run.")
                print("[BUILD] Compression will NOT run.")
                print("[BUILD] AFTER snapshot will NOT run.")
                print("[BUILD] ==========================================")
                return False

            completed += 1
            previous_asset_path = current_asset_path

            if progress is not None:
                progress.update(1)
            else:
                print("[BUILD] Finished successfully.")

        print("[BUILD] ==========================================")
        print("[BUILD] All NewUAFGJ operations finished successfully.")
        print(f"[BUILD] Successful: {completed}")
        print("[BUILD] Failed:     0")
        print("[BUILD] ==========================================")

        return True

    finally:
        if progress is not None:
            progress.close()


# ============================================================
# AUTOGEN PROCESSING
# ============================================================

def process_autogen_entries(files):
    normal_entries = []

    for entry in files:
        if not isinstance(entry, (list, tuple)):
            continue
        if NEEDS_DLL_PATCHES:
            if is_dll_patch_operation(entry):
                target = dll_path(DLL_RELATIVE_PATH)

                DLL_PATCH_REQUESTS.add(os.path.abspath(target))
                GA_FILES.add(os.path.abspath(target))

                print("[AUTOGEN] Registered DLL_PATCH:")
                print(f"    {target}")

                continue

        normal_entries.append(entry)

    return normal_entries


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    

    # ========================================================
    # AUTOGEN
    # ========================================================

    # === AUTOGEN START ===

# AUTOGEN main + run_program (generated by GUI)
    files = [
    
    ]


# === AUTOGEN END ===


    # ========================================================
    # PROCESS AUTOGEN
    # ========================================================


    files = process_autogen_entries(files)


    # ========================================================
    # DLL INITIALIZATION
    # ========================================================


    if NEEDS_DLL_PATCHES:
        if DLL_PATCH_REQUESTS:
            initialize_dll_state()


    # ========================================================
    # BEFORE SNAPSHOT
    # ========================================================


    if files:
        print("[RAYQUAZA] ==========================================")
        print("[RAYQUAZA] Creating BEFORE snapshot...")

        try:
            copy_ga_files(before_dir)
        except Exception as e:
            print("[RAYQUAZA] BEFORE snapshot FAILED:")
            print(str(e))
            raise

        print("[RAYQUAZA] BEFORE snapshot completed.")
        print("[RAYQUAZA] ==========================================")


    # ========================================================
    # DLL PATCH
    # ========================================================


    if NEEDS_DLL_PATCHES:
        if DLL_PATCH_REQUESTS:

            try:
                run_dll_patcher()
            except Exception as e:
                print("[DLL] PATCH FAILED:")
                print(str(e))
                print("[BUILD] Aborting before NewUAFGJ.")
                raise


    # ========================================================
    # NEWUAFGJ
    # ========================================================


    if files:
        build_success = run_program(
            program,
            files
        )

        if not build_success:
            raise RuntimeError("Una o più operazioni NewUAFGJ sono fallite.")
    else:
        print("[BUILD] No NewUAFGJ operations.")


    # ========================================================
    # TARGET IMAGE PATCH
    # ========================================================
    #
    # Bundle:
    #   bundle che contiene i due slot vuoti.
    #
    # TMP PathID:
    #   PathID dei due TextMeshProUGUI corrispondenti agli slot.
    #
    # NON servono gli Image PathID:
    #   FontReplacementHunter trova automaticamente
    #   l'Image del parent InteractCharacter e
    #   l'Image del figlio OutlineImage.
    # ========================================================

    if NEEDS_FRH:
        if files:
            targeted_patch_success = run_targeted_image_patcher(
                files,
                "StreamingAssets/AssetBundles/fd321a81826f968a8c8086d118ed88bb",
                [
                    "-5794335730920407933",
                    "2164585838490730081",
                ]
            )
            
            if not targeted_patch_success:
                raise RuntimeError("Targeted Image Patcher failed.")
            
            targeted_patch_success = run_targeted_image_patcher(
                files,
                "StreamingAssets/AssetBundles/e96a993af23a890be1e87bd8e1c250ee",
                [
                    "-6043221978528093929",
                ]
            )
            
            if not targeted_patch_success:
                raise RuntimeError("Targeted Image Patcher failed.")
            
            targeted_patch_success = run_targeted_image_patcher(
                files,
                "StreamingAssets/AssetBundles/640e49b2bc11fc8faf81a4d4921f19fb",
                [
                    "5858823373558919106",
                ]
            )

            if not targeted_patch_success:
                raise RuntimeError("Targeted Image Patcher failed.")


    # ========================================================
    # COMPRESSION
    # ========================================================


    if ENABLE_COMPRESSION:
        if files:
            print("[COMPRESS] ==========================================")
            print("[COMPRESS] Compressing GA files before AFTER snapshot...")

            compression_success = compress_ga_files()

            if not compression_success:

                print("[COMPRESS] ==========================================")
                print("[COMPRESS] COMPRESSION FAILED.")
                print("[COMPRESS] AFTER snapshot will NOT run.")
                print("[COMPRESS] ==========================================")

                raise RuntimeError("Una o più compressioni UnityFS sono fallite.")

            print("[COMPRESS] Compression step completed.")
            print("[COMPRESS] ==========================================")


    # ========================================================
    # AFTER SNAPSHOT
    # ========================================================


    if files:
        print("[RAYQUAZA] ==========================================")
        print("[RAYQUAZA] Creating AFTER snapshot...")

        try:
            copy_ga_files(after_dir)
        except Exception as e:
            print("[RAYQUAZA] AFTER snapshot FAILED:")
            print(str(e))
            raise

        print("[RAYQUAZA] AFTER snapshot completed.")
        print("[RAYQUAZA] ==========================================")


    # ========================================================
    # FINAL STATUS
    # ========================================================


    print("")
    
    print("============================================================")
    print("PIPELINE COMPLETATA CON SUCCESSO")
    print("============================================================")
    print("NewUAFGJ: PASS")
    print("Target Image patch: PASS")
    print("Compression: PASS")
    print("AFTER snapshot: PASS")
    print("============================================================")
    
    print("")


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
