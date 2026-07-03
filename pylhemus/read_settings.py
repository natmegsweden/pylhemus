from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import serial


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read FASTRAK settings and print or save JSON.")
    parser.add_argument("--port", required=True, help="Serial port (e.g., COM3 or /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=9600, help="Baud rate (default: 9600)")
    parser.add_argument("--out", type=Path, help="Optional output JSON file path")
    parser.add_argument("--timeout", type=float, default=1.0, help="Serial read timeout (s)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        ser = open_port(args.port, args.baud, timeout=args.timeout)
    except Exception as exc:
        print(f"ERROR: Could not open port {args.port} @ {args.baud}: {exc}", file=sys.stderr)
        return 2

    try:
        ensure_ascii_and_quiet(ser)

        data = {
            "collected_at_utc": datetime.utcnow().isoformat() + "Z",
            "serial_port": args.port,
            "serial_baud": args.baud,
            "system": query_system(ser),
        }

        active, l_raw = query_active_stations(ser)
        data["stations_active_raw"] = l_raw
        data["stations_active"] = active

        data["stations"] = {}
        for index in range(1, 5):
            if active[index - 1]:
                try:
                    data["stations"][str(index)] = query_station(ser, index)
                except TimeoutError as exc:
                    data["stations"][str(index)] = {"station": index, "error": str(exc)}
                except Exception as exc:
                    data["stations"][str(index)] = {"station": index, "error": repr(exc)}
            else:
                data["stations"][str(index)] = {"station": index, "active": False}

        json_text = json.dumps(data, indent=2)
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json_text, encoding="utf-8")
            print(f"Saved settings to {args.out}")
        else:
            print(json_text)
        return 0
    finally:
        try:
            ser.close()
        except Exception:
            pass


def open_port(port: str, baud: int, timeout: float = 1.0) -> serial.Serial:
    ser = serial.Serial(
        port=port,
        baudrate=baud,
        stopbits=serial.STOPBITS_ONE,
        parity=serial.PARITY_NONE,
        bytesize=serial.EIGHTBITS,
        rtscts=False,
        timeout=timeout,
        write_timeout=1,
        xonxoff=False,
    )
    time.sleep(0.2)
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    return ser


def _split_fastrak_line(line: str) -> list[str]:
    if "*" not in line:
        return [line]
    return [fragment.strip() for fragment in line.split("*") if fragment.strip()]


def _tag_expect_pattern(tag: str) -> str:
    return rf"^(?:\s*\d+\s*)?{re.escape(tag)}"


def _payload_after_tag(line: str, tag: str) -> str:
    match = re.search(_tag_expect_pattern(tag), line)
    if not match:
        return line.strip()
    return line[match.end() :].strip()


def _system_toggle_cmds(flags: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(flags, dict):
        return {}

    return {
        "output_format": {
            "cmd": "F" if flags.get("output_format") == "ASCII" else "f",
            "value": flags.get("output_format"),
        },
        "units": {
            "cmd": "u" if flags.get("units") == "Centimeters" else "U",
            "value": flags.get("units"),
        },
        "compensation": {
            "cmd": "D" if flags.get("compensation") else "d",
            "value": flags.get("compensation"),
        },
        "continuous_mode": {
            "cmd": "C" if flags.get("continuous_mode") else "c",
            "value": flags.get("continuous_mode"),
        },
    }


def _floats_to_cmd(tag: str, values: float | int | list[float] | tuple[float, ...] | None) -> str | None:
    if values is None:
        return None

    if isinstance(values, (int, float)):
        float_values = [float(values)]
    else:
        float_values = [float(value) for value in values]

    if not float_values:
        return None
    return tag + "," + ",".join(f"{value:.6g}" for value in float_values)


def _ints_to_cmd(tag: str, values: list[int] | None) -> str | None:
    if not values:
        return None
    return tag + "," + ",".join(str(value) for value in values)


def _filter_restore_cmd(tag: str, vals: dict[str, float] | None) -> str | None:
    if vals is None:
        return None
    return _floats_to_cmd(tag, [vals["F"], vals["FLOW"], vals["FHIGH"], vals["FACTOR"]])


def _classify_response(response: str | list[str]) -> dict[str, Any]:
    if isinstance(response, list):
        lines = [line for line in response if line]
    elif response:
        lines = [response]
    else:
        lines = []

    if not lines:
        return {"outcome": "no_response", "error": False}

    error_lines = [line for line in lines if re.search(r"ERROR", line)]
    error_code_line = next((line for line in lines if re.search(r"\bEC\s*-?\d+\b", line)), None)
    if error_lines or error_code_line:
        code_source = error_code_line or error_lines[0]
        code_match = re.search(r"\bEC\s*(-?\d+)\b", code_source)
        error_code = int(code_match.group(1)) if code_match else None
        related_lines = error_lines.copy()
        if error_code_line and error_code_line not in related_lines:
            related_lines.append(error_code_line)

        hint = (
            "Device rejected the command (unsupported in current firmware/mode or invalid syntax). "
            "On this FASTRAK, read/query commands may work while some write/config commands are not accepted."
            if error_code == -99
            else "Device returned a FASTRAK error line; check command syntax and device mode."
        )
        return {
            "outcome": "rejected",
            "error": True,
            "error_code": error_code,
            "error_lines": related_lines,
            "hint": hint,
        }

    return {"outcome": "accepted", "error": False}


def send_cmd(
    ser: serial.Serial,
    cmd: str,
    expect=None,
    tries: int = 3,
    read_timeout: float = 1.0,
    settle: float = 0.15,
):
    # FASTRAK control commands (for example ^S/^Q) are single control bytes and
    # should be sent without a trailing carriage return.
    is_control = len(cmd) == 1 and ord(cmd) < 32
    if is_control:
        full = cmd
    else:
        full = cmd + "\r"
    last_exc = None
    lines: list[str] = []
    for _ in range(tries):
        try:
            ser.reset_input_buffer()
            ser.write(full.encode("ascii"))
            ser.flush()
            if not is_control and tries == 1:
                time.sleep(settle)
                if ser.in_waiting == 0:
                    return []
            lines = []
            start = time.time()
            while time.time() - start < read_timeout:
                line = ser.readline()
                if not line:
                    continue
                try:
                    text = line.decode("ascii", errors="ignore").strip()
                except UnicodeDecodeError:
                    text = line.decode("latin1", errors="ignore").strip()
                if not text:
                    continue
                fragments = _split_fastrak_line(text)
                if not fragments:
                    continue
                lines.extend(fragments)
                if expect:
                    for fragment in fragments:
                        if re.search(expect, fragment):
                            return fragment
            if expect:
                continue
            return lines
        except Exception as exc:
            last_exc = exc
            time.sleep(0.05)
    if expect:
        raise TimeoutError(
            f"Command '{cmd}' did not return a line matching {expect!r} in time. "
            f"Last lines received: {lines}"
        ) from last_exc
    return []


def ensure_ascii_and_quiet(ser: serial.Serial):
    for command in ["\x13", "c", "F"]:
        try:
            send_cmd(ser, command, tries=1, read_timeout=0.3)
        except Exception:
            pass
    time.sleep(0.1)


def parse_S_record(s_line: str):
    out = {"raw": s_line}
    after_S = _payload_after_tag(s_line, "S") if s_line else ""
    if after_S:
        hex_flags = after_S[:3]
        out["flags_hex"] = hex_flags
        try:
            flags_val = int(hex_flags, 16)
        except ValueError:
            flags_val = None

        if flags_val is not None:
            out["flags"] = {
                "output_format": "Binary" if (flags_val & (1 << 0)) else "ASCII",
                "units": "Centimeters" if (flags_val & (1 << 1)) else "Inches",
                "compensation": bool(flags_val & (1 << 2)),
                "continuous_mode": bool(flags_val & (1 << 3)),
            }

        rest = after_S[3:]
        out["bit_error_code_raw"] = rest[:3]

        match = re.search(r"\b([0-9A-F]{2})\b\s+([^\s])", rest[3:].strip())
        if match:
            out["id_tag"] = match.group(1)
            out["sensor_map_raw"] = match.group(2)

        version_match = re.search(r"(\d+\.\d+\.\d+|\d+\.\d+)", s_line)
        if version_match:
            out["firmware_version"] = version_match.group(1)
    return out


def parse_vector_triplet_fields(payload: str, count=3):
    tokens = payload.replace(",", " ").split()
    floats = []
    for token in tokens[:count]:
        try:
            floats.append(float(token))
        except Exception:
            pass
    if len(floats) == count:
        return floats
    return None


def query_simple_value(ser: serial.Serial, cmd: str, expect_tag: str, parser=float, fallback=None):
    line = send_cmd(ser, cmd, expect=_tag_expect_pattern(expect_tag), read_timeout=0.8)
    if not line:
        return fallback, None
    value = None
    try:
        payload = _payload_after_tag(line, expect_tag)
        numbers = re.findall(r"[-+]?\d+\.\d+|[-+]?\d+", payload)
        if numbers:
            if parser is float:
                value = [float(item) for item in numbers]
            elif parser is int:
                value = [int(item) for item in numbers]
            else:
                value = numbers
            if len(value) == 1:
                value = value[0]
    except Exception:
        value = fallback
    return value, line


def query_station_list_ints(ser: serial.Serial, cmd: str, expect_tag: str):
    line = send_cmd(ser, cmd, expect=_tag_expect_pattern(expect_tag), read_timeout=0.8)
    if not line:
        return None, None
    payload = _payload_after_tag(line, expect_tag)
    ids = re.findall(r"\b(\d{1,3})\b", payload)
    return [int(item) for item in ids] if ids else [], line


def query_filters(ser: serial.Serial):
    v_vals, v_raw = query_simple_value(ser, "v", "v", parser=float, fallback=None)
    x_vals, x_raw = query_simple_value(ser, "x", "x", parser=float, fallback=None)

    def to_named(values):
        if isinstance(values, list) and len(values) >= 4:
            frequency, low, high, factor = values[:4]
            return dict(F=frequency, FLOW=low, FHIGH=high, FACTOR=factor)
        return None

    return {
        "attitude": to_named(v_vals) if v_vals else None,
        "attitude_raw": v_raw,
        "attitude_cmd": _filter_restore_cmd("v", to_named(v_vals) if v_vals else None),
        "position": to_named(x_vals) if x_vals else None,
        "position_raw": x_raw,
        "position_cmd": _filter_restore_cmd("x", to_named(x_vals) if x_vals else None),
    }


def query_system(ser: serial.Serial):
    sys_info = {}

    s_line = send_cmd(ser, "S", expect=_tag_expect_pattern("S"), read_timeout=2)
    sys_info["status"] = parse_S_record(s_line) if s_line else None
    toggles = _system_toggle_cmds(sys_info["status"].get("flags") if sys_info["status"] else None)
    if toggles:
        sys_info["toggles"] = toggles

    x_line = send_cmd(ser, "X", expect=_tag_expect_pattern("X"), read_timeout=10)
    if x_line:
        sys_info["config_string_raw"] = x_line
        try:
            idx = x_line.index("X")
            config_string = x_line[idx + 1 :].strip()
        except ValueError:
            config_string = x_line
        sys_info["config_string"] = config_string
    else:
        sys_info["config_string_raw"] = None
        sys_info["config_string"] = None

    y_line = send_cmd(ser, "y", expect=_tag_expect_pattern("y"), read_timeout=0.8)
    if y_line:
        mode_map = {"0": "Internal", "1": "External", "2": "Video"}
        mode_digit = _payload_after_tag(y_line, "y")[:1]
        sys_info["sync_mode"] = mode_map.get(mode_digit)
        sys_info["sync_mode_raw"] = y_line
        sys_info["sync_mode_annotated"] = (
            {"cmd": f"y {mode_digit}", "value": sys_info["sync_mode"]} if mode_digit in mode_map else None
        )
    else:
        sys_info["sync_mode"] = None
        sys_info["sync_mode_raw"] = None
        sys_info["sync_mode_annotated"] = None

    sys_info["filters"] = query_filters(ser)
    return sys_info


def query_active_stations(ser: serial.Serial):
    line = send_cmd(ser, "l1", expect=_tag_expect_pattern("l"), read_timeout=0.8)
    active = [False, False, False, False]
    if line:
        payload = _payload_after_tag(line, "l")
        values = re.findall(r"[01]", payload)
        ones = [int(value) for value in values[:4]] if len(values) >= 4 else []
        for index, value in enumerate(ones[:4]):
            active[index] = bool(value)
    return active, line


def query_station(ser: serial.Serial, station_index: int):
    station = str(station_index)
    result = {"station": station_index}

    h_line = send_cmd(ser, f"H{station}", expect=_tag_expect_pattern("H"), read_timeout=0.8)
    result["hemisphere_raw"] = h_line
    result["hemisphere_vector"] = parse_vector_triplet_fields(_payload_after_tag(h_line, "H"), 3) if h_line else None
    result["hemisphere_cmd"] = _floats_to_cmd(f"H{station}", result["hemisphere_vector"])

    a_line = send_cmd(ser, f"A{station}", expect=_tag_expect_pattern("A"), read_timeout=0.8)
    result["alignment_raw"] = a_line
    values = re.findall(r"[-+]?\d+\.\d+|[-+]?\d+", _payload_after_tag(a_line, "A") if a_line else "")
    result["alignment"] = None
    if values and len(values) >= 9:
        numbers = list(map(float, values[:9]))
        result["alignment"] = {
            "origin": numbers[0:3],
            "x_axis_point": numbers[3:6],
            "y_axis_point": numbers[6:9],
        }
    result["alignment_cmd"] = _floats_to_cmd(
        f"A{station}",
        (
            result["alignment"]["origin"]
            + result["alignment"]["x_axis_point"]
            + result["alignment"]["y_axis_point"]
        )
        if result["alignment"]
        else None,
    )

    g_vals, g_raw = query_simple_value(ser, f"G{station}", "G", parser=float, fallback=None)
    result["boresight_reference_raw"] = g_raw
    result["boresight_reference_angles"] = g_vals[:3] if isinstance(g_vals, list) else None
    result["boresight_reference_cmd"] = _floats_to_cmd(f"G{station}", result["boresight_reference_angles"])

    i_vals, i_raw = query_simple_value(ser, f"I{station}", "I", parser=float, fallback=None)
    result["increment_raw"] = i_raw
    if isinstance(i_vals, list):
        result["increment_distance"] = i_vals[0] if i_vals else None
    else:
        result["increment_distance"] = i_vals
    result["increment_cmd"] = _floats_to_cmd(f"I{station}", result["increment_distance"])

    o_list, o_raw = query_station_list_ints(ser, f"O{station}", "O")
    result["output_data_list_raw"] = o_raw
    result["output_data_list_ids"] = o_list
    result["output_data_list_cmd"] = _ints_to_cmd(f"O{station}", o_list)

    v_vals, v_raw = query_simple_value(ser, f"V{station}", "V", parser=float, fallback=None)
    result["position_envelope_raw"] = v_raw
    if isinstance(v_vals, list) and len(v_vals) >= 6:
        result["position_envelope"] = {
            "x_max": v_vals[0],
            "y_max": v_vals[1],
            "z_max": v_vals[2],
            "x_min": v_vals[3],
            "y_min": v_vals[4],
            "z_min": v_vals[5],
        }
    else:
        result["position_envelope"] = None
    result["position_envelope_cmd"] = _floats_to_cmd(
        f"V{station}",
        [
            result["position_envelope"]["x_max"],
            result["position_envelope"]["y_max"],
            result["position_envelope"]["z_max"],
            result["position_envelope"]["x_min"],
            result["position_envelope"]["y_min"],
            result["position_envelope"]["z_min"],
        ]
        if result["position_envelope"]
        else None,
    )

    q_vals, q_raw = query_simple_value(ser, f"Q{station}", "Q", parser=float, fallback=None)
    result["angular_envelope_raw"] = q_raw
    if isinstance(q_vals, list) and len(q_vals) >= 6:
        result["angular_envelope"] = {
            "az_max": q_vals[0],
            "el_max": q_vals[1],
            "rl_max": q_vals[2],
            "az_min": q_vals[3],
            "el_min": q_vals[4],
            "rl_min": q_vals[5],
        }
    else:
        result["angular_envelope"] = None
    result["angular_envelope_cmd"] = _floats_to_cmd(
        f"Q{station}",
        [
            result["angular_envelope"]["az_max"],
            result["angular_envelope"]["el_max"],
            result["angular_envelope"]["rl_max"],
            result["angular_envelope"]["az_min"],
            result["angular_envelope"]["el_min"],
            result["angular_envelope"]["rl_min"],
        ]
        if result["angular_envelope"]
        else None,
    )

    r_vals, r_raw = query_simple_value(ser, f"r{station}", "r", parser=float, fallback=None)
    result["transmitter_mounting_raw"] = r_raw
    result["transmitter_mounting_AER"] = r_vals[:3] if isinstance(r_vals, list) else None
    result["transmitter_mounting_cmd"] = _floats_to_cmd(f"r{station}", result["transmitter_mounting_AER"])

    n_vals, n_raw = query_simple_value(ser, f"N{station}", "N", parser=float, fallback=None)
    result["tip_offsets_raw"] = n_raw
    result["tip_offsets"] = n_vals[:3] if isinstance(n_vals, list) else None
    result["tip_offsets_cmd"] = _floats_to_cmd(f"N{station}", result["tip_offsets"])

    return result


def apply_settings(ser: serial.Serial, data: dict[str, Any]) -> dict[str, Any]:
    ensure_ascii_and_quiet(ser)

    commands: list[str | None] = []
    system = data.get("system") or {}
    toggles = system.get("toggles") or {}
    for key in ("output_format", "units", "compensation", "continuous_mode"):
        record = toggles.get(key)
        commands.append(record.get("cmd") if isinstance(record, dict) else None)

    sync_mode = system.get("sync_mode_annotated")
    commands.append(sync_mode.get("cmd") if isinstance(sync_mode, dict) else None)

    filters = system.get("filters") or {}
    commands.append(filters.get("attitude_cmd") if isinstance(filters, dict) else None)
    commands.append(filters.get("position_cmd") if isinstance(filters, dict) else None)

    target_active, _ = query_active_stations(ser)
    station_fields = [
        "hemisphere_cmd",
        "alignment_cmd",
        "boresight_reference_cmd",
        "increment_cmd",
        "output_data_list_cmd",
        "position_envelope_cmd",
        "angular_envelope_cmd",
        "transmitter_mounting_cmd",
        "tip_offsets_cmd",
    ]
    stations = data.get("stations") or {}
    for station_index in range(1, 5):
        if not target_active[station_index - 1]:
            continue
        station_data = stations.get(str(station_index))
        if not isinstance(station_data, dict):
            continue
        for field in station_fields:
            commands.append(station_data.get(field))

    report = []
    applied = 0
    skipped = 0
    for cmd in commands:
        if cmd is None or not str(cmd).strip():
            skipped += 1
            continue

        try:
            response = send_cmd(ser, cmd, tries=1, read_timeout=0.5)
            diagnostics = _classify_response(response)
            entry = {
                "cmd": cmd,
                "outcome": diagnostics["outcome"],
                "error": diagnostics["error"],
            }
            if "error_code" in diagnostics:
                entry["error_code"] = diagnostics["error_code"]
            report.append(entry)
        except Exception as exc:
            report.append({"cmd": cmd, "outcome": "rejected", "error": True, "exception": repr(exc)})
        finally:
            applied += 1

    return {"applied": applied, "skipped": skipped, "report": report}
