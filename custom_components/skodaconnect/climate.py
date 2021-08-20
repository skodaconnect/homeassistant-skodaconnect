"""
Support for Skoda Connect Platform
"""
import logging

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    HVAC_MODE_COOL,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    SUPPORT_TARGET_TEMPERATURE,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    STATE_UNKNOWN,
    TEMP_CELSIUS,
    TEMP_FAHRENHEIT,
    CONF_RESOURCES
)

SUPPORT_HVAC = [HVAC_MODE_COOL, HVAC_MODE_HEAT, HVAC_MODE_OFF]

from . import DATA, DATA_KEY, DOMAIN, SkodaEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """ Setup the Skoda climate."""
    if discovery_info is None:
        return
    async_add_entities([SkodaClimate(hass.data[DATA_KEY], *discovery_info)])


async def async_setup_entry(hass, entry, async_add_devices):
    data = hass.data[DOMAIN][entry.entry_id][DATA]
    coordinator = data.coordinator
    if coordinator.data is not None:
        if CONF_RESOURCES in entry.options:
            resources = entry.options[CONF_RESOURCES]
        else:
            resources = entry.data[CONF_RESOURCES]

        async_add_devices(
            SkodaClimate(
                data, instrument.vehicle_name, instrument.component, instrument.attr
            )
            for instrument in (
                instrument
                for instrument in data.instruments
                if instrument.component == "climate" and instrument.attr in resources
            )
        )

    return True


class SkodaClimate(SkodaEntity, ClimateEntity):
    """Representation of a Skoda Connect Climate."""

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_TARGET_TEMPERATURE

    @property
    def hvac_mode(self):
        """Return hvac operation ie. heat, cool mode.
        Need to be one of HVAC_MODE_*.
        """
        if not self.instrument.hvac_mode:
            return HVAC_MODE_OFF

        hvac_modes = {
            "HEATING": HVAC_MODE_HEAT,
            "COOLING": HVAC_MODE_COOL,
        }
        return hvac_modes.get(self.instrument.hvac_mode, HVAC_MODE_OFF)

    @property
    def hvac_modes(self):
        """Return the list of available hvac operation modes.
        Need to be a subset of HVAC_MODES.
        """
        return SUPPORT_HVAC

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return TEMP_CELSIUS

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        if self.instrument.target_temperature:
            return float(self.instrument.target_temperature)
        else:
            return STATE_UNKNOWN

    async def async_set_temperature(self, **kwargs):
        """Set new target temperatures."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature:
            await self.instrument.set_temperature(temperature)

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        if hvac_mode == HVAC_MODE_OFF:
            await self.instrument.set_hvac_mode(False)
        elif hvac_mode == HVAC_MODE_HEAT:
            await self.instrument.set_hvac_mode(True)
