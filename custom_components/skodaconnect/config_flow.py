import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_DEVICES,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_RESOURCES,
    CONF_SCAN_INTERVAL,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_validation as cv

from skodaconnect import Connection
from skodaconnect.exceptions import SkodaAccountLockedException, SkodaLoginFailedException

from .const import (
    DOMAIN,
    CONVERT_DICT,
    CONF_CONVERT,
    CONF_NO_CONVERSION,
    CONF_MIN_SCAN_INTERVAL,
    CONF_MAX_SCAN_INTERVAL,
    CONF_DEFAULT_SCAN_INTERVAL,
    CONF_DEBUG,
    CONF_MUTABLE,
    CONF_SPIN,
)

_LOGGER = logging.getLogger(__name__)


class SkodaConnectConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle Skoda Connect config flow instance."""

    VERSION = 3

    def __init__(self):
        """Initialize flow instance."""
        self._connection = None
        self.task_login = None
        self.task_get_vehicles = None
        self.error = None
        self.data = {}

   # Config flow steps
    # Initial step - User input
    async def async_step_user(self, user_input=None):
        """Handle start of Skoda Connect config flow."""
        if user_input is not None:
            self.task_login = None
            self.error = None
            # Abort if this account is already configured
            await self.async_set_unique_id(user_input[CONF_USERNAME])
            self._abort_if_unique_id_configured()
            self.data = {
                CONF_USERNAME: user_input.get(CONF_USERNAME, None),
                CONF_PASSWORD: user_input.get(CONF_PASSWORD, None),
                CONF_SPIN: user_input.get(CONF_SPIN, None),
                CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL, CONF_DEFAULT_SCAN_INTERVAL),
                CONF_CONVERT: user_input.get(CONF_CONVERT, CONF_NO_CONVERSION),
                CONF_MUTABLE: user_input.get(CONF_MUTABLE, True),
                CONF_DEBUG: user_input.get(CONF_DEBUG, False),
                CONF_DEVICES: [],
            }
            return await self.async_step_login()

        return await self._async_setup_form()

    # Return user input form
    async def _async_setup_form(self):
        """Show the initial setup form."""
        return self.async_show_form(
            step_id="user", data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=self.data.get(CONF_USERNAME, "")
                    ): cv.string,
                    vol.Required(
                        CONF_PASSWORD,
                        default=self.data.get(CONF_PASSWORD, "")
                    ): cv.string,
                    vol.Optional(
                        CONF_SPIN,
                        default=self.data.get(CONF_SPIN, "")
                    ): cv.string,
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=self.data.get(CONF_SCAN_INTERVAL, CONF_DEFAULT_SCAN_INTERVAL)
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=CONF_MIN_SCAN_INTERVAL, max=CONF_MAX_SCAN_INTERVAL)
                    ),
                    vol.Required(
                        CONF_CONVERT,
                        default=self.data.get(CONF_CONVERT, CONF_NO_CONVERSION)
                    ): vol.In(CONVERT_DICT),
                    vol.Required(
                        CONF_MUTABLE,
                        default=self.data.get(CONF_MUTABLE, True)
                    ): cv.boolean,
                    vol.Optional(
                        CONF_DEBUG,
                        default=self.data.get(CONF_DEBUG, False)
                    ): cv.boolean,
                }
            ), errors={"base": self.error}
        )

    # Step 2 - Validate credentials via login background task
    async def async_step_login(self, user_input=None):
        """Test login with credentials."""
        # Create background task if it doesn't exist
        if not self.task_login:
            self.task_login = self.hass.async_create_task(self._async_task_login())
            return self.async_show_progress(
                step_id="login",
                progress_action="task_login",
            )

        # If errors were encountered, return to setup form and display them
        if self.error:
            _LOGGER.debug(f"Error is: {self.error}")
            return self.async_show_progress_done(next_step_id="user")

        # Wait for background login task, abort if it fails
        try:
            await self.task_login
        except Exception:
            return self.async_abort(reason="An error occured when trying to login.")

        # If login doesn't encounter errors initiate next step, get vehicles
        return self.async_show_progress_done(next_step_id="get_vehicles")

    # Step 3 - Validate account via fetching vehicles associated
    async def async_step_get_vehicles(self, user_input=None):
        """Fetch vehicles associated with account."""
        # Create background task if it doesn't exist
        if not self.task_get_vehicles:
            self.task_get_vehicles = self.hass.async_create_task(self._async_task_get_vehicles())

            return self.async_show_progress(
                step_id="get_vehicles",
                progress_action="task_get_vehicles"
            )

        # Try to fetch vehicles associated with account and abort if it fails
        try:
            await self.task_get_vehicles
        except Exception:
            return self.async_abort(reason="An error occured when trying to fetch vehicles associated with account.")

        # If errors were encountered, return to credentials form and display them
        if self.error:
            return self.async_show_progress_done(next_step_id="user")

        # Check that discovered vehicles doesn't exist in old config entries
        for vehicle in self._connection.vehicles:
            # Add vehicle VIN to devices if it doesn't exist
            if vehicle.vin not in self.data[CONF_DEVICES]:
                self.data[CONF_DEVICES] += {
                    vehicle.vin: vehicle.nickname
                }
            for entry in self.hass.config_entries.async_entries(DOMAIN):
                if entry.unique_id == vehicle.vin:
                    return self.async_abort(reason=f"There's existing config for VIN {vehicle.vin}. Please remove it and try again.")

        return self.async_show_progress_done(next_step_id="create_entry")

    # Step 4 - Save config entry
    async def async_step_create_entry(self, user_input=None):
        """Finalize config flow and create config entry."""
        # Set config data
        config_data = {
            CONF_USERNAME: self.data[CONF_USERNAME],
            CONF_PASSWORD: self.data[CONF_PASSWORD],
            CONF_DEVICES: self.data[CONF_DEVICES],
        }
        # Set options, use defaults if not in user data
        config_options = {
            CONF_CONVERT: self.data.get(
                CONF_CONVERT,
                CONF_NO_CONVERSION
            ),
            CONF_MUTABLE: self.data.get(
                CONF_MUTABLE,
                True
            ),
            CONF_RESOURCES: self.data.get(
                CONF_DEVICES,
                []
            ),
            CONF_SCAN_INTERVAL: self.data.get(
                CONF_SCAN_INTERVAL,
                CONF_DEFAULT_SCAN_INTERVAL
            ),
            CONF_SPIN: self.data.get(
                CONF_SPIN,
                None
            ),
            CONF_DEBUG: self.data.get(
                CONF_DEBUG,
                False
            ),
        }
        # Save config entry
        return self.async_create_entry(
            title=config_data[CONF_USERNAME],
            data=config_data,
            options=config_options
        )


   # Background tasks
    async def _async_task_login(self):
        """Background login task."""
        try:
            _LOGGER.debug("Creating connection to Skoda Connect")
            self._connection = Connection(
                session=async_get_clientsession(self.hass),
                username=self.data[CONF_USERNAME],
                password=self.data[CONF_PASSWORD],
                fulldebug=False
            )
            self.error = None
            result = await self._connection.doLogin()
        except (SkodaAccountLockedException):
            self.error = "account_locked"
        except (SkodaLoginFailedException):
            self.error = "login_failed"
        except Exception as e:
            self.error = "cannot_connect"

        if self.error is None:
            if result is False and self.error is None:
                self.error = "cannot_connect"

        return self.hass.async_create_task(
            self.hass.config_entries.flow.async_configure(flow_id=self.flow_id)
        )

    async def _async_task_get_vehicles(self):
        """Background task to fetch vehicles."""
        try:
            result = await self._connection.get_vehicles()
        except Exception as e:
            self.error = "cannot_connect"

        if result is False:
            self.error = "cannot_connect"
        elif len(self._connection.vehicles) == 0:
            self.error = "no_vehicles"

        self.hass.async_create_task(
            self.hass.config_entries.flow.async_configure(flow_id=self.flow_id)
        )

   # Handle re-authentication
    async def async_step_reauth(self, entry) -> dict:
        """Handle initiation of re-authentication with Skoda Connect."""
        self.entry = entry
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict = None) -> dict:
        """Handle re-authentication with Skoda Connect."""
        error: dict = {}

        if user_input is not None:
            _LOGGER.debug("Creating connection to Skoda Connect")
            self._connection = Connection(
                session=async_get_clientsession(self.hass),
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                fulldebug=self.entry.options.get(CONF_DEBUG, self.entry.data.get(CONF_DEBUG, False)),
            )

            try:
                if not await self._connection.doLogin():
                    _LOGGER.debug("Unable to login to Skoda Connect. Need to accept a new EULA/T&C? Try logging in to the portal: https://www.skoda-connect.com/")
                    error = "cannot_connect"
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
                return self.async_abort(reason="Failed to connect to Connect")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=self.entry.data[CONF_USERNAME]): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ), errors={"base": error}
        )
   # Configuration.yaml import
    async def async_step_import(self, yaml):
        """Import existing configuration from YAML config."""
        # Set default data and options
        self._data = {
            CONF_USERNAME: None,
            CONF_PASSWORD: None,
        }
        self._options = {
            CONF_CONVERT: CONF_NO_CONVERSION,
            CONF_MUTABLE: True,
            CONF_SCAN_INTERVAL: CONF_DEFAULT_SCAN_INTERVAL,
            CONF_DEBUG: False,
            CONF_SPIN: None,
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
            seconds = CONF_DEFAULT_SCAN_INTERVAL
            minutes = 0
            if "seconds" in yaml["scan_interval"]:
                seconds = int(yaml["scan_interval"]["seconds"])
            if "minutes" in yaml["scan_interval"]:
                minutes = int(yaml["scan_interval"]["minutes"])
            self._options[CONF_SCAN_INTERVAL] = seconds+(minutes*60)
        if "response_debug" in yaml:
                if yaml["response_debug"]:
                    self._options[CONF_DEBUG] = True

        await self.async_set_unique_id(self._data[CONF_USERNAME])
        self._abort_if_unique_id_configured()

        # Try to login and fetch vehicles
        self._connection = Connection(
            session=async_get_clientsession(self.hass),
            username=self._data[CONF_USERNAME],
            password=self._data[CONF_PASSWORD],
            fulldebug=False
        )
        try:
            await self._connection.doLogin()
            await self._connection.get_vehicles()
        except:
            raise

        if len(self._connection.vehicles) == 0:
            return self.async_abort(reason="Skoda Connect account didn't return any vehicles")
        self._init_info["CONF_VEHICLES"] = {
            vehicle.vin: vehicle.dashboard().instruments
            for vehicle in self._connection.vehicles
        }

        return self.async_create_entry(
            title=self._data[CONF_USERNAME],
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
            # Save user input to options
            options = {
                CONF_CONVERT: user_input.get(
                    CONF_CONVERT,
                    CONF_NO_CONVERSION
                ),
                CONF_DEBUG: user_input.get(
                    CONF_DEBUG,
                    False
                ),
                CONF_MUTABLE: user_input.get(
                    CONF_MUTABLE,
                    True
                ),
                CONF_SCAN_INTERVAL: user_input.get(
                    CONF_SCAN_INTERVAL,
                    60
                ),
                CONF_SPIN: user_input.get(
                    CONF_SPIN,
                    None
                ),
                CONF_RESOURCES: user_input.get(
                    CONF_RESOURCES,
                    []
                )
            }

            return self.async_create_entry(
                title=self._config_entry,
                data={
                    **options,
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CONVERT,
                        default=self._config_entry.options.get(
                            CONF_CONVERT,
                            CONF_NO_CONVERSION
                        )): vol.In(CONVERT_DICT),
                    vol.Optional(
                        CONF_DEBUG,
                        default=self._config_entry.options.get(
                            CONF_DEBUG,
                            False
                        )): cv.boolean,
                    vol.Optional(
                        CONF_MUTABLE,
                        default=self._config_entry.options.get(
                            CONF_MUTABLE,
                            False
                        )): cv.boolean,
                    vol.Optional(
                        CONF_RESOURCES,
                        default=self._config_entry.options.get(
                            CONF_RESOURCES,
                            self._config_entry.data.get(CONF_DEVICES)
                        )): cv.multi_select(
                            self._config_entry.data.get(
                                CONF_DEVICES,
                                []
                            )
                        ),
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self._config_entry.options.get(
                            CONF_SCAN_INTERVAL,
                            CONF_DEFAULT_SCAN_INTERVAL
                        )): vol.All(
                            vol.Coerce(int),
                            vol.Range(
                                min=CONF_MIN_SCAN_INTERVAL,
                                max=CONF_MAX_SCAN_INTERVAL
                            )
                        ),
                    vol.Optional(
                        CONF_SPIN,
                        default=self._config_entry.options.get(
                            CONF_SPIN,
                            ""
                        )): cv.string,

                }
            ),
        )
