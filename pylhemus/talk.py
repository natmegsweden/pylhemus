from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Sequence

from . import read_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pylhemus talk",
        description="Friendly FASTRAK command interface.",
    )
    parser.add_argument("--port", default="COM1", help="Serial port (for example COM3 or /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=9600, help="Baud rate (default: 9600)")
    parser.add_argument("--timeout", type=float, default=1.0, help="Serial read timeout in seconds")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON output")

    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Read system status and configuration")
    status_parser.set_defaults(handler=_handle_status)

    receivers_parser = subparsers.add_parser("receivers", help="Show active station flags")
    receivers_parser.set_defaults(handler=_handle_receivers)

    station_parser = subparsers.add_parser("station", help="Read a specific station configuration")
    station_parser.add_argument("--id", required=True, type=int, choices=[1, 2, 3, 4], help="Station index (1-4)")
    station_parser.set_defaults(handler=_handle_station)

    dump_parser = subparsers.add_parser("dump-settings", help="Dump full settings summary")
    dump_parser.add_argument("--out", type=Path, help="Optional output JSON file path")
    dump_parser.set_defaults(handler=_handle_dump_settings)

    apply_parser = subparsers.add_parser(
        "apply-settings",
        help="Restore settings to device from a previously-saved JSON file",
    )
    apply_parser.add_argument(
        "--from",
        dest="from_file",
        required=True,
        type=Path,
        help="Path to settings JSON file (produced by dump-settings)",
    )
    apply_parser.set_defaults(handler=_handle_apply_settings)

    set_units_parser = subparsers.add_parser("set-units", help="Set conversion units")
    set_units_parser.add_argument("units", choices=["cm", "in"], help="Target units")
    set_units_parser.set_defaults(handler=_handle_set_units)

    prepare_parser = subparsers.add_parser("prepare", help="Run basic prepare sequence (ASCII + defaults + metric)")
    prepare_parser.set_defaults(handler=_handle_prepare)

    stream_parser = subparsers.add_parser("stream", help="Stream FASTRAK output without the GUI")
    stream_parser.add_argument("--duration", type=float, default=0.0, help="Seconds to stream (0 = until interrupted)")
    stream_parser.add_argument("--max-lines", type=int, default=0, help="Stop after this many received lines (0 = unlimited)")
    stream_parser.add_argument("--parsed", action="store_true", help="Emit one JSON object per received line")
    stream_parser.add_argument("--continuous", "--continous", action="store_true", help="Enable continuous FASTRAK output mode (send C)")
    stream_parser.add_argument("--metric", action="store_true", help="Set centimeters before starting the stream")
    stream_parser.add_argument("--no-prepare", action="store_true", help="Skip ^S / c / F before starting the stream")
    stream_parser.set_defaults(handler=_handle_stream)

    raw_parser = subparsers.add_parser("send-raw", help="Send a raw FASTRAK command")
    raw_parser.add_argument("raw_command", help="Command text, for example S, X, l1, H1, ^S")
    raw_parser.add_argument("--expect", help="Optional regex expected in response")
    raw_parser.add_argument(
        "--all-lines",
        action="store_true",
        help="Return all received lines instead of preferring command-matching lines",
    )
    raw_parser.add_argument(
        "--prepare",
        action="store_true",
        help="Run ^S / c / F (ASCII+quiet) before sending the command",
    )
    raw_parser.add_argument("--read-timeout", type=float, default=1.0, help="Read timeout for this command")
    raw_parser.set_defaults(handler=_handle_send_raw)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        ser = read_settings.open_port(args.port, args.baud, timeout=args.timeout)
    except Exception as exc:
        print(f"ERROR: Could not open port {args.port} @ {args.baud}: {exc}", file=sys.stderr)
        return 2

    try:
        payload = args.handler(args, ser)
        if payload is None:
            return 0
        _emit(payload, as_json=args.as_json)
        return 0
    except TimeoutError as exc:
        print(f"ERROR: Timeout while communicating with FASTRAK: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            ser.close()
        except Exception:
            pass


def _emit(payload: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2))
        return

    if isinstance(payload, (dict, list)):
        print(json.dumps(payload, indent=2))
        return

    print(payload)


def _handle_status(args: argparse.Namespace, ser) -> dict[str, Any]:
    read_settings.ensure_ascii_and_quiet(ser)
    system = read_settings.query_system(ser)
    return {"system": system}


def _handle_receivers(args: argparse.Namespace, ser) -> dict[str, Any]:
    read_settings.ensure_ascii_and_quiet(ser)
    active, raw = read_settings.query_active_stations(ser)
    return {
        "stations_active": active,
        "stations_active_raw": raw,
        "active_station_ids": [index + 1 for index, enabled in enumerate(active) if enabled],
    }


def _handle_station(args: argparse.Namespace, ser) -> dict[str, Any]:
    read_settings.ensure_ascii_and_quiet(ser)
    station_data = read_settings.query_station(ser, args.id)
    return {"station": station_data}


def _handle_dump_settings(args: argparse.Namespace, ser) -> dict[str, Any]:
    read_settings.ensure_ascii_and_quiet(ser)

    data: dict[str, Any] = {
        "serial_port": args.port,
        "serial_baud": args.baud,
        "system": read_settings.query_system(ser),
    }

    active, l_raw = read_settings.query_active_stations(ser)
    data["stations_active_raw"] = l_raw
    data["stations_active"] = active

    stations: dict[str, Any] = {}
    for index in range(1, 5):
        if active[index - 1]:
            stations[str(index)] = read_settings.query_station(ser, index)
        else:
            stations[str(index)] = {"station": index, "active": False}
    data["stations"] = stations

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(data, indent=2), encoding="utf-8")

    return data


def _handle_apply_settings(args: argparse.Namespace, ser) -> dict[str, Any]:
    data = json.loads(args.from_file.read_text(encoding="utf-8"))
    return read_settings.apply_settings(ser, data)


def _handle_set_units(args: argparse.Namespace, ser) -> dict[str, Any]:
    read_settings.ensure_ascii_and_quiet(ser)
    command = "u" if args.units == "cm" else "U"
    response = read_settings.send_cmd(ser, command, tries=1, read_timeout=0.5)
    return {"command": command, "units": args.units, "response": response}


def _handle_prepare(args: argparse.Namespace, ser) -> dict[str, Any]:
    read_settings.ensure_ascii_and_quiet(ser)
    read_settings.send_cmd(ser, "W", tries=1, read_timeout=0.5)
    read_settings.send_cmd(ser, "u", tries=1, read_timeout=0.5)

    active, raw = read_settings.query_active_stations(ser)
    return {
        "prepared": True,
        "units": "cm",
        "stations_active": active,
        "stations_active_raw": raw,
    }


def _handle_send_raw(args: argparse.Namespace, ser) -> dict[str, Any]:
    normalized = _normalize_raw_command(args.raw_command)
    if args.prepare:
        read_settings.ensure_ascii_and_quiet(ser)
    response = read_settings.send_cmd(
        ser,
        normalized,
        expect=args.expect,
        tries=1,
        read_timeout=args.read_timeout,
    )
    if args.expect is None and not args.all_lines and isinstance(response, list):
        response = _prefer_matching_lines(response, normalized)

    result: dict[str, Any] = {
        "command_input": args.raw_command,
        "command_sent": _display_command(normalized),
        "expect": args.expect,
        "response": response,
        "diagnostics": read_settings._classify_response(response),
    }
    return result


def _handle_stream(args: argparse.Namespace, ser) -> dict[str, Any]:
    if not args.no_prepare:
        read_settings.ensure_ascii_and_quiet(ser)

    if args.metric:
        read_settings.send_cmd(ser, "u", tries=1, read_timeout=0.3)

    ser.reset_input_buffer()
    if args.continuous:
        ser.write(b"C\r")
        ser.flush()

    start_time = time.time()
    deadline = start_time + args.duration if args.duration and args.duration > 0 else None
    total_lines = 0
    sample_lines = 0
    station_ids: set[int] = set()
    first_line_at: float | None = None
    interrupted = False
    idle_notice_shown = False

    try:
        while True:
            if deadline is not None and time.time() >= deadline:
                break

            raw = ser.readline()
            if not raw:
                if not idle_notice_shown and first_line_at is None and time.time() - start_time >= max(args.timeout * 2.0, 2.0):
                    mode_hint = "continuous output is off, so try clicking the pen" if not args.continuous else "check continuous output, active stations, and pen clicks"
                    print(
                        f"No FASTRAK sample lines received yet; {mode_hint}.",
                        file=sys.stderr,
                    )
                    idle_notice_shown = True
                continue

            text = raw.decode("ascii", errors="ignore").strip()
            if not text:
                continue

            first_line_at = first_line_at or time.time()
            total_lines += 1

            parsed = _parse_stream_sample(text)
            if parsed is not None:
                sample_lines += 1
                station_id = parsed.get("station_id")
                if isinstance(station_id, int):
                    station_ids.add(station_id)

            if args.parsed:
                print(json.dumps(parsed if parsed is not None else {"sample": False, "raw": text}))
            else:
                print(text)
            sys.stdout.flush()

            if args.max_lines and total_lines >= args.max_lines:
                break
    except KeyboardInterrupt:
        interrupted = True
    finally:
        if args.continuous:
            try:
                read_settings.send_cmd(ser, "c", tries=1, read_timeout=0.2)
            except Exception:
                pass

    return {
        "streaming_started": total_lines > 0,
        "interrupted": interrupted,
        "duration_seconds": round(time.time() - start_time, 3),
        "lines_received": total_lines,
        "sample_lines": sample_lines,
        "non_sample_lines": total_lines - sample_lines,
        "stations_seen": sorted(station_ids),
        "hint": (
            "No sample lines were received. Check whether the FASTRAK entered continuous output, whether stations are active, and whether pen clicks produce records."
            if sample_lines == 0
            else None
        ),
    }


def _normalize_raw_command(command: str) -> str:
    text = command.strip()
    if len(text) == 2 and text.startswith("^"):
        return chr(ord(text[1].upper()) - 64)
    return text


def _display_command(command: str) -> str:
    if len(command) == 1 and ord(command) < 32:
        return "^" + chr(ord(command) + 64)
    return command


def _prefer_matching_lines(lines: list[str], command: str) -> list[str]:
    if not lines:
        return lines

    if len(command) == 1 and ord(command) < 32:
        return lines

    tag = command[0]
    pattern = re.compile(read_settings._tag_expect_pattern(tag), re.IGNORECASE)
    matching = [line for line in lines if pattern.search(line)]
    return matching if matching else lines


def _parse_stream_sample(line: str) -> dict[str, Any] | None:
    try:
        header = int(line[0:2].strip())
        x = float(line[3:10].strip())
        y = float(line[10:17].strip())
        z = float(line[17:24].strip())
        azimuth = float(line[24:31].strip())
        elevation = float(line[31:38].strip())
        roll = float(line[38:46].strip())
    except Exception:
        return None

    station_id = header % 10
    if station_id not in {1, 2, 3, 4}:
        station_id = None

    return {
        "sample": True,
        "raw": line,
        "header": header,
        "station_id": station_id,
        "x": x,
        "y": y,
        "z": z,
        "azimuth": azimuth,
        "elevation": elevation,
        "roll": roll,
    }
