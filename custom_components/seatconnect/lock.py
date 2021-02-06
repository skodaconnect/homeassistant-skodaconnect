"""
Support for Seat Connect Platform
"""
import logging

from homeassistant.components.lock import LockEntity

from . import DATA_KEY, SeatEntity

# from homeassistant.components.lock import LockDevice


_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """ Setup the Seat lock """
    if discovery_info is None:
        return

    async_add_entities([SeatLock(hass.data[DATA_KEY], *discovery_info)])


class SeatLock(SeatEntity, LockEntity):
    # class SeatLock(SeatEntity, LockDevice):
    """Represents a Seat Connect Lock."""

    @property
    def is_locked(self):
        """Return true if lock is locked."""
        _LOGGER.debug("Getting state of %s" % self.instrument.attr)
        return self.instrument.is_locked

    async def async_lock(self, **kwargs):
        """Lock the car."""
        await self.instrument.lock()
        await super().update_hass()

    async def async_unlock(self, **kwargs):
        """Unlock the car."""
        await self.instrument.unlock()
        await super().update_hass()
