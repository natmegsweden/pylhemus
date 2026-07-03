from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Sequence

from . import read_settings
from . import talk
from .digitise.fastrak_connector import FastrakConnector
from .settings_loader import load_settings


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
    settings_parser.add_argument("--port", default="COM1", help="Serial port (e.g., COM3 or /dev/ttyUSB0)")
    settings_parser.add_argument("--baud", type=int, default=9600, help="Baud rate (default: 9600)")
    settings_parser.add_argument("--timeout", type=float, default=1.0, help="Serial read timeout in seconds (default: 1.0)")
    settings_parser.set_defaults(handler=_handle_read_settings)

    talk_parser = subparsers.add_parser(
        "talk",
        help="Friendly FASTRAK command interface",
        description="Run easier-to-understand FASTRAK commands"
    )
    talk_parser.add_argument("talk_args", nargs=argparse.REMAINDER, help="Arguments forwarded to 'pylhemus talk'")
    talk_parser.set_defaults(handler=_handle_talk)

    stream_parser = subparsers.add_parser(
        "stream",
        help="Stream FASTRAK output without the GUI",
        description="Open the FASTRAK serial port and print streamed sample lines without launching the GUI",
    )
    stream_parser.add_argument("--port", help="Override the serial port from settings (e.g., COM3 or /dev/ttyUSB0)")
    stream_parser.add_argument("--baud", type=int, default=9600, help="Baud rate (default: 9600)")
    stream_parser.add_argument("--timeout", type=float, default=1.0, help="Serial read timeout in seconds (default: 1.0)")
    stream_parser.add_argument("--duration", type=float, default=0.0, help="Seconds to stream (0 = until interrupted)")
    stream_parser.add_argument("--max-lines", type=int, default=0, help="Stop after this many received lines (0 = unlimited)")
    stream_parser.add_argument("--parsed", action="store_true", help="Emit one JSON object per received line")
    stream_parser.add_argument("--metric", action="store_true", help="Set centimeters before starting the stream")
    stream_parser.add_argument("--no-prepare", action="store_true", help="Skip ^S / c / F before starting the stream")
    stream_parser.set_defaults(handler=_handle_stream)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    forwarded_argv = list(argv) if argv is not None else sys.argv[1:]

    if not forwarded_argv:
        forwarded_argv = ["gui"]

    # Forward talk arguments directly so flags like "--port" are parsed by
    # pylhemus.talk instead of the top-level parser.
    if forwarded_argv and forwarded_argv[0] == "talk":
        return talk.main(forwarded_argv[1:])

    parser = build_parser()
    args = parser.parse_args(forwarded_argv)
    return args.handler(args)


def _handle_gui(args: argparse.Namespace) -> int:
    from .gui import launch_gui

    return launch_gui(settings_path=args.settings, serial_port=args.port, output_dir=args.output_dir, dev_mode=args.dev_mode, restore_last=args.restore_last)


def _handle_read_settings(args: argparse.Namespace) -> int:
    argv = [
        "--port",
        args.port,
        "--baud",
        str(args.baud),
        "--timeout",
        str(args.timeout),
    ]
    return read_settings.main(argv)


def _handle_talk(args: argparse.Namespace) -> int:
    talk_args = list(args.talk_args)
    if talk_args and talk_args[0] == "--":
        talk_args = talk_args[1:]
    return talk.main(talk_args)


def _handle_stream(args: argparse.Namespace) -> int:
    settings = load_settings()
    dig_settings = settings.get("digitisation", {})
    port = args.port or settings.get("serial_port", "COM1")
    hemisphere = _parse_fastrak_hemisphere(dig_settings)

    connector = FastrakConnector(usb_port=port, hemisphere=hemisphere)
    connector.debug_serial = True
    connector.serialobj.timeout = args.timeout

    try:
        startup_warnings = connector.prepare_for_digitisation()
        if startup_warnings:
            for warning in startup_warnings:
                print(f"[FASTRAK WARNING] {warning}", file=sys.stderr)

        if args.metric:
            connector.send_serial_command(b"u", read_timeout=0.2 if connector.debug_serial else 0.0)

        connector.clear_old_data()
        connector.send_serial_command(b"C\r")

        start_time = time.time()
        deadline = start_time + args.duration if args.duration and args.duration > 0 else None
        first_line_at: float | None = None
        idle_notice_shown = False
        total_lines = 0

        while True:
            if deadline is not None and time.time() >= deadline:
                break

            raw = connector.serialobj.readline()
            if not raw:
                if not idle_notice_shown and first_line_at is None and time.time() - start_time >= max(args.timeout * 2.0, 2.0):
                    print(
                        "[FASTRAK STREAM] No sample lines received yet; check active stations and pen activity.",
                        file=sys.stderr,
                    )
                    idle_notice_shown = True
                continue

            text = raw.decode("ascii", errors="ignore").strip()
            if not text:
                continue

            first_line_at = first_line_at or time.time()
            total_lines += 1
            parsed = talk._parse_stream_sample(text)

            if args.parsed:
                print(json.dumps(parsed if parsed is not None else {"sample": False, "raw": text}))
            elif connector.debug_serial:
                print(f"[FASTRAK RAW] {text}")
            else:
                print(text)

            if args.max_lines and total_lines >= args.max_lines:
                break
    except KeyboardInterrupt:
        pass
    finally:
        try:
            connector.send_serial_command(b"c\r")
        except Exception:
            pass
        try:
            connector.serialobj.close()
        except Exception:
            pass

    return 0


def _parse_fastrak_hemisphere(dig_settings: dict) -> tuple[float, float, float] | None:
    hemisphere = dig_settings.get("hemisphere", [0.0, 0.0, 1.0])
    if hemisphere is None:
        return None
    if not isinstance(hemisphere, (list, tuple)) or len(hemisphere) != 3:
        raise ValueError("digitisation.hemisphere must be a 3-value list or tuple.")

    values = tuple(float(value) for value in hemisphere)
    if values == (0.0, 0.0, 0.0):
        raise ValueError("digitisation.hemisphere must not be the zero vector.")
    return values
