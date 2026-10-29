"""Sensors for local SolarEdge monitoring."""

from homeassistant.components.sensor import (
    SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass,
)
from homeassistant.const import (
    EntityCategory, UnitOfApparentPower, UnitOfElectricCurrent,
    UnitOfElectricPotential, UnitOfEnergy, UnitOfFrequency,
    UnitOfPower, UnitOfReactivePower, UnitOfTemperature, PERCENTAGE,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import STATES
from .const import DOMAIN

PARALLEL_UPDATES = 0


def measurement(key, unit, device_class, precision=2):
    return SensorEntityDescription(
        key=key, translation_key=key, native_unit_of_measurement=unit,
        device_class=device_class, state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=precision,
    )


SENSORS = (
    measurement("ac_power", UnitOfPower.WATT, SensorDeviceClass.POWER),
    SensorEntityDescription(
        key="energy_total", translation_key="energy_total",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
    ),
    measurement("ac_voltage", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE),
    measurement("ac_current", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT),
    measurement("frequency", UnitOfFrequency.HERTZ, SensorDeviceClass.FREQUENCY),
    measurement("dc_power", UnitOfPower.WATT, SensorDeviceClass.POWER),
    measurement("dc_voltage", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE),
    measurement("dc_current", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT),
    measurement("temperature", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE),
    measurement("apparent_power", UnitOfApparentPower.VOLT_AMPERE,
                SensorDeviceClass.APPARENT_POWER),
    measurement("reactive_power", UnitOfReactivePower.VOLT_AMPERE_REACTIVE,
                SensorDeviceClass.REACTIVE_POWER),
    measurement("power_factor", PERCENTAGE, SensorDeviceClass.POWER_FACTOR),
    SensorEntityDescription(
        key="status", translation_key="status", device_class=SensorDeviceClass.ENUM,
        options=list(STATES.values()),
    ),
    SensorEntityDescription(
        key="vendor_status", translation_key="vendor_status",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        SolarEdgeSensor(entry.runtime_data, description) for description in SENSORS
    )


class SolarEdgeSensor(CoordinatorEntity, SensorEntity):
    """Expose a measurement from the shared snapshot."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, description):
        super().__init__(coordinator)
        self.entity_description = description
        data = coordinator.data
        self._attr_unique_id = f"{data.serial.casefold()}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, data.serial.casefold())},
            name=f"SolarEdge {data.model}", manufacturer=data.manufacturer,
            model=data.model, sw_version=data.firmware, serial_number=data.serial,
        )

    @property
    def native_value(self):
        return self.coordinator.data.values[self.entity_description.key]
