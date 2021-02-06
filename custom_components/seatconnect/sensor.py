"""
Support for Seat Connect Platform
"""
import logging

from homeassistant.helpers.icon import icon_for_battery_level

from . import DATA_KEY, SeatEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Seat sensors."""
    if discovery_info is None:
        return
    async_add_entities([SeatSensor(hass.data[DATA_KEY], *discovery_info)])


class SeatSensor(SeatEntity):
    """Representation of a Seat Carnet Sensor."""

    @property
    def state(self):
        """Return the state of the sensor."""
        _LOGGER.debug("Getting state of %s" % self.instrument.attr)
        return self.instrument.state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self.instrument.unit
