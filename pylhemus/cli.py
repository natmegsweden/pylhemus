from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .gui import launch_gui
from . import read_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pylhemus",
        description="FASTRAK digitisation GUI for OPM/MEG head tracking"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    gui_parser = subparsers.add_parser(
        "gui",
        help="Launch the digitisation GUI",
        description="Launch the FASTRAK digitisation GUI to capture head coordinates"
    )
    gui_parser.add_argument("--settings", type=Path, help="Path to the settings JSON file")
    gui_parser.add_argument("--port", help="Override the serial port from settings (e.g., COM3 or /dev/ttyUSB0)")
    gui_parser.add_argument("--output-dir", type=Path, help="Override the output directory for CSV files")
    gui_parser.add_argument("--dev-mode", action="store_true", help="Use development mode with simulated FASTRAK hardware")
    gui_parser.add_argument("--restore-last", action="store_true", help="Restore from last auto-saved session (skips setup dialog)")
    gui_parser.set_defaults(handler=_handle_gui)

    settings_parser = subparsers.add_parser(
        "read-settings",
        help="Dump FASTRAK settings to JSON",
        description="Read and dump FASTRAK device settings via serial connection"
    )
    settings_parser.add_argument("--port", required=True, help="Serial port (e.g., COM3 or /dev/ttyUSB0)")
    settings_parser.add_argument("--baud", type=int, default=9600, help="Baud rate (default: 9600)")
    settings_parser.add_argument("--out", required=True, type=Path, help="Output JSON file path")
    settings_parser.add_argument("--timeout", type=float, default=1.0, help="Serial read timeout in seconds (default: 1.0)")
    settings_parser.set_defaults(handler=_handle_read_settings)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return args.handler(args)


def _handle_gui(args: argparse.Namespace) -> int:
    return launch_gui(settings_path=args.settings, serial_port=args.port, output_dir=args.output_dir, dev_mode=args.dev_mode, restore_last=args.restore_last)


def _handle_read_settings(args: argparse.Namespace) -> int:
    argv = [
        "--port",
        args.port,
        "--baud",
        str(args.baud),
        "--out",
        str(args.out),
        "--timeout",
        str(args.timeout),
    ]
    return read_settings.main(argv)