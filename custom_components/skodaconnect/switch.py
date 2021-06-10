"""
Support for Skoda Connect Platform
"""
import logging
from typing import Any, Dict, Optional
import voluptuous as vol

from homeassistant.helpers.entity import ToggleEntity
from homeassistant.helpers import config_validation as cv, entity_platform, service

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
        async_add_devices(
            SkodaSwitch(
                data, coordinator.vin, instrument.component, instrument.attr, hass.data[DOMAIN][entry.entry_id][UPDATE_CALLBACK]
            )
            for instrument in (
                instrument
                for instrument in data.instruments
                if instrument.component == "switch"
            )
        )

    # Register entity service
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "set_departure_schedule",
        {
            vol.Required("id", default=1): vol.In([1,2,3]),
            vol.Required("enabled", default=True): cv.boolean,
            vol.Required("recurring", default=False): cv.boolean,
            vol.Required("time", default="08:00"): cv.time,
            vol.Optional("date", default="2020-01-01"): cv.string,
            vol.Optional("days", default='nnnnnnn'): cv.string,
        },
        "set_departure_schedule",
    )
    platform.async_register_entity_service(
        "set_charge_limit",
        {
            vol.Required("limit"): vol.In([0,10,20,30,40,50]),
        },
        "set_charge_limit",
    )
    platform.async_register_entity_service(
        "set_pheater_duration",
        {
            vol.Required("duration"): vol.In([10,20,30,40,50,60]),
        },
        "set_pheater_duration",
    )
    platform.async_register_entity_service(
        "set_charger_current",
        {
            vol.Required("current"): vol.In(["maximum", "reduced"]),
        },
        "set_charger_current",
    )

    return True


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
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        _LOGGER.debug("Turning OFF %s." % self.instrument.attr)
        await self.instrument.turn_off()
        self.async_write_ha_state()

    @property
    def assumed_state(self):
        return self.instrument.assumed_state

    @property
    def state_attributes(self) -> Optional[Dict[str, Any]]:
        return self.instrument.attributes

    # Service functions
    async def async_charge_limit(
        self,
        limit: int
    ) -> None:
        """Set minimum charge limit."""
        _LOGGER.info(f'Set charging limit to {limit}')

    async def async_departure_schedule(
        self,
        id: int,
        enabled: bool,
        recurring: bool,
        time: str,
        date: str,
        days: str
    ) -> None:
        """Set departure schedule."""
        _LOGGER.info(f'Set departure schedule: {id}, {enabled}, {recurring}, {time}, {date}, {days}')

    async def async_pheater_duration(
        self,
        duration: int
    ) -> None:
        """Set duration for parking heater."""
        _LOGGER.info(f'Set parking heater duration to {duration}')

    async def async_charger_current(
        self,
        current: str
    ) -> None:
        """Set charger current."""
        _LOGGER.info(f'Set charger current to {current}')
