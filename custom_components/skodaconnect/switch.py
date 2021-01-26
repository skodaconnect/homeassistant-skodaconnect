"""
Support for Skoda Connect Platform
"""
import logging

from homeassistant.helpers.entity import ToggleEntity

from . import DATA_KEY, SkodaEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """ Setup the Skoda switch."""
    if discovery_info is None:
        return
    async_add_entities([SkodaSwitch(hass.data[DATA_KEY], *discovery_info)])


class SkodaSwitch(SkodaEntity, ToggleEntity):
    """Representation of a Skoda Connect Switch."""

    @property
    def is_on(self):
        """Return true if switch is on."""
        _LOGGER.debug("Getting state of %s" % self.instrument.attr)
        return self.instrument.state

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        _LOGGER.debug("Turning ON %s." % self.instrument.attr)
        await self.instrument.turn_on()
        await super().update_hass()

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        _LOGGER.debug("Turning OFF %s." % self.instrument.attr)
        await self.instrument.turn_off()
        await super().update_hass()

    @property
    def assumed_state(self):
        return self.instrument.assumed_state
