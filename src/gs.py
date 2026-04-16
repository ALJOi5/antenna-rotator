"""
NSLP (Nano Serial Link Protocol) - Python port of the Arduino C++ library.

Frame structure:
  [FRAME_START (1)] [sender (1)] [receiver (1)] [type (1)] [size (1)] [payload (0-255)] [CRC32 (4)]

CRC-32 details (must match Arduino crc32.cpp exactly):
  Polynomial : 0x04C11DB7  (non-reflected / MSB-first)
  Init value : 0xFFFFFFFF
  Final XOR  : none
  zlib.crc32 is NOT compatible (uses reflected poly + different init).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import serial  # pyserial


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NSLP_VOID_TYPE: int = 0x00
FRAME_START: int = 0x7E
FRAME_START_SIZE: int = 1
HEADER_SIZE: int = 4          # sender + receiver + type + size
MAX_PAYLOAD_SIZE: int = 255
CHECKSUM_SIZE: int = 4        # CRC-32 (4 bytes, little-endian on wire)

TOTAL_OVERHEAD: int = FRAME_START_SIZE + HEADER_SIZE + CHECKSUM_SIZE


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Packet:
    """Mirrors the C++ NSLP::Packet struct."""
    sender:   int
    receiver: int
    type:     int
    payload:  bytes = field(default=b"")

    @property
    def size(self) -> int:
        return len(self.payload)

    def __repr__(self) -> str:
        return (
            f"Packet(sender=0x{self.sender:02X}, receiver=0x{self.receiver:02X}, "
            f"type=0x{self.type:02X}, size={self.size}, payload={self.payload.hex()})"
        )


class Status(Enum):
    """Mirrors the C++ NSLP::Status enum."""
    UNKNOWN        = 0
    SUCCESS        = 1
    INVALID_PACKET = 2
    CHECKSUM_ERROR = 3
    FRAME_ERROR    = 4
    TIMEOUT_ERROR  = 5


# ---------------------------------------------------------------------------
# CRC-32 (exact port of Arduino crc32.cpp)
# ---------------------------------------------------------------------------

def _build_crc32_table() -> list:
    table = []
    for i in range(256):
        c = i << 24
        for _ in range(8):
            c = ((c << 1) ^ 0x04C11DB7) if (c & 0x80000000) else (c << 1)
            c &= 0xFFFFFFFF
        table.append(c)
    return table

_CRC32_TABLE = _build_crc32_table()


def _crc32(data: bytes) -> int:
    """CRC-32 matching Arduino crc32_init() / crc32_update() exactly."""
    crc = 0xFFFFFFFF
    for byte in data:
        idx = ((crc >> 24) & 0xFF) ^ byte
        crc = ((crc << 8) & 0xFFFFFFFF) ^ _CRC32_TABLE[idx]
    return crc  # no final XOR, matching the Arduino implementation


# ---------------------------------------------------------------------------
# Protocol helpers
# ---------------------------------------------------------------------------

def build_frame(packet: Packet) -> bytes:
    """Serialise a Packet into a raw NSLP frame ready to write to serial."""
    if len(packet.payload) > MAX_PAYLOAD_SIZE:
        raise ValueError(f"Payload too large: {len(packet.payload)} > {MAX_PAYLOAD_SIZE}")

    # CRC covers header + payload only, FRAME_START byte excluded,
    # matching Arduino send_packet: crc32_update(crc, &pData[1], packetSize)
    header_and_payload = bytes([
        packet.sender,
        packet.receiver,
        packet.type,
        packet.size,
    ]) + packet.payload

    crc = _crc32(header_and_payload)
    return bytes([FRAME_START]) + header_and_payload + struct.pack("<I", crc)


def parse_frame(raw: bytes) -> tuple:
    """
    Parse and validate a complete raw NSLP frame.

    Returns (packet, status, calculated_crc, received_crc).
    packet is None when status != SUCCESS.
    """
    if len(raw) < FRAME_START_SIZE + HEADER_SIZE + CHECKSUM_SIZE:
        return None, Status.INVALID_PACKET, 0, 0

    if raw[0] != FRAME_START:
        return None, Status.FRAME_ERROR, 0, 0

    sender   = raw[1]
    receiver = raw[2]
    pkt_type = raw[3]
    size     = raw[4]

    expected_total = FRAME_START_SIZE + HEADER_SIZE + size + CHECKSUM_SIZE
    if len(raw) < expected_total:
        return None, Status.INVALID_PACKET, 0, 0

    payload_start = FRAME_START_SIZE + HEADER_SIZE
    payload    = raw[payload_start: payload_start + size]
    crc_offset = payload_start + size

    received_crc   = struct.unpack_from("<I", raw, crc_offset)[0]
    # CRC excludes FRAME_START, matching Arduino receive_packet:
    # crc32_update(crc, &receiveData[FRAME_START_SIZE], HEADER_SIZE + size)
    calculated_crc = _crc32(raw[FRAME_START_SIZE:crc_offset])

    if calculated_crc != received_crc:
        return None, Status.CHECKSUM_ERROR, calculated_crc, received_crc

    return (
        Packet(sender=sender, receiver=receiver, type=pkt_type, payload=bytes(payload)),
        Status.SUCCESS,
        calculated_crc,
        received_crc,
    )


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class NSLP:
    """Python equivalent of the C++ NSLP::NSLP class."""

    def __init__(self, port: serial.Serial) -> None:
        self._serial = port
        self._receive_status: Status = Status.UNKNOWN
        self._receive_data: bytes = b""
        self._calculated_crc: int = 0
        self._received_crc:   int = 0

    def receive_packet(self) -> Optional[Packet]:
        """Blocking receive. Returns the parsed Packet or None on error."""
        # 1. Sync to FRAME_START
        while True:
            byte = self._serial.read(1)
            if not byte:
                self._receive_status = Status.TIMEOUT_ERROR
                return None
            if byte[0] == FRAME_START:
                break

        # 2. Read header (sender, receiver, type, size)
        header = self._serial.read(HEADER_SIZE)
        if len(header) < HEADER_SIZE:
            self._receive_status = Status.TIMEOUT_ERROR
            return None

        size = header[3]

        # 3. Read payload + CRC
        remainder = self._serial.read(size + CHECKSUM_SIZE)
        if len(remainder) < size + CHECKSUM_SIZE:
            self._receive_status = Status.TIMEOUT_ERROR
            return None

        raw = bytes([FRAME_START]) + header + remainder
        self._receive_data = raw

        # 4. Parse & validate
        packet, status, calc_crc, recv_crc = parse_frame(raw)
        self._receive_status = status
        self._calculated_crc = calc_crc
        self._received_crc   = recv_crc
        return packet

    def send_packet(self, packet: Packet) -> None:
        """Serialise packet and write it to the serial port."""
        self._serial.write(build_frame(packet))

    @property
    def receive_status(self) -> Status:
        return self._receive_status

    @property
    def receive_data(self) -> bytes:
        return self._receive_data

    @property
    def calculated_crc(self) -> int:
        return self._calculated_crc

    @property
    def received_crc(self) -> int:
        return self._received_crc






# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    PORT    = "COM3"
    BAUD    = 9600
    TIMEOUT = 1  # seconds

    try:
        ser = serial.Serial(PORT, baudrate=BAUD, timeout=TIMEOUT)
    except serial.SerialException as exc:
        print(f"[ERROR] Could not open {PORT}: {exc}", file=sys.stderr)
        sys.exit(1)

    nslp = NSLP(ser)
    print(f"[NSLP] Listening on {PORT} @ {BAUD} baud -- Ctrl-C to quit\n")

    try:
        while True:
            packet = nslp.receive_packet()

            if nslp.receive_status == Status.TIMEOUT_ERROR:
                continue  # nothing in this window, keep waiting

            if nslp.receive_status != Status.SUCCESS:
                print(
                    f"[ERROR] {nslp.receive_status.name} | "
                    f"raw={nslp.receive_data.hex()} | "
                    f"calc=0x{nslp.calculated_crc:08X} "
                    f"recv=0x{nslp.received_crc:08X}"
                )
                continue

            #? print(f"[OK] {packet}")
            parse_packet(packet)

    except KeyboardInterrupt:
        print("\n[NSLP] Stopped.")
    finally:
        ser.close()