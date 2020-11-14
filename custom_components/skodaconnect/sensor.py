"""
Support for Skoda Connect Platform
"""
import logging

from homeassistant.helpers.icon import icon_for_battery_level

from . import DATA_KEY, SkodaEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Skoda sensors."""
    if discovery_info is None:
        return
    async_add_entities([SkodaSensor(hass.data[DATA_KEY], *discovery_info)])


class SkodaSensor(SkodaEntity):
    """Representation of a Skoda Carnet Sensor."""

    @property
    def state(self):
        """Return the state of the sensor."""
        _LOGGER.debug("Getting state of %s" % self.instrument.attr)
        return self.instrument.state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self.instrument.unit
