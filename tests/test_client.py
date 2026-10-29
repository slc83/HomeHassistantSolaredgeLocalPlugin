"""Protocol and decoding tests using a real local TCP simulator, no HA required."""

import asyncio
from contextlib import suppress
import importlib.util
from pathlib import Path
import struct
import sys
import unittest

path = Path(__file__).resolve().parents[1] / "custom_components/solaredge_local/client.py"
spec = importlib.util.spec_from_file_location("solaredge_test_client", path)
client = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = client
spec.loader.exec_module(client)


def string_words(value, size):
    return list(struct.unpack(f">{size}H", value.encode().ljust(size * 2, b"\0")))


def fixture():
    common = [0] * 69
    common[:4] = [0x5375, 0x6E53, 1, 65]
    common[4:20] = string_words("SolarEdge", 16)
    common[20:36] = string_words("SE6000H", 16)
    common[44:52] = string_words("4.1234", 8)
    common[52:68] = string_words("TEST-1234", 16)
    common[68] = 1
    block = [0] * 52
    block[:2] = [101, 50]
    block[2], block[6] = 2608, 0xFFFE
    block[7], block[13] = 2301, 0xFFFF
    block[14], block[15] = 6000, 0
    block[16], block[17] = 5000, 0xFFFE
    block[24], block[25], block[26] = 1, 34464, 0  # 100,000 Wh
    block[27], block[28] = 1600, 0xFFFE
    block[29], block[30] = 3800, 0xFFFF
    block[31], block[32] = 6080, 0
    block[34], block[37] = 425, 0xFFFF
    block[38] = 4
    return common, block


class DecodeTests(unittest.TestCase):
    def test_measurements(self):
        result = client.decode(*fixture())
        self.assertEqual(result.serial, "TEST-1234")
        self.assertEqual(result.model, "SE6000H")
        for key, value in {
            "ac_power": 6000, "ac_current": 26.08, "ac_voltage": 230.1,
            "frequency": 50, "energy_total": 100, "temperature": 42.5,
            "dc_current": 16, "dc_voltage": 380, "status": "producing",
        }.items():
            if isinstance(value, str):
                self.assertEqual(result.values[key], value)
            else:
                self.assertAlmostEqual(result.values[key], value)

    def test_signed_and_sentinels(self):
        common, block = fixture()
        block[14] = 0xFFFF  # signed -1, not unsigned sentinel
        block[34] = 0xFFCE  # -50 -> -5 C
        block[2] = 0xFFFF
        block[29] = 0x8000  # unsigned 32768, valid
        block[38] = 0xFFFF
        result = client.decode(common, block)
        self.assertEqual(result.values["ac_power"], -1)
        self.assertEqual(result.values["temperature"], -5)
        self.assertIsNone(result.values["ac_current"])
        self.assertIsNone(result.values["status"])
        self.assertEqual(result.values["dc_voltage"], 3276.8)
        self.assertIsNone(client.scaled(0x8000, 0, is_signed=True))
        self.assertIsNone(client.scaled(1, 0x8000))
        self.assertIsNone(client.scaled(1, 100))

    def test_accumulator_word_order_and_boundaries(self):
        common, block = fixture()
        for high, low, expected in ((0, 65535, 65.535), (65535, 65535, 4294967.295),
                                     (0, 0, None), (0x1234, 0x5678, 305419.896)):
            block[24:26] = [high, low]
            value = client.decode(common, block).values["energy_total"]
            if expected is None:
                self.assertIsNone(value)
            else:
                self.assertAlmostEqual(value, expected)

    def test_invalid_identity_and_model(self):
        for target, index, value in ((0, 0, 0), (0, 3, 64), (1, 0, 201), (1, 1, 49)):
            data = fixture()
            data[target][index] = value
            with self.assertRaises(client.UnsupportedDevice):
                client.decode(*data)
        common, block = fixture()
        common[52:68] = [0] * 16
        with self.assertRaises(client.UnsupportedDevice):
            client.decode(common, block)


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mode = "normal"
        self.requests = []
        self.connections = 0
        self.tasks = set()
        self.server = await asyncio.start_server(self.handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()
        for task in self.tasks.copy():
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        self.connections += 1
        try:
            for _ in range(2):
                request = await reader.readexactly(12)
                tid, protocol, length, unit, function, address, count = struct.unpack(
                    ">HHHBBHH", request
                )
                self.requests.append((protocol, length, unit, function, address, count))
                if self.mode == "timeout":
                    await reader.read()
                    return
                if self.mode == "disconnect":
                    return
                registers = fixture()[0 if address == 40000 else 1]
                pdu = bytes((3, count * 2)) + struct.pack(f">{count}H", *registers)
                if self.mode == "exception":
                    pdu = b"\x83\x02"
                if self.mode == "bytecount":
                    pdu = b"\x03\x00" + pdu[2:]
                header = struct.pack(">HHHB", tid + (self.mode == "tid"),
                                     int(self.mode == "protocol"),
                                     65535 if self.mode == "length" else len(pdu) + 1,
                                     unit + (self.mode == "unit"))
                # Exercise fragmented TCP delivery, including the MBAP header.
                writer.write(header[:3])
                await writer.drain()
                await asyncio.sleep(0)
                writer.write(header[3:] + pdu)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()
            self.tasks.discard(task)

    async def test_poll_and_reconnect(self):
        reader = client.SolarEdgeClient("127.0.0.1", self.port)
        for _ in range(2):
            result = await reader.async_poll()
            self.assertEqual(result.values["energy_total"], 100)
        self.assertEqual(self.connections, 2)
        self.assertEqual(self.requests, [(0, 6, 1, 3, 40000, 69),
                                       (0, 6, 1, 3, 40069, 52)] * 2)

    async def test_malformed_response_and_recovery(self):
        reader = client.SolarEdgeClient("127.0.0.1", self.port, timeout=0.1)
        for mode in ("exception", "bytecount", "tid", "protocol", "unit", "length",
                     "timeout", "disconnect"):
            with self.subTest(mode=mode):
                self.mode = mode
                with self.assertRaises(client.SolarEdgeError):
                    await reader.async_poll()
        self.mode = "normal"
        self.assertEqual((await reader.async_poll()).serial, "TEST-1234")

    async def test_cancellation(self):
        self.mode = "timeout"
        task = asyncio.create_task(client.SolarEdgeClient(
            "127.0.0.1", self.port
        ).async_poll())
        while not self.requests:
            await asyncio.sleep(0.001)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task


if __name__ == "__main__":
    unittest.main()
