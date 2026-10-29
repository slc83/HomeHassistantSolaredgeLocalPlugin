"""Read-only asynchronous SolarEdge SunSpec Modbus TCP client.

Addresses are protocol addresses (base zero), without subtracting 40001.
Only function 03 is implemented. Each poll closes its TCP connection.
"""

import asyncio
from contextlib import suppress
from dataclasses import dataclass
import struct


class SolarEdgeError(Exception):
    """Invalid response or failed communication."""


class UnsupportedDevice(SolarEdgeError):
    """The endpoint is not a supported SolarEdge SunSpec inverter."""


@dataclass(frozen=True)
class Snapshot:
    """Identity and measurements from one poll."""

    manufacturer: str
    model: str
    firmware: str
    serial: str
    values: dict[str, float | int | str | None]


def text(registers: list[int]) -> str:
    """Decode a SunSpec string."""
    return struct.pack(f">{len(registers)}H", *registers).decode(
        "ascii", errors="replace"
    ).rstrip("\x00 ")


def signed(value: int) -> int:
    """Decode a signed 16-bit register."""
    return value - 65536 if value & 0x8000 else value


def scaled(raw: int, sf: int, *, is_signed: bool = False) -> float | None:
    """Decode scale factors and SunSpec not-implemented sentinels."""
    if raw == (0x8000 if is_signed else 0xFFFF) or sf == 0x8000:
        return None
    exponent = signed(sf)
    if not -10 <= exponent <= 10:
        return None
    return (signed(raw) if is_signed else raw) * 10.0**exponent


STATES = {
    1: "off", 2: "sleeping", 3: "starting", 4: "producing",
    5: "throttled", 6: "shutting_down", 7: "fault", 8: "standby",
}


def decode(common: list[int], block: list[int]) -> Snapshot:
    """Decode common model and integer inverter models 101/102/103."""
    if len(common) != 69 or common[:4] != [0x5375, 0x6E53, 1, 65]:
        raise UnsupportedDevice("Firma SunSpec o modello comune non valido")
    manufacturer = text(common[4:20])
    serial = text(common[52:68])
    if manufacturer.casefold() != "solaredge" or not serial:
        raise UnsupportedDevice("Produttore SolarEdge o numero seriale assente")
    if len(block) != 52 or block[0] not in (101, 102, 103) or block[1] != 50:
        raise UnsupportedDevice("Modello inverter SunSpec non supportato")
    # Offsets below are relative to the model header at protocol address 40069.
    fields = {
        "ac_current": (2, 6, False),
        "ac_voltage": (7, 13, False),
        "ac_power": (14, 15, True),
        "frequency": (16, 17, False),
        "apparent_power": (18, 19, True),
        "reactive_power": (20, 21, True),
        "power_factor": (22, 23, True),
        "dc_current": (27, 28, False),
        "dc_voltage": (29, 30, False),
        "dc_power": (31, 32, True),
        "temperature": (34, 37, True),
    }
    values = {
        key: scaled(block[index], block[sf], is_signed=is_signed)
        for key, (index, sf, is_signed) in fields.items()
    }
    # SolarEdge's single-phase voltage is in the AB register (40076).
    energy = (block[24] << 16) | block[25]
    # acc32: zero is the SunSpec not-implemented value; 0xffffffff is valid.
    values["energy_total"] = (
        energy * 10.0**signed(block[26]) / 1000
        if energy != 0 and block[26] != 0x8000
        and -10 <= signed(block[26]) <= 10 else None
    )
    values["status"] = STATES.get(block[38])
    values["vendor_status"] = None if block[39] == 0xFFFF else block[39]
    return Snapshot(manufacturer, text(common[20:36]), text(common[44:52]), serial, values)


class SolarEdgeClient:
    """A bounded Modbus TCP reader without third-party dependencies."""

    def __init__(self, host: str, port: int = 1502, unit_id: int = 1,
                 timeout: float = 10) -> None:
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout

    async def _read(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                    transaction: int, address: int, count: int) -> list[int]:
        writer.write(struct.pack(
            ">HHHBBHH", transaction, 0, 6, self.unit_id, 3, address, count
        ))
        await writer.drain()
        header = await reader.readexactly(7)
        tid, protocol, length, unit = struct.unpack(">HHHB", header)
        if tid != transaction or protocol != 0 or unit != self.unit_id:
            raise SolarEdgeError("Header Modbus non valido")
        if not 2 <= length <= 254:
            raise SolarEdgeError("Lunghezza Modbus non valida")
        pdu = await reader.readexactly(length - 1)
        if pdu[0] == 0x83 and len(pdu) == 2:
            raise SolarEdgeError(f"Eccezione Modbus: {pdu[1]}")
        if pdu[0] != 3 or len(pdu) != count * 2 + 2 or pdu[1] != count * 2:
            raise SolarEdgeError("Risposta registri Modbus non valida")
        return list(struct.unpack(f">{count}H", pdu[2:]))

    async def async_poll(self) -> Snapshot:
        """Connect, validate the identity, read a snapshot, and disconnect."""
        writer = None
        try:
            async with asyncio.timeout(self.timeout):
                reader, writer = await asyncio.open_connection(self.host, self.port)
                common = await self._read(reader, writer, 1, 40000, 69)
                block = await self._read(reader, writer, 2, 40069, 52)
                return decode(common, block)
        except (OSError, TimeoutError, asyncio.IncompleteReadError) as err:
            raise SolarEdgeError(f"Connessione Modbus fallita: {err}") from err
        finally:
            if writer is not None:
                writer.close()
                with suppress(OSError, TimeoutError):
                    async with asyncio.timeout(1):
                        await writer.wait_closed()
