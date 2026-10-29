"""Coordinate one local poll for all entities."""

from datetime import timedelta
import logging

from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import SolarEdgeClient, SolarEdgeError, Snapshot
from .const import CONF_UNIT_ID, DEFAULT_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class SolarEdgeCoordinator(DataUpdateCoordinator[Snapshot]):
    """Retrieve a single snapshot, marking all sensors unavailable on failure."""

    def __init__(self, hass, entry):
        settings = {**entry.data, **entry.options}
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN,
            update_interval=timedelta(
                seconds=settings.get(CONF_SCAN_INTERVAL, DEFAULT_INTERVAL)
            ), always_update=False,
        )
        self.client = SolarEdgeClient(
            settings[CONF_HOST], settings[CONF_PORT], settings[CONF_UNIT_ID]
        )

    async def _async_update_data(self) -> Snapshot:
        try:
            data = await self.client.async_poll()
            if data.serial.casefold() != self.config_entry.unique_id:
                raise SolarEdgeError("Il numero seriale dell'inverter è cambiato")
            return data
        except SolarEdgeError as err:
            raise UpdateFailed(str(err)) from err
