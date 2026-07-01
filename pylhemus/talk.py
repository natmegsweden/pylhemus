from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

from . import read_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pylhemus talk",
        description="Friendly FASTRAK command interface.",
    )
    parser.add_argument("--port", required=True, help="Serial port (for example COM3 or /dev/ttyUSB0)")
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

    set_units_parser = subparsers.add_parser("set-units", help="Set conversion units")
    set_units_parser.add_argument("units", choices=["cm", "in"], help="Target units")
    set_units_parser.set_defaults(handler=_handle_set_units)

    prepare_parser = subparsers.add_parser("prepare", help="Run basic prepare sequence (ASCII + defaults + metric)")
    prepare_parser.set_defaults(handler=_handle_prepare)

    raw_parser = subparsers.add_parser("send-raw", help="Send a raw FASTRAK command")
    raw_parser.add_argument("raw_command", help="Command text, for example S, X, l1, H1, ^S")
    raw_parser.add_argument("--expect", help="Optional regex expected in response")
    raw_parser.add_argument(
        "--all-lines",
        action="store_true",
        help="Return all received lines instead of preferring command-matching lines",
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
    response = read_settings.send_cmd(
        ser,
        normalized,
        expect=args.expect,
        tries=1,
        read_timeout=args.read_timeout,
    )
    if args.expect is None and not args.all_lines and isinstance(response, list):
        response = _prefer_matching_lines(response, normalized)

    diagnostics = _build_raw_diagnostics(response)

    result: dict[str, Any] = {
        "command_input": args.raw_command,
        "command_sent": _display_command(normalized),
        "expect": args.expect,
        "response": response,
    }
    if diagnostics is not None:
        result["diagnostics"] = diagnostics
    return result


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
    pattern = re.compile(rf"^\s*\d+\s*{re.escape(tag)}", re.IGNORECASE)
    matching = [line for line in lines if pattern.search(line)]
    return matching if matching else lines


def _build_raw_diagnostics(response: str | list[str]) -> dict[str, Any] | None:
    lines = response if isinstance(response, list) else [response]
    error_lines = [line for line in lines if "E*ERROR" in line]
    if not error_lines:
        return None

    first = error_lines[0]
    code_match = re.search(r"\bEC\s*(-?\d+)\b", first)
    error_code = int(code_match.group(1)) if code_match else None

    diagnostics: dict[str, Any] = {
        "error": True,
        "error_code": error_code,
        "error_lines": error_lines,
    }

    if error_code == -99:
        diagnostics["hint"] = (
            "Device rejected the command (unsupported in current firmware/mode or invalid syntax). "
            "On this FASTRAK, read/query commands may work while some write/config commands are not accepted."
        )
    else:
        diagnostics["hint"] = "Device returned a FASTRAK error line; check command syntax and device mode."

    return diagnostics
