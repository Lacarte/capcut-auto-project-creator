#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Copy the newest project folder from ./out to CapCut drafts
and send all ./out subfolders to the Recycle Bin (Windows).

Usage:
    python move_latest_capcut_project.py
    # or with options:
    python move_latest_capcut_project.py --out ./out --dest "C:\\Users\\Admin\\AppData\\Local\\CapCut\\User Data\\Projects\\com.lveditor.draft"
"""

import argparse
import datetime as dt
import logging
import os
from pathlib import Path
import shutil
import sys
import ctypes
from ctypes import wintypes

# -----------------------------
# Windows Recycle Bin helper (no extra deps)
# -----------------------------
# Uses SHFileOperationW with FOF_ALLOWUNDO to send to Recycle Bin.

def send_to_recycle_bin(path: Path) -> None:
    """
    Move a file or folder to the Recycle Bin on Windows using SHFileOperationW.
    Raises RuntimeError on failure.
    """
    # Constants
    FO_DELETE = 3
    FOF_ALLOWUNDO = 0x0040
    FOF_NOCONFIRMATION = 0x0010
    FOF_SILENT = 0x0004
    FOF_NOERRORUI = 0x0400

    # Prepare double-NULL-terminated string for SHFileOperation
    p = str(path.resolve()) + "\0\0"

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_uint16),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", wintypes.LPVOID),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    shfo = SHFILEOPSTRUCTW()
    shfo.hwnd = None
    shfo.wFunc = FO_DELETE
    shfo.pFrom = p
    shfo.pTo = None
    shfo.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
    shfo.fAnyOperationsAborted = False
    shfo.hNameMappings = None
    shfo.lpszProgressTitle = None

    res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(shfo))
    if res != 0:
        raise RuntimeError(f"SHFileOperationW failed with code {res}")
    if shfo.fAnyOperationsAborted:
        raise RuntimeError("Recycle Bin operation aborted by user/system.")

# -----------------------------
# Core logic
# -----------------------------

def newest_subfolder(parent: Path) -> Path | None:
    candidates = [p for p in parent.iterdir() if p.is_dir()]
    if not candidates:
        return None
    # On Windows, getctime is creation time.
    return max(candidates, key=lambda p: p.stat().st_ctime)

def unique_dest(dest_root: Path, name: str) -> Path:
    base = dest_root / name
    if not base.exists():
        return base
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return dest_root / f"{name}-{stamp}"

def copy_tree(src: Path, dest: Path) -> None:
    # Python 3.8+: dirs_exist_ok available; but we choose a safe fail if exists.
    if dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")
    shutil.copytree(src, dest)

def move_all_out_to_recycle(out_dir: Path) -> None:
    for p in out_dir.iterdir():
        if p.is_dir():
            logging.info(f"Sending to Recycle Bin: {p}")
            send_to_recycle_bin(p)

def main():
    parser = argparse.ArgumentParser(description="Copy latest ./out project to CapCut drafts and recycle ./out folders.")
    parser.add_argument("--out", default="./out", help="Path to the 'out' directory containing project folders.")
    parser.add_argument(
        "--dest",
        default=r"C:\Users\Admin\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft",
        help="Destination CapCut drafts directory."
    )
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG","INFO","WARNING","ERROR","CRITICAL"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    out_dir = Path(args.out).resolve()
    dest_root = Path(args.dest)

    if not os.name == "nt":
        logging.error("This script is Windows-only.")
        sys.exit(1)

    if not out_dir.exists():
        logging.error(f"Out directory does not exist: {out_dir}")
        sys.exit(1)

    if not dest_root.exists():
        try:
            dest_root.mkdir(parents=True, exist_ok=True)
            logging.info(f"Created destination root: {dest_root}")
        except Exception as e:
            logging.error(f"Failed to create destination root: {dest_root} -> {e}")
            sys.exit(1)

    latest = newest_subfolder(out_dir)
    if latest is None:
        logging.warning(f"No subfolders found in {out_dir}. Nothing to copy.")
    else:
        target = unique_dest(dest_root, latest.name)
        logging.info(f"Copying newest folder:\n  from: {latest}\n    to: {target}")
        try:
            copy_tree(latest, target)
            logging.info("Copy complete.")
        except Exception as e:
            logging.error(f"Copy failed: {e}")
            sys.exit(1)

    # Recycle all subfolders inside ./out
    try:
        move_all_out_to_recycle(out_dir)
        logging.info("All subfolders in ./out were sent to the Recycle Bin.")
    except Exception as e:
        logging.error(f"Failed to move folders to Recycle Bin: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()


# //list transition pick
# //cover image