"""UI configuration for a local SolarEdge inverter."""

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import callback

from .client import SolarEdgeClient, SolarEdgeError, UnsupportedDevice
from .const import CONF_UNIT_ID, DEFAULT_INTERVAL, DEFAULT_PORT, DOMAIN


def schema(defaults):
    """Connection and polling settings."""
    return vol.Schema({
        vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): vol.All(
            str, vol.Strip, vol.Length(min=1)
        ),
        vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)):
            vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
        vol.Required(CONF_UNIT_ID, default=defaults.get(CONF_UNIT_ID, 1)):
            vol.All(vol.Coerce(int), vol.Range(min=1, max=247)),
        vol.Required(CONF_SCAN_INTERVAL,
                     default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_INTERVAL)):
            vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
    })


async def validate(settings):
    """Verify live measurements before saving settings."""
    return await SolarEdgeClient(
        settings[CONF_HOST], settings[CONF_PORT], settings[CONF_UNIT_ID]
    ).async_poll()


class SolarEdgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a unique inverter using its hardware serial number."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                data = await validate(user_input)
            except UnsupportedDevice:
                errors["base"] = "unsupported_device"
            except SolarEdgeError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(data.serial.casefold())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"{data.model} ({data.serial})", data=user_input
                )
        return self.async_show_form(
            step_id="user", data_schema=schema(user_input or {}), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SolarEdgeOptionsFlow()


class SolarEdgeOptionsFlow(config_entries.OptionsFlow):
    """Change network settings or polling interval without recreating entities."""

    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                data = await validate(user_input)
            except UnsupportedDevice:
                errors["base"] = "unsupported_device"
            except SolarEdgeError:
                errors["base"] = "cannot_connect"
            else:
                if data.serial.casefold() != self.config_entry.unique_id:
                    errors["base"] = "wrong_device"
                else:
                    return self.async_create_entry(title="", data=user_input)
        defaults = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init", data_schema=schema(user_input or defaults), errors=errors
        )
