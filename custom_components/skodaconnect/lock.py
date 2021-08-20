"""
Support for Skoda Connect Platform
"""
import logging

from homeassistant.components.lock import LockEntity
from homeassistant.const import CONF_RESOURCES

from . import DATA, DATA_KEY, DOMAIN, SkodaEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """ Setup the Skoda lock """
    if discovery_info is None:
        return

    async_add_entities([SkodaLock(hass.data[DATA_KEY], *discovery_info)])


async def async_setup_entry(hass, entry, async_add_devices):
    data = hass.data[DOMAIN][entry.entry_id][DATA]
    coordinator = data.coordinator
    if coordinator.data is not None:
        if CONF_RESOURCES in entry.options:
            resources = entry.options[CONF_RESOURCES]
        else:
            resources = entry.data[CONF_RESOURCES]

        async_add_devices(
            SkodaLock(data, instrument.vehicle_name, instrument.component, instrument.attr)
            for instrument in (
                instrument
                for instrument in data.instruments
                if instrument.component == "lock" and instrument.attr in resources
            )
        )

    return True


class SkodaLock(SkodaEntity, LockEntity):
    """Represents a Skoda Connect Lock."""

    @property
    def is_locked(self):
        """Return true if lock is locked."""
        return self.instrument.is_locked

    async def async_lock(self, **kwargs):
        """Lock the car."""
        await self.instrument.lock()

    async def async_unlock(self, **kwargs):
        """Unlock the car."""
        await self.instrument.unlock()
