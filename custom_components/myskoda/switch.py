"""
Support for Skoda Connect Platform
"""
import logging
from typing import Any, Dict, Optional
import voluptuous as vol

from homeassistant.helpers.entity import ToggleEntity
from homeassistant.helpers import config_validation as cv, entity_platform, service
from homeassistant.const import CONF_RESOURCES

from . import DATA, DATA_KEY, DOMAIN, SkodaEntity, UPDATE_CALLBACK

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """ Setup the Skoda switch."""
    if discovery_info is None:
        return
    async_add_entities([SkodaSwitch(hass.data[DATA_KEY], *discovery_info)])


async def async_setup_entry(hass, entry, async_add_devices):
    data = hass.data[DOMAIN][entry.entry_id][DATA]
    coordinator = data.coordinator
    if coordinator.data is not None:
        if CONF_RESOURCES in entry.options:
            resources = entry.options[CONF_RESOURCES]
        else:
            resources = entry.data[CONF_RESOURCES]

        async_add_devices(
            SkodaSwitch(
                data, instrument.vehicle_name, instrument.component, instrument.attr, hass.data[DOMAIN][entry.entry_id][UPDATE_CALLBACK]
            )
            for instrument in (
                instrument
                for instrument in data.instruments
                if instrument.component == "switch" and instrument.attr in resources
            )
        )

    return True


class SkodaSwitch(SkodaEntity, ToggleEntity):
    """Representation of a Skoda Connect Switch."""

    @property
    def is_on(self):
        """Return true if switch is on."""
        return self.instrument.state

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        await self.instrument.turn_on()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        await self.instrument.turn_off()
        self.async_write_ha_state()

    @property
    def assumed_state(self):
        return self.instrument.assumed_state

    @property
    def state_attributes(self) -> Optional[Dict[str, Any]]:
        return self.instrument.attributes
