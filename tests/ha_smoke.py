"""Optional end-to-end smoke test; run with Home Assistant 2026.6.2 installed."""

import asyncio
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from homeassistant import loader
from homeassistant.config_entries import ConfigEntries
from homeassistant.const import __version__
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry, device_registry, entity_registry

from test_client import ProtocolTests


async def main():
    assert __version__ == "2026.6.2", __version__
    simulator = ProtocolTests()
    await simulator.asyncSetUp()
    try:
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "custom_components").symlink_to(
                Path(__file__).resolve().parents[1] / "custom_components",
                target_is_directory=True,
            )
            hass = HomeAssistant(directory)
            loader.async_setup(hass)
            hass.config_entries = ConfigEntries(hass, {})
            try:
                device_registry.async_setup(hass)
                await area_registry.async_load(hass)
                await device_registry.async_load(hass)
                await entity_registry.async_load(hass)
                await hass.config_entries.async_initialize()
                form = await hass.config_entries.flow.async_init(
                    "solaredge_local", context={"source": "user"}
                )
                assert form["type"] == "form", form
                settings = {"host": "127.0.0.1", "port": simulator.port,
                            "unit_id": 1, "scan_interval": 30}
                result = await hass.config_entries.flow.async_configure(
                    form["flow_id"], settings
                )
                assert result["type"] == "create_entry", result
                await hass.async_block_till_done()
                entry = result["result"]
                assert entry.state.value == "loaded", entry.state
                states = hass.states.async_all("sensor")
                assert len(states) == 14, [(s.entity_id, s.state) for s in states]
                energy = next(s for s in states if s.attributes.get("device_class") == "energy")
                assert float(energy.state) == 100, energy
                assert energy.attributes["state_class"] == "total_increasing"
                duplicate = await hass.config_entries.flow.async_init(
                    "solaredge_local", context={"source": "user"}, data=settings
                )
                assert duplicate["reason"] == "already_configured", duplicate
                options = await hass.config_entries.options.async_init(entry.entry_id)
                assert options["type"] == "form", options
                settings["scan_interval"] = 60
                changed = await hass.config_entries.options.async_configure(
                    options["flow_id"], settings
                )
                assert changed["type"] == "create_entry", changed
                await hass.async_block_till_done()
                assert entry.runtime_data.update_interval.total_seconds() == 60
                simulator.mode = "exception"
                await entry.runtime_data.async_refresh()
                await hass.async_block_till_done()
                assert all(s.state == "unavailable" for s in hass.states.async_all("sensor"))
                simulator.mode = "normal"
                await entry.runtime_data.async_refresh()
                await hass.async_block_till_done()
                assert hass.states.get(energy.entity_id).state == "100.0"
                assert await hass.config_entries.async_unload(entry.entry_id)
                print("Core 2026.6.2: configuration, 14 sensors, duplicate prevention, "
                      "options/reload, disconnect/recovery and unload OK")
            finally:
                await hass.async_stop()
    finally:
        await simulator.asyncTearDown()


if __name__ == "__main__":
    asyncio.run(main())
