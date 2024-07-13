# -*- coding: utf-8 -*-
"""
Skoda Connect integration

Read more at https://github.com/skodaconnect/homeassistant-skodaconnect/
"""
import re
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Union
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, SOURCE_REAUTH, SOURCE_IMPORT
from homeassistant.const import (
    CONF_NAME,
    CONF_PASSWORD,
    CONF_RESOURCES,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, device_registry
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.icon import icon_for_battery_level
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from skodaconnect import Connection
from skodaconnect.vehicle import Vehicle
from skodaconnect.exceptions import (
    SkodaConfigException,
    SkodaAuthenticationException,
    SkodaAccountLockedException,
    SkodaTokenExpiredException,
    SkodaTokenInvalidException,
    SkodaException,
    SkodaEULAException,
    SkodaThrottledException,
    SkodaLoginFailedException,
    SkodaInvalidRequestException,
    SkodaRequestInProgressException
)

from .const import (
    PLATFORMS,
    CONF_MUTABLE,
    CONF_SCANDINAVIAN_MILES,
    CONF_SPIN,
    CONF_VEHICLE,
    CONF_TOKENS,
    CONF_INSTRUMENTS,
    CONF_DEBUG,
    CONF_CONVERT,
    CONF_NO_CONVERSION,
    CONF_IMPERIAL_UNITS,
    CONF_SAVESESSION,
    DATA,
    DATA_KEY,
    MIN_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_DEBUG,
    DOMAIN,
    SIGNAL_STATE_UPDATED,
    UNDO_UPDATE_LISTENER,
    REMOVE_LISTENER,
    UPDATE_CALLBACK,
    SERVICE_SET_SCHEDULE,
    SERVICE_SET_MAX_CURRENT,
    SERVICE_SET_CHARGE_LIMIT,
    SERVICE_SET_CLIMATER,
    SERVICE_SET_PHEATER_DURATION,
)

SERVICE_SET_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): vol.All(cv.string, vol.Length(min=32, max=32)),
        vol.Required("id"): vol.In([1,2,3]),
        vol.Required("time"): cv.string,
        vol.Required("enabled"): cv.boolean,
        vol.Required("recurring"): cv.boolean,
        vol.Optional("date"): cv.string,
        vol.Optional("days"): cv.string,
        vol.Optional("temp"): vol.All(vol.Coerce(float), vol.Range(min=16, max=30)),
        vol.Optional("climatisation"): cv.boolean,
        vol.Optional("charging"): cv.boolean,
        vol.Optional("charge_current"): vol.Any(
            vol.Range(min=1, max=254),
            vol.In(['Maximum', 'maximum', 'Max', 'max', 'Minimum', 'minimum', 'Min', 'min', 'Reduced', 'reduced'])
        ),
        vol.Optional("charge_target"): vol.In([0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]),
        vol.Optional("heater_source"): cv.boolean,
        vol.Optional("spin"): vol.All(cv.string, vol.Match(r"^[0-9]{4}$")),
        vol.Optional("off_peak_active"): cv.boolean,
        vol.Optional("off_peak_start"): cv.string,
        vol.Optional("off_peak_end"): cv.string,
    }
)
SERVICE_SET_MAX_CURRENT_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): vol.All(cv.string, vol.Length(min=32, max=32)),
        vol.Required("current"): vol.Any(
            vol.Range(min=1, max=255),
            vol.In(['Maximum', 'maximum', 'Max', 'max', 'Minimum', 'minimum', 'Min', 'min', 'Reduced', 'reduced'])
        ),
    }
)
SERVICE_SET_CHARGE_LIMIT_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): vol.All(cv.string, vol.Length(min=32, max=32)),
        vol.Required("limit"): vol.In([0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]),
    }
)
SERVICE_SET_CLIMATER_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): vol.All(cv.string, vol.Length(min=32, max=32)),
        vol.Required("enabled", default=True): cv.boolean,
        vol.Optional("temp"): vol.All(vol.Coerce(float), vol.Range(min=16, max=30)),
        vol.Optional("battery_power"): cv.boolean,
        vol.Optional("aux_heater"): cv.boolean,
        vol.Optional("spin"): vol.All(cv.string, vol.Match(r"^[0-9]{4}$"))
    }
)
SERVICE_SET_PHEATER_DURATION_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): vol.All(cv.string, vol.Length(min=32, max=32)),
        vol.Required("duration"): vol.In([10, 20, 30, 40, 50, 60]),
    }
)

# Set max parallel updates to 2 simultaneous (1 poll and 1 request waiting)
#PARALLEL_UPDATES = 2

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Setup Skoda Connect component from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    if entry.options.get(CONF_SCAN_INTERVAL):
        update_interval = timedelta(seconds=entry.options[CONF_SCAN_INTERVAL])
    else:
        update_interval = timedelta(seconds=DEFAULT_SCAN_INTERVAL)
    if update_interval < timedelta(seconds=MIN_SCAN_INTERVAL):
        update_interval = timedelta(seconds=MIN_SCAN_INTERVAL)

    coordinator = SkodaCoordinator(hass, entry, update_interval)

    try:
        if not await coordinator.async_login():
            await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_REAUTH},
                data=entry,
            )
            return False
    except (SkodaAuthenticationException, SkodaAccountLockedException, SkodaLoginFailedException) as e:
        raise ConfigEntryAuthFailed(e) from e
    except Exception as e:
        raise ConfigEntryNotReady(e) from e

    # Do a first update of all vehicles
    await coordinator.async_refresh()
    if not coordinator.last_update_success:
        raise ConfigEntryNotReady

    # Get parent device
    try:
        identifiers={(DOMAIN, entry.unique_id)}
        registry = device_registry.async_get(hass)
        device = registry.async_get_device(identifiers)
        # Get user configured name for device
        name = device.name_by_user if not device.name_by_user is None else None
    except:
        name = None

    data = SkodaData(entry.data, name, coordinator)
    instruments = coordinator.data

    conf_instruments = entry.data.get(CONF_INSTRUMENTS, {}).copy()
    if entry.options.get(CONF_DEBUG, False) is True:
        _LOGGER.debug(f"Configured data: {entry.data}")
        _LOGGER.debug(f"Configured options: {entry.options}")
        _LOGGER.debug(f"Resources from options are: {entry.options.get(CONF_RESOURCES, [])}")
        _LOGGER.debug(f"All instruments (data): {conf_instruments}")
    new_instruments = {}

    def is_enabled(attr):
        """Return true if the user has enabled the resource."""
        return attr in entry.data.get(CONF_RESOURCES, [attr])

    components = set()

    # Check if new instruments
    for instrument in (
        instrument
        for instrument in instruments
        if not instrument.attr in conf_instruments
    ):
            _LOGGER.info(f"Discovered new instrument {instrument.name}")
            new_instruments[instrument.attr] = instrument.name

    # Update config entry with new instruments
    if len(new_instruments) > 0:
        conf_instruments.update(new_instruments)
        # Prepare data to update config entry with
        update = {
            'data': {
                CONF_INSTRUMENTS: dict(sorted(conf_instruments.items(), key=lambda item: item[1]))
            },
            'options': {
                CONF_RESOURCES: entry.options.get(
                    CONF_RESOURCES,
                    entry.data.get(CONF_RESOURCES, ['none']))
            }
        }

        # Enable new instruments if "activate newly enable entitys" is active
        if hasattr(entry, "pref_disable_new_entities"):
            if not entry.pref_disable_new_entities:
                _LOGGER.debug(f"Enabling new instruments {new_instruments}")
                for item in new_instruments:
                    update['options'][CONF_RESOURCES].append(item)

        _LOGGER.debug(f"Updating config entry data: {update.get('data')}")
        _LOGGER.debug(f"Updating config entry options: {update.get('options')}")
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, **update['data']},
            options={**entry.options, **update['options']}
        )

    for instrument in (
        instrument
        for instrument in instruments
        if instrument.component in PLATFORMS and is_enabled(instrument.slug_attr)
    ):
        data.instruments.add(instrument)
        components.add(PLATFORMS[instrument.component])

    hass.data[DOMAIN][entry.entry_id] = {
        UPDATE_CALLBACK: update_callback,
        DATA: data,
        UNDO_UPDATE_LISTENER: entry.add_update_listener(_async_update_listener),
        REMOVE_LISTENER: hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, coordinator.async_logout
        ),
    }

    for component in components:
        coordinator.platforms.append(component)
        await hass.config_entries.async_forward_entry_setup(entry, component)

    # Service functions
    async def get_car(service_call):
        """Get VIN associated with HomeAssistant device ID."""
        # Get device entry
        dev_id = service_call.data.get("device_id")
        dev_reg = device_registry.async_get(hass)
        dev_entry = dev_reg.async_get(dev_id)

        # Get vehicle VIN from device identifiers
        skoda_identifiers = [
            identifier
            for identifier in dev_entry.identifiers
            if identifier[0] == DOMAIN
        ]
        vin_identifier = next(iter(skoda_identifiers))
        vin = vin_identifier[1]

        # Get coordinator handling the device entry
        conf_entry = next(iter(dev_entry.config_entries))
        try:
            dev_coordinator = hass.data[DOMAIN][conf_entry]['data'].coordinator
        except:
            raise SkodaConfigException('Could not find associated coordinator for given vehicle')

        # Return with associated Vehicle class object
        return dev_coordinator.connection.vehicle(vin)

    async def set_schedule(service_call=None):
        """Set departure schedule."""
        try:
            # Prepare data
            id = service_call.data.get("id", 0)
            temp = None
            spin = service_call.data.get("spin", None)


            # Convert datetime objects to simple strings or check that strings are correctly formatted
            try:
                time = service_call.data.get("time").strftime("%H:%M")
            except:
                if re.match('^[0-9]{2}:[0-9]{2}$', service_call.data.get('time', '')):
                    time = service_call.data.get("time", "08:00")
                else:
                    raise SkodaInvalidRequestException(f"Invalid time string: {service_call.data.get('time')}")
            if service_call.data.get("off_peak_start", False):
                try:
                    peakstart = service_call.data.get("off_peak_start").strftime("%H:%M")
                except:
                    if re.match('^[0-9]{2}:[0-9]{2}$', service_call.data.get("off_peak_start", "")):
                        peakstart = service_call.data.get("off_peak_start", "00:00")
                    else:
                        raise SkodaInvalidRequestException(f"Invalid value for off peak start hours: {service_call.data.get('off_peak_start')}")
            if service_call.data.get("off_peak_end", False):
                try:
                    peakend = service_call.data.get("off_peak_end").strftime("%H:%M")
                except:
                    if re.match('^[0-9]{2}:[0-9]{2}$', service_call.data.get("off_peak_end", "")):
                        peakend = service_call.data.get("off_peak_end", "00:00")
                    else:
                        raise SkodaInvalidRequestException(f"Invalid value for off peak end hours: {service_call.data.get('off_peak_end')}")

            # Convert to parseable data
            schedule = {
                "id": service_call.data.get("id", 1),
                "enabled": service_call.data.get("enabled"),
                "recurring": service_call.data.get("recurring"),
                "date": service_call.data.get("date"),
                "time": time,
                "days": service_call.data.get("days", "nnnnnnn"),
            }
            # Set optional values
            # Heater source
            if service_call.data.get("heater_source", None) is not None:
                if service_call.data.get("heater_source", False) is True:
                    if spin is None:
                        raise SkodaInvalidRequestException("S-PIN is required when using auxiliary heater.")
                    schedule["heaterSource"] = "automatic"
                else:
                    schedule["heaterSource"] = "electric"
            # Night rate
            if service_call.data.get("off_peak_active", None) is not None:
                schedule["nightRateActive"] = service_call.data.get("off_peak_active")
            if service_call.data.get("off_peak_start", None) is not None:
                schedule["nightRateTimeStart"] = service_call.data.get("off_peak_start")
            if service_call.data.get("off_peak_end", None) is not None:
                schedule["nightRateTimeEnd"] = service_call.data.get("off_peak_end")
            # Climatisation and charging options
            if service_call.data.get("climatisation", None) is not None:
                schedule["operationClimatisation"] = service_call.data.get("climatisation")
            if service_call.data.get("charging", None) is not None:
                schedule["operationCharging"] = service_call.data.get("charging")
            if service_call.data.get("charge_target", None) is not None:
                schedule["targetChargeLevel"] = service_call.data.get("charge_target")
            if service_call.data.get("charge_current", None) is not None:
                schedule["chargeMaxCurrent"] = service_call.data.get("charge_current")
            # Global optional options
            if service_call.data.get("temp", None) is not None:
                schedule["targetTemp"] = service_call.data.get("temp")

            # Find the correct car and execute service call
            car = await get_car(service_call)
            _LOGGER.info(f'Set departure schedule {id} with data {schedule} for car {car.vin}')
            state = await car.set_timer_schedule(id, schedule, spin)
            if state is not False:
                _LOGGER.debug(f"Service call 'set_schedule' executed without error")
                await coordinator.async_request_refresh()
            else:
                _LOGGER.warning(f"Failed to execute service call 'set_schedule' with data '{service_call}'")
        except (SkodaInvalidRequestException) as e:
            _LOGGER.warning(f"Service call 'set_schedule' failed. {e}")
        except Exception as e:
            raise

    async def set_charge_limit(service_call=None):
        """Set minimum charge limit."""
        try:
            car = await get_car(service_call)

            # Get charge limit and execute service call
            limit = service_call.data.get("limit", 50)
            state = await car.set_charge_limit(limit)
            if state is not False:
                _LOGGER.debug(f"Service call 'set_charge_limit' executed without error")
                await coordinator.async_request_refresh()
            else:
                _LOGGER.warning(f"Failed to execute service call 'set_charge_limit' with data '{service_call}'")
        except (SkodaInvalidRequestException) as e:
            _LOGGER.warning(f"Service call 'set_charge_limit' failed {e}")
        except Exception as e:
            raise

    async def set_current(service_call=None):
        """Set departure schedule."""
        try:
            car = await get_car(service_call)

            # Get charge current and execute service call
            current = service_call.data.get('current', None)
            state = await car.set_charger_current(current)
            if state is not False:
                _LOGGER.debug(f"Service call 'set_current' executed without error")
                await coordinator.async_request_refresh()
            else:
                _LOGGER.warning(f"Failed to execute service call 'set_current' with data '{service_call}'")
        except (SkodaInvalidRequestException) as e:
            _LOGGER.warning(f"Service call 'set_current' failed {e}")
        except Exception as e:
            raise

    async def set_pheater_duration(service_call=None):
        """Set duration for parking heater."""
        try:
            car = await get_car(service_call)
            car.pheater_duration = service_call.data.get("duration", car.pheater_duration)
            _LOGGER.debug(f"Service call 'set_pheater_duration' executed without error")
            await coordinator.async_request_refresh()
        except (SkodaInvalidRequestException) as e:
            _LOGGER.warning(f"Service call 'set_pheater_duration' failed {e}")
        except Exception as e:
            raise

    async def set_climater(service_call=None):
        """Start or stop climatisation with options."""
        try:
            car = await get_car(service_call)

            if service_call.data.get('enabled'):
                action = 'auxiliary' if service_call.data.get('aux_heater', False) else 'electric'
                temp = service_call.data.get('temp', None)
                hvpower = service_call.data.get('battery_power', None)
                spin = service_call.data.get('spin', None)
            else:
                action = 'off'
                temp = hvpower = spin = None
            # Execute service call
            if await car.set_climatisation(action, temp, hvpower, spin) is True:
                _LOGGER.debug("Service call 'set_climater' executed without error")
                await coordinator.async_request_refresh()
            else:
                _LOGGER.warning(f"Failed to execute service call 'set_climater' with data '{service_call}'")
        except (SkodaInvalidRequestException) as e:
            _LOGGER.warning(f"Service call 'set_climater' failed {e}")
        except Exception as e:
            raise

    # Register services
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_SCHEDULE,
        set_schedule,
        schema = SERVICE_SET_SCHEDULE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_MAX_CURRENT,
        set_current,
        schema = SERVICE_SET_MAX_CURRENT_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_CHARGE_LIMIT,
        set_charge_limit,
        schema = SERVICE_SET_CHARGE_LIMIT_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_CLIMATER,
        set_climater,
        schema = SERVICE_SET_CLIMATER_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_PHEATER_DURATION,
        set_pheater_duration,
        schema = SERVICE_SET_PHEATER_DURATION_SCHEMA
    )
    return True

def update_callback(hass, coordinator):
    _LOGGER.debug("CALLBACK!")
    hass.async_create_task(
        coordinator.async_request_refresh()
    )

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the component from configuration.yaml."""
    hass.data.setdefault(DOMAIN, {})

    if hass.config_entries.async_entries(DOMAIN):
        return True

    if DOMAIN in config:
        _LOGGER.info("Found existing Skoda Connect configuration.")
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data=config[DOMAIN],
            )
        )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    _LOGGER.debug("Unloading services")
    hass.services.async_remove(DOMAIN, SERVICE_SET_SCHEDULE)
    hass.services.async_remove(DOMAIN, SERVICE_SET_MAX_CURRENT)
    hass.services.async_remove(DOMAIN, SERVICE_SET_CHARGE_LIMIT)
    hass.services.async_remove(DOMAIN, SERVICE_SET_CLIMATER)
    hass.services.async_remove(DOMAIN, SERVICE_SET_PHEATER_DURATION)
    return await async_unload_coordinator(hass, entry)

async def async_unload_coordinator(hass: HomeAssistant, entry: ConfigEntry):
    """Unload auth token based entry."""
    _LOGGER.debug("Unloading update listener")
    hass.data[DOMAIN][entry.entry_id][UNDO_UPDATE_LISTENER]()
    hass.data[DOMAIN][entry.entry_id].pop(UNDO_UPDATE_LISTENER, None)

    _LOGGER.debug("Unloading coordinator")
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA].coordinator
    await coordinator.async_logout()
    _LOGGER.debug("Waiting for shutdown to complete")
    unloaded = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in PLATFORMS
                if platform in coordinator.platforms
            ]
        )
    )
    if unloaded:
        _LOGGER.debug("Unloading entry")
        del hass.data[DOMAIN][entry.entry_id]

    if not hass.data[DOMAIN]:
        _LOGGER.debug("Unloading data")
        del hass.data[DOMAIN]

    return unloaded

async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""
    # Do a lazy reload of integration when configuration changed
    await hass.config_entries.async_reload(entry.entry_id)

def get_convert_conf(entry: ConfigEntry):
    return CONF_SCANDINAVIAN_MILES if entry.options.get(
        CONF_SCANDINAVIAN_MILES,
        entry.data.get(
            CONF_SCANDINAVIAN_MILES,
            False
        )
    ) else CONF_NO_CONVERSION

async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Migrate configuration from old version to new."""
    _LOGGER.debug(f'Migrating from version {entry.version}')

    # Migrate data from version 1, pre 1.0.57
    if entry.version == 1:
        # Make a copy of old config
        new_data = {**entry.data}
        new_options = {**entry.options}

        # Convert from minutes to seconds for poll interval
        minutes = entry.options.get("update_interval", 1)
        seconds = minutes*60
        new_data.pop("update_interval", None)
        new_data[CONF_SCAN_INTERVAL] = seconds
        # Default "save session" to false
        new_options[CONF_SAVESESSION] = False

        # Save "new" config
        entry.data = {**new_data}
        entry.options = {**new_options}
        entry.version = 3
        hass.config_entries.async_update_entry(entry, data=new_data, options=new_options)

    # Migrate data from version 2, pre version 1.2
    if entry.version == 2:
        # Make a copy of old config
        new_data = {**entry.data}
        new_options = {**entry.options}

        # Default "save session" to false
        new_options[CONF_SAVESESSION] = False
        new_data[CONF_TOKENS] = {}

        # Save "new" config
        #entry.options = {**new_options}
        #entry.data = {**new_data}
        entry.version = 3
        hass.config_entries.async_update_entry(entry, data=new_data, options=new_options)

    _LOGGER.info("Migration to version %s successful", entry.version)
    return True


class SkodaData:
    """Hold component state."""

    def __init__(self, config, name=None, coordinator=None):
        """Initialize the component state."""
        self.vehicles = set()
        self.instruments = set()
        self.config = config.get(DOMAIN, config)
        self.name = name
        self.coordinator = coordinator

    def instrument(self, vin, component, attr):
        """Return corresponding instrument."""
        return next(
            (
                instrument
                for instrument in (
                    self.coordinator.data
                    if self.coordinator is not None
                    else self.instruments
                )
                if instrument.vehicle.vin == vin
                and instrument.component == component
                and instrument.attr == attr
            ),
            None,
        )

    def vehicle_name(self, vehicle):
        """Provide a friendly name for a vehicle."""
        try:
            # Return name if configured by user
            if isinstance(self.name, str):
                if len(self.name) > 0:
                    return self.name
        except:
            pass

        # Default name to nickname if supported, else vin number
        try:
            if vehicle.is_nickname_supported:
                return vehicle.nickname
            elif vehicle.vin:
                return vehicle.vin
        except:
            _LOGGER.info(f"Name set to blank")
            return ""


class SkodaEntity(Entity):
    """Base class for all Skoda entities."""

    def __init__(self, data, vin, component, attribute, callback=None):
        """Initialize the entity."""

        def update_callbacks():
            if callback is not None:
                callback(self.hass, data.coordinator)

        self.data = data
        self.vin = vin
        self.component = component
        self.attribute = attribute
        self.coordinator = data.coordinator
        self.instrument.callback = update_callbacks
        self.callback = callback

    async def async_update(self) -> None:
        """Update the entity.

        Only used by the generic entity update service.
        """

        # Ignore manual update requests if the entity is disabled
        if not self.enabled:
            return

        await self.coordinator.async_request_refresh()

    async def async_added_to_hass(self):
        """Register update dispatcher."""
        if self.coordinator is not None:
            self.async_on_remove(
                self.coordinator.async_add_listener(self.async_write_ha_state)
            )
        else:
            self.async_on_remove(
                async_dispatcher_connect(
                    self.hass, SIGNAL_STATE_UPDATED, self.async_write_ha_state
                )
            )

    @property
    def instrument(self):
        """Return corresponding instrument."""
        return self.data.instrument(self.vin, self.component, self.attribute)

    @property
    def icon(self):
        """Return the icon."""
        if self.instrument.attr in ["battery_level", "charging"]:
            return icon_for_battery_level(
                battery_level=self.instrument.state, charging=self.vehicle.charging
            )
        if self.instrument.attr in ["plug_autounlock"]:
            if self.instrument.state == True:
                return "mdi:battery-lock-open"
            else:
                return "mdi:battery-lock"
        return self.instrument.icon

    @property
    def vehicle(self):
        """Return vehicle."""
        return self.instrument.vehicle

    @property
    def _entity_name(self):
        return self.instrument.name

    @property
    def _vehicle_name(self):
        return self.data.vehicle_name(self.vehicle)

    @property
    def name(self):
        """Return full name of the entity."""
        return f"{self._vehicle_name} {self._entity_name}"

    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def assumed_state(self):
        """Return true if unable to access real state of entity."""
        return True

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        attributes = dict(
            self.instrument.attributes,
            model=f"{self.vehicle.model}/{self.vehicle.model_year}",
        )

        # Return model image as picture attribute for position entity
        if "position" in self.attribute:
            # Try to use small thumbnail first hand, else fallback to fullsize
            if self.vehicle.is_model_image_small_supported:
                attributes["entity_picture"] = self.vehicle.model_image_small
            elif self.vehicle.is_model_image_large_supported:
                attributes["entity_picture"] = self.vehicle.model_image_large

        return attributes

    @property
    def device_info(self):
        """Return the device_info of the device."""
        return {
            "identifiers": {(DOMAIN, self.vin)},
            "name": self._vehicle_name,
            "manufacturer": "Skoda",
            "model": self.vehicle.model,
            "sw_version": self.vehicle.model_year,
        }

    @property
    def available(self):
        """Return if sensor is available."""
        if self.data.coordinator is not None:
            return self.data.coordinator.last_update_success
        return True

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"{self.vin}-{self.component}-{self.attribute}"


class SkodaCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    def __init__(self, hass: HomeAssistant, entry, update_interval: timedelta):
        self.vin = entry.data[CONF_VEHICLE].upper()
        self.hass = hass
        self.entry = entry
        self.platforms = []
        self.report_last_updated = None
        self.connection = Connection(
            session=async_get_clientsession(hass),
            username=self.entry.data[CONF_USERNAME],
            password=self.entry.data[CONF_PASSWORD],
            fulldebug=self.entry.options.get(CONF_DEBUG, self.entry.data.get(CONF_DEBUG, DEFAULT_DEBUG)),
        )

        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=update_interval)

    async def _async_update_data(self):
        """Update data via library."""
        vehicle = await self.update()

        if not vehicle:
            raise UpdateFailed("No vehicles found.")

        # Backward compatibility
        default_convert_conf = get_convert_conf(self.entry)

        convert_conf = self.entry.options.get(
            CONF_CONVERT,
            self.entry.data.get(
                CONF_CONVERT,
                default_convert_conf
            )
        )

        dashboard = vehicle.dashboard(
            mutable=self.entry.options.get(CONF_MUTABLE),
            spin=self.entry.options.get(CONF_SPIN),
            miles=convert_conf == CONF_IMPERIAL_UNITS,
            scandinavian_miles=convert_conf == CONF_SCANDINAVIAN_MILES,
        )

        return dashboard.instruments

    async def async_logout(self, event=None):
        """Logout from Skoda Connect"""
        _LOGGER.debug("Shutdown Skoda Connect")
        try:
            entry_options = self.entry.options.copy()
            entry_data = self.entry.data.copy()
            # Unload update listener
            try:
                if UNDO_UPDATE_LISTENER in self.hass.data[DOMAIN][self.entry.entry_id]:
                    _LOGGER.debug(f"Unloading update listener")
                    self.hass.data[DOMAIN][self.entry.entry_id][UNDO_UPDATE_LISTENER]()
            except Exception as e:
                _LOGGER.debug(f"Unloading update listener")
                # If config is only reloaded this will throw an exception
                pass

            if entry_options.get(CONF_SAVESESSION, False):
                try:
                    # Save session is true, save tokens for all clients
                    tokens = await self.connection.save_tokens()
                    if tokens is not False:
                        _LOGGER.debug('Successfully fetched tokens to save')
                        entry_data[CONF_TOKENS] = tokens
                        _LOGGER.debug("Saving tokens to config registry")
                        self.hass.config_entries.async_update_entry(
                            self.entry,
                            data=entry_data,
                            options=entry_options
                        )
                        _LOGGER.debug("Save complete.")
                    else:
                        _LOGGER.debug(f'Save tokens failed.')
                except Exception as e:
                    raise SkodaException(f'Save tokens failed: {e}')
            else:
                try:
                    # Save session is false, remove any saved tokens
                    entry_data[CONF_TOKENS] = {}
                    _LOGGER.debug("Removing tokens from config registry")
                    self.hass.config_entries.async_update_entry(
                        self.entry,
                        data=entry_data,
                        options=entry_options
                    )
                    # Revoke tokens
                    _LOGGER.debug("Terminate connection")
                    await self.connection.terminate()
                except Exception as e:
                    raise SkodaException(f'Revocation of tokens failed: {e}')
            # Clear connection session
            _LOGGER.debug('Unloading library connection')
            self.connection = None
        except (SkodaException) as e:
            _LOGGER.error(e)
            return False
        except Exception as ex:
            _LOGGER.error('Errors occured during shutdown.')
            return False
        return True

    async def async_login(self):
        """Login to Skoda Connect"""
        # Check if we can login
        try:
            restore = False
            if self.entry.options.get(CONF_SAVESESSION, False):
                if len(self.entry.data.get(CONF_TOKENS, {})) != 0:
                    if await self.connection.restore_tokens(self.entry.data.get(CONF_TOKENS, None)):
                        restore = True
            if restore is False:
                if await self.connection.doLogin() is False:
                    _LOGGER.warning(
                        "Could not login to Skoda Connect, please check your credentials and verify that the service is working"
                    )
                    return False
            # Get associated vehicles before we continue
            await self.connection.get_vehicles()
            return True
        except (SkodaAccountLockedException, SkodaAuthenticationException) as e:
            # Raise auth failed error in config flow
            raise ConfigEntryAuthFailed(e) from e
        except:
            raise

    async def update(self) -> Union[bool, Vehicle]:
        """Update status from Skoda Connect"""

        # Update vehicle data
        _LOGGER.debug("Updating data from Skoda Connect")
        try:
            # Get Vehicle object matching VIN number
            vehicle = self.connection.vehicle(self.vin)
            if await vehicle.update():
                return vehicle
            else:
                _LOGGER.warning("Could not query update from Skoda Connect")
                return False
        except Exception as error:
            _LOGGER.warning(f"An error occured while requesting update from Skoda Connect: {error}")
            return False
