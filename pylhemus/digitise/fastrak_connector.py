import serial
import time
import numpy as np
import re
import os


class FastrakConnector:
    def __init__(
        self,
        usb_port: str,
        stylus_receiver:int=0,
        head_reference:int=1,
        data_length:int=47,
        hemisphere=(0.0, 0.0, 1.0),
        baud_rate:int=9600,
        units:str="cm",
        metal_compensation:bool=True,
        set_factory_defaults:bool=True,
    ):
        """
        A class to interface with the Polhemus FASTRAK system.

        Args:
            usb_port (str): The USB port to which the Polhemus FASTRAK is connected.
            stylus_receiver (int): The receiver port number for the stylus (default is 0).
            head_reference (int): The receiver port number for the head reference (default is 1).
            data_length (int): The expected length of data for each receiver reading.
            baud_rate (int): Serial baud rate (default is 9600).
            units (str): Output units, either "cm" (metric) or "inch" (imperial). Default is "cm".
            metal_compensation (bool): Enable metal compensation on startup (default is True).
            set_factory_defaults (bool): Reset device to factory software defaults on startup (default is True).

        Methods:
            n_receivers(): Queries the number of active receivers.
            set_factory_software_defaults(): Resets the device to factory defaults.
            clear_old_data(): Clears outdated data from the serial buffer.
            set_units(): Configures the device output units based on the units setting.
            prepare_for_digitisation(): Prepares the device for digitisation use.
            get_position_relative_to_head_receiver(): Computes the position from the stylus relative to the head receiver.
        """
        self.stylus_receiver = stylus_receiver
        self.head_reference = head_reference
        self.data_length = data_length
        self.n_receivers = 0
        self.debug_serial = os.getenv("PYLHEMUS_DEBUG_SERIAL", "").lower() in {"1", "true", "yes", "on"}
        self.hemisphere = self._normalize_hemisphere(hemisphere)
        self.startup_warnings: list[str] = []
        self.units = units.lower() if units else "cm"
        self.metal_compensation_enabled = metal_compensation
        self.set_factory_defaults_enabled = set_factory_defaults

        # initialize serial object
        self.serialobj = serial.Serial(
            port=usb_port,  # Port name (adjust as necessary)
            baudrate=baud_rate,  # Baud rate
            stopbits=serial.STOPBITS_ONE,  # Stop bits (1 stop bit)
            parity=serial.PARITY_NONE,  # No parity
            bytesize=serial.EIGHTBITS,  # 8 data bits
            rtscts=False,  # No hardware flow control
            timeout=1,  # Read timeout in seconds
            write_timeout=1,  # Write timeout in seconds
            xonxoff=False,  # No software flow control
        )

    def send_serial_command(self, command:bytes, sleep_time:float=0.1, read_timeout:float=0.0):
        if self.debug_serial:
            cmd_text = command.decode(errors="ignore").replace("\r", "\\r").replace("\n", "\\n")
            print(f"[FASTRAK CMD] {cmd_text}")

        try:
            self.serialobj.write(command)
            time.sleep(sleep_time)
        except serial.SerialTimeoutException:
            print("Serial write timeout occurred.")
        except serial.SerialException as e:
            print(f"Serial communication error: {e}")

        lines: list[str] = []
        if read_timeout > 0:
            end_time = time.time() + read_timeout
            while time.time() < end_time:
                if self.serialobj.in_waiting <= 0:
                    time.sleep(0.01)
                    continue
                line = self.serialobj.readline().decode(errors="ignore").strip()
                if line:
                    lines.append(line)

        if self.debug_serial:
            for line in lines:
                print(f"[FASTRAK RESP] {line}")

        return lines

    @staticmethod
    def _normalize_hemisphere(hemisphere):
        if hemisphere is None:
            return None
        if not isinstance(hemisphere, (list, tuple)) or len(hemisphere) != 3:
            raise ValueError("FASTRAK hemisphere must be a 3-value list or tuple.")

        values = tuple(float(value) for value in hemisphere)
        if np.linalg.norm(values) <= 1e-9:
            raise ValueError("FASTRAK hemisphere vector must have non-zero length.")
        return values

    @staticmethod
    def _format_station_write(tag: str, station: int, values) -> bytes:
        payload = ",".join(f"{float(value):.6g}" for value in values)
        return f"{tag}{station},{payload}\r".encode()

    @staticmethod
    def _extract_error_code(lines: list[str]) -> int | None:
        for line in lines:
            match = re.search(r"\bEC\s*(-?\d+)\b", line)
            if match:
                return int(match.group(1))
        return None

    @staticmethod
    def _has_error(lines: list[str]) -> bool:
        return any("ERROR" in line.upper() for line in lines) or FastrakConnector._extract_error_code(lines) is not None

    @staticmethod
    def _parse_numeric_values(line: str) -> list[float]:
        return [float(value) for value in re.findall(r"[-+]?\d+(?:\.\d+)?", line)]

    def _add_startup_warning(self, message: str):
        if message not in self.startup_warnings:
            self.startup_warnings.append(message)
        if self.debug_serial:
            print(f"[FASTRAK WARN] {message}")

    def _record_write_result(self, *, label: str, station: int, lines: list[str]):
        if not self._has_error(lines):
            return

        error_code = self._extract_error_code(lines)
        detail = f" (EC {error_code})" if error_code is not None else ""
        self._add_startup_warning(
            f"Failed to apply FASTRAK {label} setting for station {station}{detail}."
        )

    def _query_hemisphere(self, station: int) -> tuple[float, float, float] | None:
        lines = self.send_serial_command(f"H{station}\r".encode(), read_timeout=0.3)
        self._record_write_result(label="hemisphere readback", station=station, lines=lines)
        for line in lines:
            if "H" not in line.upper():
                continue
            values = self._parse_numeric_values(line)
            if len(values) >= 3:
                return tuple(values[-3:])
        return None

    def query_n_receivers(self, read_timeout: float = 0.5):
        self.send_serial_command(b"P")  # Send 'P' command to request number of probes

        # Collect response lines for a short time window to avoid missing delayed lines.
        lines: list[str] = []
        start = time.time()
        while time.time() - start < read_timeout:
            if self.serialobj.in_waiting <= 0:
                time.sleep(0.01)
                continue
            raw = self.serialobj.readline()
            line = raw.decode(errors="ignore").strip()
            if line:
                lines.append(line)

        # Prefer counting unique station IDs when present, fallback to non-empty lines.
        station_ids: set[int] = set()
        for line in lines:
            # Typical FASTRAK records are prefixed like "21...", "22..." where
            # the second digit is the station index.
            match = re.match(r"^\s*2([1-4])", line)
            if match:
                station_ids.add(int(match.group(1)))
                continue

            # Fallback for alternative outputs that begin directly with station ID.
            match = re.match(r"^\s*([1-4])", line)
            if match:
                station_ids.add(int(match.group(1)))

        counted = len(station_ids) if station_ids else len(lines)

        # FASTRAK digitisation workflow requires stylus + head reference.
        # Many setups return no probe list even when streaming works, so keep this
        # as best-effort and silently fall back to 2 receivers.
        if counted < 2:
            self.n_receivers = 2
            return

        # Ignore extra noise/status lines and keep the expected receiver count.
        self.n_receivers = 2

    def set_factory_software_defaults(self):
        """
        Resets the device to its factory software defaults by sending the appropriate command.
        """
        self.send_serial_command(b"W")  # Send 'W' command

    def clear_old_data(self):
        """
        Checks if there are bytes waiting in the buffer. If so it reads and discards.
        """
        while self.serialobj.in_waiting > 0:
            self.serialobj.read(self.serialobj.in_waiting)

    def set_hemisphere(self):
        if self.hemisphere is None:
            return

        x, y, z = self.hemisphere
        for station in range(1, self.n_receivers + 1):
            expected = (x, y, z)
            cmd = self._format_station_write("H", station, expected)
            lines = self.send_serial_command(cmd, read_timeout=0.2)
            self._record_write_result(label="hemisphere", station=station, lines=lines)

            actual = self._query_hemisphere(station)
            if actual is None:
                self._add_startup_warning(
                    f"Could not verify FASTRAK hemisphere for station {station} after applying settings."
                )
                continue

            if not np.allclose(actual, expected, atol=1e-3):
                self._add_startup_warning(
                    "FASTRAK hemisphere readback mismatch for station "
                    f"{station}: requested {expected}, device reported {actual}."
                )

    def metal_compensation(self):
        self.send_serial_command(b"D")  # send 'D' command to set metal compensation on

    def set_units(self):
        """Configure the device output units based on self.units.

        When units is "cm" (metric): sends `U` (inch baseline) then `u` (switch to cm)
        so the FASTRAK rescales any inch-defined envelopes before switching to metric.
        When units is "inch": sends only `U` to put the device in imperial mode.

        The identity alignment matrix extents are scaled to match the active unit:
        200 cm (~79 inches) for metric, or 79 inches for imperial.
        """
        if self.units == "cm":
            self.send_serial_command(b"U")
            self.send_serial_command(b"u")
            alignment_extent = 200  # cm
        elif self.units == "inch":
            self.send_serial_command(b"U")
            alignment_extent = 78.74  # inches (~200 cm)
        else:
            self._add_startup_warning(
                f"Unrecognised units value '{self.units}'; falling back to metric (cm)."
            )
            self.send_serial_command(b"U")
            self.send_serial_command(b"u")
            alignment_extent = 200

        for station in range(1, self.n_receivers + 1):
            cmd = self._format_station_write(
                "A", station,
                [0, 0, 0, alignment_extent, 0, 0, 0, alignment_extent, 0],
            )
            lines = self.send_serial_command(cmd, read_timeout=0.2)
            self._record_write_result(label="alignment", station=station, lines=lines)

    # Keep legacy name as an alias for backward compatibility.
    def set_metric(self):
        """Deprecated alias for set_units(). Use set_units() instead."""
        self.set_units()

    def prepare_for_digitisation(self):
        self.startup_warnings = []
        if self.set_factory_defaults_enabled:
            self.set_factory_software_defaults()
        self.clear_old_data()
        if self.metal_compensation_enabled:
            self.metal_compensation()
        self.query_n_receivers()
        self.set_units()
        self.set_hemisphere()
        self.clear_old_data()
        return list(self.startup_warnings)

    def get_position_relative_to_head_receiver(self):
        # Read line-based FASTRAK records; avoid fixed byte thresholds because
        # firmware/config can change record length and break click-triggered capture.
        sensor_data = np.zeros((7, self.n_receivers))

        j = 0
        read_start = time.time()
        while j < self.n_receivers:
            if time.time() - read_start > 2.0:
                raise RuntimeError("Timed out reading FASTRAK sample records.")

            ftstring = self.serialobj.readline().decode(errors="ignore").strip()
            if not ftstring:
                continue

            if self.debug_serial:
                print(f"[FASTRAK RAW] {ftstring}")

            try:
                header, x, y, z, azimuth, elevation, roll = self.ftformat(ftstring)
            except Exception:
                # Skip non-sample/status/error lines.
                continue

            if self.debug_serial:
                print(
                    "[FASTRAK PARSED] "
                    f"header={header} x={x:.3f} y={y:.3f} z={z:.3f} "
                    f"az={azimuth:.3f} el={elevation:.3f} roll={roll:.3f}"
                )

            sensor_data[0, j] = header
            sensor_data[1, j] = x
            sensor_data[2, j] = y
            sensor_data[3, j] = z
            sensor_data[4, j] = azimuth
            sensor_data[5, j] = elevation
            sensor_data[6, j] = roll
            j += 1

        # Get sensor position relative to head reference
        sensor_position = self.rotate_and_translate(
            sensor_data[1, self.head_reference],
            sensor_data[2, self.head_reference],
            sensor_data[3, self.head_reference],
            sensor_data[4, self.head_reference],
            sensor_data[5, self.head_reference],
            sensor_data[6, self.head_reference],
            sensor_data[1, self.stylus_receiver],
            sensor_data[2, self.stylus_receiver],
            sensor_data[3, self.stylus_receiver],
        )

        return sensor_data, sensor_position[:3]

    @staticmethod
    def rotate_and_translate(xref:float, yref:float, zref:float, azi:float, ele:float, rol:float, xraw:float, yraw:float, zraw:float):
        # Convert angles to radians
        azi = -np.deg2rad(azi)
        ele = -np.deg2rad(ele)
        rol = -np.deg2rad(rol)

        # Rotation matrix around x-axis (roll)
        rx = np.array(
            [
                [1, 0, 0, 0],
                [0, np.cos(rol), np.sin(rol), 0],
                [0, -np.sin(rol), np.cos(rol), 0],
                [0, 0, 0, 1],
            ]
        )

        # Rotation matrix around y-axis (elevation)
        ry = np.array(
            [
                [np.cos(ele), 0, -np.sin(ele), 0],
                [0, 1, 0, 0],
                [np.sin(ele), 0, np.cos(ele), 0],
                [0, 0, 0, 1],
            ]
        )

        # Rotation matrix around z-axis (azimuth)
        rz = np.array(
            [
                [np.cos(azi), np.sin(azi), 0, 0],
                [-np.sin(azi), np.cos(azi), 0, 0],
                [0, 0, 1, 0],
                [0, 0, 0, 1],
            ]
        )

        # Translation matrix
        tm = np.array([[1, 0, 0, -xref], [0, 1, 0, -yref], [0, 0, 1, -zref], [0, 0, 0, 1]])

        # Raw data as a 4x1 matrix (homogeneous coordinates)
        xyzraw = np.array([xraw, yraw, zraw, 1])

        # Translate the raw data
        xyzt = np.dot(tm, xyzraw)

        # Apply inverse rotations to align the point with the reference frame
        xyz = np.dot(rz.T, xyzt)
        xyz = np.dot(ry.T, xyz)
        xyz = np.dot(rx.T, xyz)

        return xyz[:3] 

    @staticmethod
    def ftformat(data):
        """
        Extract specific character slices from the data from the fastrak and convert them to appropriate types
        """
        
        header = int(
            data[0:2].strip()
        )

        x = float(data[3:10].strip()) 
        y = float(data[10:17].strip())
        z = float(data[17:24].strip())

        azimuth = float(data[24:31].strip())
        elevation = float(data[31:38].strip())
        roll = float(data[38:46].strip())

        return header, x, y, z, azimuth, elevation, roll
