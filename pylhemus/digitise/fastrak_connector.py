import serial
import time
import numpy as np
import re
import os


class FastrakConnector:
    def __init__(
        self, usb_port: str, stylus_receiver:int=0, head_reference:int=1, data_length:int=47
    ):
        """
        A class to interface with the Polhemus FASTRAK system.

        Args:
            usb_port (str): The USB port to which the Polhemus FASTRAK is connected.
            stylus_receiver (int): The receiver port number for the stylus (default is 0).
            head_reference (int): The receiver port number for the head reference (default is 1).
            data_length (int): The expected length of data for each receiver reading.

        Methods:
            n_receivers(): Queries the number of active receivers.
            set_factory_software_defaults(): Resets the device to factory defaults.
            clear_old_data(): Clears outdated data from the serial buffer.
            output_metric(): Sets the measurement units to metric.
            prepare_for_digitisation(): Prepares the device for digitisation use.
            get_position_relative_to_head_receiver(): Computes the position from the stylus relative to the head receiver.
        """
        self.stylus_receiver = stylus_receiver
        self.head_reference = head_reference
        self.data_length = data_length
        self.n_receivers = 0
        self.debug_serial = os.getenv("PYLHEMUS_DEBUG_SERIAL", "").lower() in {"1", "true", "yes", "on"}

        # initialize serial object
        self.serialobj = serial.Serial(
            port=usb_port,  # Port name (adjust as necessary)
            baudrate=9600,  # Baud rate
            stopbits=serial.STOPBITS_ONE,  # Stop bits (1 stop bit)
            parity=serial.PARITY_NONE,  # No parity
            bytesize=serial.EIGHTBITS,  # 8 data bits
            rtscts=False,  # No hardware flow control
            timeout=1,  # Read timeout in seconds
            write_timeout=1,  # Write timeout in seconds
            xonxoff=False,  # No software flow control
        )

    def send_serial_command(self, command:bytes, sleep_time:float=0.1):
        try:
            self.serialobj.write(command)
            time.sleep(sleep_time)
        except serial.SerialTimeoutException:
            print("Serial write timeout occurred.")
        except serial.SerialException as e:
            print(f"Serial communication error: {e}")

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

    def output_metric(self):
        """
        Changes the output to centimeters instead of inches
        """
        self.send_serial_command(b"u")  # send 'u' command to set metric units

    def prepare_for_digitisation(self):
        self.set_factory_software_defaults()
        self.clear_old_data()
        self.output_metric()
        self.query_n_receivers()

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
