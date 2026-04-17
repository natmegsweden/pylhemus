from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .gui import launch_gui
from . import read_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pylhemus")
    subparsers = parser.add_subparsers(dest="command", required=True)

    gui_parser = subparsers.add_parser("gui", help="Launch the digitisation GUI")
    gui_parser.add_argument("--settings", type=Path, help="Path to the settings JSON file")
    gui_parser.add_argument("--port", help="Override the serial port from settings")
    gui_parser.add_argument("--output-dir", type=Path, help="Override the output directory")
    gui_parser.set_defaults(handler=_handle_gui)

    settings_parser = subparsers.add_parser("read-settings", help="Dump FASTRAK settings to JSON")
    settings_parser.add_argument("--port", required=True, help="Serial port (e.g., COM3 or /dev/ttyUSB0)")
    settings_parser.add_argument("--baud", type=int, default=9600, help="Baud rate (default: 9600)")
    settings_parser.add_argument("--out", required=True, type=Path, help="Output JSON file path")
    settings_parser.add_argument("--timeout", type=float, default=1.0, help="Serial read timeout (s)")
    settings_parser.set_defaults(handler=_handle_read_settings)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return args.handler(args)


def _handle_gui(args: argparse.Namespace) -> int:
    return launch_gui(settings_path=args.settings, serial_port=args.port, output_dir=args.output_dir)


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