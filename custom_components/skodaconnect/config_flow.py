import homeassistant.helpers.config_validation as cv
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_RESOURCES,
    CONF_USERNAME,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from skodaconnect import Connection
from . import get_convert_conf
from .const import (
    CONF_CONVERT,
    CONF_SCANDINAVIAN_MILES,
    CONF_IMPERIAL_UNITS,
    CONF_NO_CONVERSION,
    CONF_DEBUG,
    CONVERT_DICT,
    CONF_MUTABLE,
    CONF_UPDATE_INTERVAL,
    CONF_SPIN,
    CONF_VEHICLE,
    CONF_INSTRUMENTS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    DEFAULT_DEBUG
)

_LOGGER = logging.getLogger(__name__)

class SkodaConnectConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    task_login = None
    task_finish = None
    entry = None

    def __init__(self):
        """Initialize."""
        self._entry = None
        self._init_info = {}
        self._data = {}
        self._options = {}
        self._errors = {}
        self._connection = None
        self._session = None

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            self.task_login = None
            self.task_update = None
            self.task_finish = None
            self._errors = {}
            self._data = {
                CONF_USERNAME: user_input[CONF_USERNAME],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
                CONF_INSTRUMENTS: {},
                CONF_VEHICLE: None
            }
            # Set default options
            self._options = {
                CONF_CONVERT: CONF_NO_CONVERSION,
                CONF_MUTABLE: True,
                CONF_UPDATE_INTERVAL: 5,
                CONF_DEBUG: False,
                CONF_SPIN: None,
                CONF_RESOURCES: []
            }

            _LOGGER.debug("Creating connection to Skoda Connect")
            self._connection = Connection(
                session=async_get_clientsession(self.hass),
                username=self._data[CONF_USERNAME],
                password=self._data[CONF_PASSWORD],
                fulldebug=False
            )

            return await self.async_step_login()

        return self.async_show_form(
            step_id="user", data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): cv.string,
                    vol.Required(CONF_PASSWORD): cv.string,
                }
            ), errors=self._errors
        )

    # noinspection PyBroadException
    async def _async_task_login(self):
        try:
            await self._connection.doLogin()
        except Exception as e:
            _LOGGER.error("Failed to login due to error: %s", str(e))
            self._errors["base"] = "cannot_connect"

        if not self._connection.logged_in:
            self._errors["base"] = "cannot_connect"

        self.hass.async_create_task(
            self.hass.config_entries.flow.async_configure(flow_id=self.flow_id)
        )

    async def async_step_vehicle(self, user_input=None):
        if user_input is not None:
            self._data[CONF_VEHICLE] = user_input[CONF_VEHICLE]
            self._options[CONF_SPIN] = user_input[CONF_SPIN]
            self._options[CONF_MUTABLE] = user_input[CONF_MUTABLE]
            return await self.async_step_monitoring()

        vin_numbers = self._init_info["CONF_VEHICLES"].keys()
        return self.async_show_form(
            step_id="vehicle",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_VEHICLE, default=next(iter(vin_numbers))): vol.In(vin_numbers),
                    vol.Optional(CONF_SPIN, default=""): cv.string,
                    vol.Required(CONF_MUTABLE, default=True): cv.boolean
                }
            ), errors=self._errors
        )

    async def async_step_monitoring(self, user_input=None):
        if user_input is not None:
            self._options[CONF_RESOURCES] = user_input[CONF_RESOURCES]
            self._options[CONF_CONVERT] = user_input[CONF_CONVERT]
            self._options[CONF_UPDATE_INTERVAL] = user_input[CONF_UPDATE_INTERVAL]
            self._options[CONF_DEBUG] = user_input[CONF_DEBUG]

            await self.async_set_unique_id(self._data[CONF_VEHICLE])
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=self._data[CONF_VEHICLE],
                data=self._data,
                options=self._options
            )

        instruments = self._init_info["CONF_VEHICLES"][self._data[CONF_VEHICLE]]
        instruments_dict = {
            instrument.attr: instrument.name for instrument in instruments
        }
        self._data[CONF_INSTRUMENTS] = dict(sorted(instruments_dict.items(), key=lambda item: item[1]))

        return self.async_show_form(
            step_id="monitoring",
            errors=self._errors,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_RESOURCES, default=list(self._data[CONF_INSTRUMENTS].keys())
                    ): cv.multi_select(self._data[CONF_INSTRUMENTS]),
                    vol.Required(
                        CONF_CONVERT, default=CONF_NO_CONVERSION
                    ): vol.In(CONVERT_DICT),
                    vol.Required(
                        CONF_UPDATE_INTERVAL, default=1
                    ): cv.positive_int,
                    vol.Required(
                        CONF_DEBUG, default=False
                    ): cv.boolean
                }
            ),
        )

   # Authentication and login
    async def async_step_login(self, user_input=None):
        if not self.task_login:
            self.task_login = self.hass.async_create_task(self._async_task_login())

            return self.async_show_progress(
                step_id="login",
                progress_action="task_login",
            )

        # noinspection PyBroadException
        try:
            await self.task_login
        except Exception:
            return self.async_abort(reason="Failed to connect to Skoda Connect")

        if self._errors:
            return self.async_show_progress_done(next_step_id="user")

        for vehicle in self._connection.vehicles:
            _LOGGER.info(f"Found data for VIN: {vehicle.vin} from Skoda Connect")
        if len(self._connection.vehicles) == 0:
            return self.async_abort(reason="Skoda Connect account didn't return any vehicles")

        self._init_info["CONF_VEHICLES"] = {
            vehicle.vin: vehicle.dashboard().instruments
            for vehicle in self._connection.vehicles
        }

        return self.async_show_progress_done(next_step_id="vehicle")

    async def async_step_reauth(self, entry) -> dict:
        """Handle initiation of re-authentication with Skoda Connect."""
        self.entry = entry
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict = None) -> dict:
        """Handle re-authentication with Skoda Connect."""
        errors: dict = {}

        if user_input is not None:
            _LOGGER.debug("Creating connection to Skoda Connect")
            self._connection = Connection(
                session=async_get_clientsession(self.hass),
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                fulldebug=self.entry.options.get(CONF_DEBUG, self.entry.data.get(CONF_DEBUG, DEFAULT_DEBUG)),
            )

            # noinspection PyBroadException
            try:
                await self._connection.doLogin()

                if not await self._connection.validate_login:
                    _LOGGER.debug("Unable to login to Skoda Connect. Need to accept a new EULA/T&C? Try logging in to the portal: https://www.skoda-connect.com/")
                    errors["base"] = "cannot_connect"
                else:
                    data = self.entry.data.copy()
                    self.hass.config_entries.async_update_entry(
                        self.entry,
                        data={
                            **data,
                            CONF_USERNAME: user_input[CONF_USERNAME],
                            CONF_PASSWORD: user_input[CONF_PASSWORD],
                        },
                    )
                    self.hass.async_create_task(
                        self.hass.config_entries.async_reload(self.entry.entry_id)
                    )

                    return self.async_abort(reason="reauth_successful")
            except Exception as e:
                _LOGGER.error("Failed to login due to error: %s", str(e))
                return self.async_abort(reason="Failed to connect to Connect")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=self.entry.data[CONF_USERNAME]): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )
   # Configuration.yaml import
    async def async_step_import(self, yaml):
        """Import existing configuration from YAML config."""
        # Set default data and options
        self._data = {
            CONF_USERNAME: None,
            CONF_PASSWORD: None,
            CONF_INSTRUMENTS: {},
            CONF_VEHICLE: None
        }
        self._options = {
            CONF_CONVERT: CONF_NO_CONVERSION,
            CONF_MUTABLE: True,
            CONF_UPDATE_INTERVAL: 5,
            CONF_DEBUG: False,
            CONF_SPIN: None,
            CONF_RESOURCES: []
        }
        self._init_info = {}

        # Check if integration is already configured
        if self._async_current_entries():
            _LOGGER.info(f"Integration is already setup, please remove yaml configuration as it is deprecated")

        # Validate and convert yaml config
        if all (entry in yaml for entry in ("username", "password")):
            self._data[CONF_USERNAME] = yaml["username"]
            self._data[CONF_PASSWORD] = yaml["password"]
        else:
            return False
        if "spin" in yaml:
            self._options[CONF_SPIN] = yaml["spin"]
        if "scandinavian_miles" in yaml:
            if yaml["scandinavian_miles"]:
                self._options[CONF_CONVERT] = "scandinavian_miles"
        if "scan_interval" in yaml:
            if "minutes" in yaml["scan_interval"]:
                self._options[CONF_UPDATE_INTERVAL] = int(yaml["scan_interval"]["minutes"])
        if "name" in yaml:
            vin = next(iter(yaml["name"]))
            self._data[CONF_VEHICLE] = vin.upper()
        if "response_debug" in yaml:
                if yaml["response_debug"]:
                    self._options[CONF_DEBUG] = True

        # Try to login and fetch vehicles
        self._connection = Connection(
            session=async_get_clientsession(self.hass),
            username=self._data[CONF_USERNAME],
            password=self._data[CONF_PASSWORD],
            fulldebug=False
        )
        await self._connection.doLogin()

        if len(self._connection.vehicles) == 0:
            return self.async_abort(reason="Skoda Connect account didn't return any vehicles")
        self._init_info["CONF_VEHICLES"] = {
            vehicle.vin: vehicle.dashboard().instruments
            for vehicle in self._connection.vehicles
        }

        if self._data[CONF_VEHICLE] is None:
            self._data[CONF_VEHICLE] = next(iter(self._init_info["CONF_VEHICLES"]))
        elif self._data[CONF_VEHICLE] not in self._init_info["CONF_VEHICLES"]:
            self._data[CONF_VEHICLE] = next(iter(self._init_info["CONF_VEHICLES"]))

        await self.async_set_unique_id(self._data[CONF_VEHICLE])
        self._abort_if_unique_id_configured()

        instruments = self._init_info["CONF_VEHICLES"][self._data[CONF_VEHICLE]]
        instruments_dict = {
            instrument.attr: instrument.name for instrument in instruments
        }

        if "resources" in yaml:
            for resource in yaml["resources"]:
                if resource in instruments_dict:
                    self._options[CONF_RESOURCES].append(resource)

        return self.async_create_entry(
            title=self._data[CONF_VEHICLE],
            data=self._data,
            options=self._options
        )


    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return SkodaConnectOptionsFlowHandler(config_entry)


class SkodaConnectOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle SkodaConnect options."""

    def __init__(self, config_entry: ConfigEntry):
        """Initialize domain options flow."""
        super().__init__()

        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""

        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            options = self._config_entry.options.copy()
            options[CONF_UPDATE_INTERVAL] = user_input.get(CONF_UPDATE_INTERVAL, 1)
            options[CONF_SPIN] = user_input.get(CONF_SPIN, None)
            options[CONF_DEBUG] = user_input.get(CONF_DEBUG, False)
            options[CONF_RESOURCES] = user_input.get(CONF_RESOURCES, [])
            options[CONF_CONVERT] = user_input.get(CONF_CONVERT, CONF_NO_CONVERSION)
            return self.async_create_entry(
                title=self._config_entry,
                data={
                    **options,
                },
            )

        instruments = self._config_entry.data.get(CONF_INSTRUMENTS, {})

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_UPDATE_INTERVAL,
                        default=self._config_entry.options.get(CONF_UPDATE_INTERVAL,
                            self._config_entry.data.get(CONF_UPDATE_INTERVAL, 5)
                        )
                    ): cv.positive_int,
                    vol.Optional(
                        CONF_SPIN,
                        default=self._config_entry.options.get(CONF_SPIN,
                            self._config_entry.data.get(CONF_SPIN, "")
                        )
                    ): cv.string,
                    vol.Optional(
                        CONF_DEBUG,
                        default=self._config_entry.options.get(CONF_DEBUG,
                            self._config_entry.data.get(CONF_DEBUG, False)
                        )
                    ): cv.boolean,
                    vol.Optional(
                        CONF_RESOURCES,
                        default=self._config_entry.options.get(CONF_RESOURCES,
                            self._config_entry.data.get(CONF_RESOURCES, [])
                        )
                    ): cv.multi_select(
                        self._config_entry.data.get(
                            CONF_INSTRUMENTS,
                            self._config_entry.options.get(CONF_RESOURCES, {})
                        )
                    ),
                    vol.Optional(
                        CONF_CONVERT,
                        default=self._config_entry.options.get(CONF_CONVERT,
                            self._config_entry.data.get(CONF_CONVERT, "no_conversion")
                        )
                    ): vol.In(CONVERT_DICT),
                }
            ),
        )
