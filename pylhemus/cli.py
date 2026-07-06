from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Sequence

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

    settings_gui_parser = subparsers.add_parser(
        "settings",
        help="Open settings dialog or read/write settings headlessly",
        description=(
            "Without flags: open the Pylhemus settings GUI dialog.\n"
            "With --dump or --apply: communicate with the FASTRAK device over serial.\n"
            "With --set-*: write values directly to the user settings file."
        ),
    )
    settings_gui_parser.add_argument("--settings", type=Path, help="Path to the settings JSON file (unused, reserved)")

    device_group = settings_gui_parser.add_argument_group("Device settings (require serial connection)")
    device_group.add_argument("--dump", action="store_true", help="Query FASTRAK device and dump settings JSON")
    device_group.add_argument("--out", type=Path, help="Write --dump output to FILE instead of stdout")
    device_group.add_argument("--apply", action="store_true", help="Restore device settings from --from FILE")
    device_group.add_argument("--from", dest="from_file", type=Path, help="Settings JSON file for --apply")
    device_group.add_argument("--port", help="Serial port (default: value from user settings)")
    device_group.add_argument("--baud", type=int, help="Baud rate (default: value from user settings)")
    device_group.add_argument("--timeout", type=float, default=1.0, help="Serial read timeout in seconds (default: 1.0)")

    file_group = settings_gui_parser.add_argument_group("User settings file (no device connection)")
    file_group.add_argument(
        "--set-units",
        choices=["cm", "inch"],
        metavar="cm|inch",
        help="Set digitisation.units in user settings file",
    )
    file_group.add_argument(
        "--set-metal-compensation",
        choices=["on", "off"],
        metavar="on|off",
        help="Set digitisation.metal_compensation in user settings file",
    )
    file_group.add_argument(
        "--set-factory-defaults",
        choices=["on", "off"],
        metavar="on|off",
        help="Set digitisation.set_factory_software_defaults in user settings file",
    )
    settings_gui_parser.set_defaults(handler=_handle_settings)

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
    stream_parser.add_argument("--continuous", "--continous", action="store_true", help="Enable continuous FASTRAK output mode (send C)")
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


def _handle_settings(args: argparse.Namespace) -> int:
    has_set_flag = any([args.set_units, args.set_metal_compensation, args.set_factory_defaults])
    selected_modes = sum(bool(flag) for flag in [args.dump, args.apply, has_set_flag])

    if selected_modes > 1:
        print("ERROR: --dump, --apply, and --set-* flags cannot be combined", file=sys.stderr)
        return 1

    if args.dump:
        return _handle_settings_dump(args)
    if args.apply:
        return _handle_settings_apply(args)
    if has_set_flag:
        return _handle_settings_set(args)

    from .gui import launch_settings

    return launch_settings(settings_path=args.settings)


def _handle_settings_dump(args: argparse.Namespace) -> int:
    from . import read_settings
    from .settings_loader import load_settings

    merged = load_settings()
    port = args.port or merged.get("serial_port", "COM1")
    baud = args.baud or int(merged.get("serial_baud", 9600))

    try:
        ser = read_settings.open_port(port, baud, timeout=args.timeout)
    except Exception as exc:
        print(f"ERROR: Could not open port {port} @ {baud}: {exc}", file=sys.stderr)
        return 2

    try:
        read_settings.ensure_ascii_and_quiet(ser)
        data = {
            "serial_port": port,
            "serial_baud": baud,
            "system": read_settings.query_system(ser),
        }
        active, l_raw = read_settings.query_active_stations(ser)
        data["stations_active_raw"] = l_raw
        data["stations_active"] = active

        stations = {}
        for idx in range(1, 5):
            if active[idx - 1]:
                try:
                    stations[str(idx)] = read_settings.query_station(ser, idx)
                except TimeoutError as exc:
                    stations[str(idx)] = {"station": idx, "error": str(exc)}
                except Exception as exc:
                    stations[str(idx)] = {"station": idx, "error": repr(exc)}
            else:
                stations[str(idx)] = {"station": idx, "active": False}
        data["stations"] = stations

        text = json.dumps(data, indent=2)
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text, encoding="utf-8")
        else:
            print(text)
        return 0
    finally:
        try:
            ser.close()
        except Exception:
            pass


def _handle_settings_apply(args: argparse.Namespace) -> int:
    from . import read_settings
    from .settings_loader import load_settings

    if args.from_file is None:
        print("ERROR: --apply requires --from FILE", file=sys.stderr)
        return 1

    merged = load_settings()
    port = args.port or merged.get("serial_port", "COM1")
    baud = args.baud or int(merged.get("serial_baud", 9600))

    try:
        ser = read_settings.open_port(port, baud, timeout=args.timeout)
    except Exception as exc:
        print(f"ERROR: Could not open port {port} @ {baud}: {exc}", file=sys.stderr)
        return 2

    try:
        data = json.loads(args.from_file.read_text(encoding="utf-8"))
        report = read_settings.apply_settings(ser, data)
        print(json.dumps(report, indent=2))
        return 0
    finally:
        try:
            ser.close()
        except Exception:
            pass


def _handle_settings_set(args: argparse.Namespace) -> int:
    from .settings_loader import load_user_settings, user_settings_path

    user = load_user_settings()
    user.setdefault("digitisation", {})
    changed = []

    if args.set_units is not None:
        user["digitisation"]["units"] = args.set_units
        changed.append(f"digitisation.units = {args.set_units!r}")

    if args.set_metal_compensation is not None:
        value = args.set_metal_compensation == "on"
        user["digitisation"]["metal_compensation"] = value
        changed.append(f"digitisation.metal_compensation = {value}")

    if args.set_factory_defaults is not None:
        value = args.set_factory_defaults == "on"
        user["digitisation"]["set_factory_software_defaults"] = value
        changed.append(f"digitisation.set_factory_software_defaults = {value}")

    path = user_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(user, indent=2, ensure_ascii=False), encoding="utf-8")

    for line in changed:
        print(f"Set: {line}")
    print(f"Saved to: {path}")
    return 0


def _handle_talk(args: argparse.Namespace) -> int:
    talk_args = list(args.talk_args)
    if talk_args and talk_args[0] == "--":
        talk_args = talk_args[1:]
    return talk.main(talk_args)


def _handle_stream(args: argparse.Namespace) -> int:
    settings = load_settings()
    dig_settings = settings.get("digitisation", {})
    port = args.port or settings.get("serial_port", "COM1")
    baud_rate = settings.get("serial_baud", 9600)
    hemisphere = _parse_fastrak_hemisphere(dig_settings)
    units = dig_settings.get("units", "cm")
    metal_compensation = dig_settings.get("metal_compensation", True)
    set_factory_defaults = dig_settings.get("set_factory_software_defaults", True)

    connector = FastrakConnector(
        usb_port=port,
        hemisphere=hemisphere,
        baud_rate=baud_rate,
        units=units,
        metal_compensation=metal_compensation,
        set_factory_defaults=set_factory_defaults,
    )
    connector.debug_serial = True
    connector.serialobj.timeout = args.timeout

    try:
        startup_warnings = []
        if args.no_prepare:
            connector.clear_old_data()
            connector.query_n_receivers()
        else:
            startup_warnings = connector.prepare_for_digitisation()
        if startup_warnings:
            for warning in startup_warnings:
                print(f"[FASTRAK WARNING] {warning}", file=sys.stderr)

        if args.metric:
            connector.send_serial_command(b"u", read_timeout=0.2 if connector.debug_serial else 0.0)

        connector.clear_old_data()
        if args.continuous:
            connector.send_serial_command(b"C\r", read_timeout=0.2)

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
                    mode_hint = "continuous output is off, so try clicking the pen" if not args.continuous else "check active stations and pen activity"
                    print(
                        f"[FASTRAK STREAM] No sample lines received yet; {mode_hint}.",
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
        if args.continuous:
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
