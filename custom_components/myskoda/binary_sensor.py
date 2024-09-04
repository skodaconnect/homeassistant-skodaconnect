"""
Support for Skoda Connect.
"""
import logging

from homeassistant.components.binary_sensor import DEVICE_CLASSES, BinarySensorEntity
from homeassistant.const import CONF_RESOURCES

from . import UPDATE_CALLBACK, DATA, DATA_KEY, DOMAIN, SkodaEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Skoda binary sensors."""
    if discovery_info is None:
        return
    async_add_entities([SkodaBinarySensor(hass.data[DATA_KEY], *discovery_info)])


async def async_setup_entry(hass, entry, async_add_devices):
    data = hass.data[DOMAIN][entry.entry_id][DATA]
    coordinator = data.coordinator
    if coordinator.data is not None:
        if CONF_RESOURCES in entry.options:
            resources = entry.options[CONF_RESOURCES]
        else:
            resources = entry.data[CONF_RESOURCES]

        async_add_devices(
            SkodaBinarySensor(
                data, instrument.vehicle_name, instrument.component, instrument.attr, hass.data[DOMAIN][entry.entry_id][UPDATE_CALLBACK]
            )
            for instrument in (
                instrument
                for instrument in data.instruments
                if instrument.component == "binary_sensor" and instrument.attr in resources
            )
        )

    return True


class SkodaBinarySensor(SkodaEntity, BinarySensorEntity):
    """Representation of a Skoda Binary Sensor """

    @property
    def is_on(self):
        """Return True if the binary sensor is on."""
        # Invert state for lock/window/door to get HA to display correctly
        if self.instrument.device_class in ['lock', 'door', 'window']:
            return not self.instrument.is_on
        return self.instrument.is_on

    @property
    def device_class(self):
        """Return the class of this sensor, from DEVICE_CLASSES."""
        if self.instrument.device_class in DEVICE_CLASSES:
            return self.instrument.device_class
        return None
