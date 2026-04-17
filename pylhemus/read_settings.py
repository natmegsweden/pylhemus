from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Sequence

import serial


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read FASTRAK settings and save to JSON.")
    parser.add_argument("--port", required=True, help="Serial port (e.g., COM3 or /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=9600, help="Baud rate (default: 9600)")
    parser.add_argument("--out", required=True, type=Path, help="Output JSON file path")
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

        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"Saved settings to {args.out}")
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


def send_cmd(ser: serial.Serial, cmd: str, expect=None, tries: int = 3, read_timeout: float = 1.0):
    full = cmd + "\r"
    last_exc = None
    lines: list[str] = []
    for _ in range(tries):
        try:
            ser.reset_input_buffer()
            ser.write(full.encode("ascii"))
            ser.flush()
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
                lines.append(text)
                if expect and re.search(expect, text):
                    return text
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
    parts = s_line.split()
    if len(parts) >= 3 and parts[2].endswith("S"):
        after_S = s_line.split("S", 1)[1].strip()
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
    line = send_cmd(ser, cmd, expect=expect_tag, read_timeout=0.8)
    if not line:
        return fallback, None
    value = None
    try:
        numbers = re.findall(r"[-+]?\d+\.\d+|[-+]?\d+", line)
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
    line = send_cmd(ser, cmd, expect=expect_tag, read_timeout=0.8)
    if not line:
        return None, None
    ids = re.findall(r"\b(\d{1,3})\b", line)
    try:
        pos = line.index(expect_tag)
        ids = re.findall(r"\b(\d{1,3})\b", line[pos + 1 :])
    except ValueError:
        pass
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
        "position": to_named(x_vals) if x_vals else None,
        "position_raw": x_raw,
    }


def query_system(ser: serial.Serial):
    sys_info = {}

    s_line = send_cmd(ser, "S", expect="S", read_timeout=2)
    sys_info["status"] = parse_S_record(s_line) if s_line else None

    x_line = send_cmd(ser, "X", expect=r"X", read_timeout=10)
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

    y_line = send_cmd(ser, "y", expect="y", read_timeout=0.8)
    if y_line:
        match = re.search(r"\by\b\s+([0-2])", y_line)
        if match:
            mode_map = {"0": "Internal", "1": "External", "2": "Video"}
            sys_info["sync_mode"] = mode_map.get(match.group(1), match.group(1))
        else:
            sys_info["sync_mode"] = None
        sys_info["sync_mode_raw"] = y_line
    else:
        sys_info["sync_mode"] = None
        sys_info["sync_mode_raw"] = None

    sys_info["filters"] = query_filters(ser)
    return sys_info


def query_active_stations(ser: serial.Serial):
    line = send_cmd(ser, "l1", expect="l", read_timeout=0.8)
    active = [False, False, False, False]
    if line:
        values = re.findall(r"\b[01]\b", line)
        ones = [int(value) for value in values[-4:]] if len(values) >= 4 else []
        for index, value in enumerate(ones[:4]):
            active[index] = bool(value)
    return active, line


def query_station(ser: serial.Serial, station_index: int):
    station = str(station_index)
    result = {"station": station_index}

    h_line = send_cmd(ser, f"H{station}", expect="H", read_timeout=0.8)
    result["hemisphere_raw"] = h_line
    result["hemisphere_vector"] = parse_vector_triplet_fields(h_line, 3) if h_line else None

    a_line = send_cmd(ser, f"A{station}", expect="A", read_timeout=0.8)
    result["alignment_raw"] = a_line
    values = re.findall(r"[-+]?\d+\.\d+|[-+]?\d+", a_line or "")
    result["alignment"] = None
    if values and len(values) >= 9:
        numbers = list(map(float, values[:9]))
        result["alignment"] = {
            "origin": numbers[0:3],
            "x_axis_point": numbers[3:6],
            "y_axis_point": numbers[6:9],
        }

    g_vals, g_raw = query_simple_value(ser, f"G{station}", "G", parser=float, fallback=None)
    result["boresight_reference_raw"] = g_raw
    result["boresight_reference_angles"] = g_vals[:3] if isinstance(g_vals, list) else None

    i_vals, i_raw = query_simple_value(ser, f"I{station}", "I", parser=float, fallback=None)
    result["increment_raw"] = i_raw
    result["increment_distance"] = i_vals[0] if isinstance(i_vals, list) and i_vals else None

    o_list, o_raw = query_station_list_ints(ser, f"O{station}", "O")
    result["output_data_list_raw"] = o_raw
    result["output_data_list_ids"] = o_list

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

    r_vals, r_raw = query_simple_value(ser, f"r{station}", "r", parser=float, fallback=None)
    result["transmitter_mounting_raw"] = r_raw
    result["transmitter_mounting_AER"] = r_vals[:3] if isinstance(r_vals, list) else None

    n_vals, n_raw = query_simple_value(ser, f"N{station}", "N", parser=float, fallback=None)
    result["tip_offsets_raw"] = n_raw
    result["tip_offsets"] = n_vals[:3] if isinstance(n_vals, list) else None

    return result