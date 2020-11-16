# Utilities for integration with Home Assistant
# Thanks to molobrakos

import logging
from utilities import camel2slug

_LOGGER = logging.getLogger(__name__)


class Instrument:
    def __init__(self, component, attr, name, icon=None):
        self.attr = attr
        self.component = component
        self.name = name
        self.vehicle = None
        self.icon = icon

    def __repr__(self):
        return self.full_name

    def configurate(self, **args):
        pass

    @property
    def slug_attr(self):
        return camel2slug(self.attr.replace(".", "_"))

    def setup(self, vehicle, **config):
        self.vehicle = vehicle
        if not self.is_supported:
            _LOGGER.debug("%s (%s:%s) is not supported", self, type(self).__name__, self.attr)
            return False

        _LOGGER.debug("%s is supported", self)
        self.configurate(**config)
        return True

    @property
    def vehicle_name(self):
        return self.vehicle.vin

    @property
    def full_name(self):
        return "%s %s" % (self.vehicle_name, self.name)

    @property
    def is_mutable(self):
        raise NotImplementedError("Must be set")

    @property
    def str_state(self):
        return self.state

    @property
    def state(self):
        if hasattr(self.vehicle, self.attr):
            return getattr(self.vehicle, self.attr)
        return self.vehicle.get_attr(self.attr)

    @property
    def attributes(self):
        return {}

    @property
    def is_supported(self):
        supported = 'is_' + self.attr + "_supported"
        if hasattr(self.vehicle, supported):
            return getattr(self.vehicle, supported)
        else:
            return False
        # if hasattr(self.vehicle, self.attr):
        #     return True
        # return self.vehicle.has_attr(self.attr)


class Sensor(Instrument):
    def __init__(self, attr, name, icon, unit):
        super().__init__(component="sensor", attr=attr, name=name, icon=icon)
        self.unit = unit

    def configurate(self, scandinavian_miles=False, **config):
        if self.unit and scandinavian_miles:
            if "km" == self.unit:
                self.unit = "mil"
            elif "km/h" == self.unit:
                self.unit = "mil/h"
            elif "l/100 km" == self.unit:
                self.unit = "l/100 mil"
            elif "kWh/100 km" == self.unit:
                self.unit = "kWh/100 mil"

    @property
    def is_mutable(self):
        return False

    @property
    def str_state(self):
        if self.unit:
            return f'{self.state} {self.unit}'
        else:
            return f'{self.state}'

    @property
    def state(self):
        val = super().state
        if val and self.unit in ['mil', 'mil/h']:
            return val / 10
        else:
            return val


class BinarySensor(Instrument):
    def __init__(self, attr, name, device_class, reverse_state=False):
        super().__init__(component="binary_sensor", attr=attr, name=name)
        self.device_class = device_class
        self.reverse_state = reverse_state

    @property
    def is_mutable(self):
        return False

    @property
    def str_state(self):
        if self.device_class in ["door", "window"]:
            return "Open" if self.state else "Closed"
        if self.device_class == "lock":
            return "Unlocked" if self.state else "Locked"
        if self.device_class == "safety":
            return "Warning!" if self.state else "OK"
        if self.device_class == "plug":
            return "Charging" if self.state else "Plug removed"
        if self.state is None:
            _LOGGER.error("Can not encode state %s:%s", self.attr, self.state)
            return "?"
        return "On" if self.state else "Off"

    @property
    def state(self):
        val = super().state

        if isinstance(val, (bool, list)):
            #  for list (e.g. bulb_failures):
            #  empty list (False) means no problem
            if self.reverse_state:
                if bool(val):
                    return False
                else:
                    return True
            else:
                return bool(val)
        elif isinstance(val, str):
            return val != "Normal"
        return val

    @property
    def is_on(self):
        return self.state


class Switch(Instrument):
    def __init__(self, attr, name, icon):
        super().__init__(component="switch", attr=attr, name=name, icon=icon)

    @property
    def is_mutable(self):
        return True

    @property
    def str_state(self):
        return "On" if self.state else "Off"

    def is_on(self):
        return self.state

    def turn_on(self):
        pass

    def turn_off(self):
        pass

    @property
    def assumed_state(self):
        return True


class Climate(Instrument):
    def __init__(self, attr, name, icon):
        super().__init__(component="climate", attr=attr, name=name, icon=icon)

    @property
    def hvac_mode(self):
        pass

    @property
    def target_temperature(self):
        pass

    def set_temperature(self, **kwargs):
        pass

    def set_hvac_mode(self, hvac_mode):
        pass


class ElectricClimatisationClimate(Climate):
    def __init__(self):
        super().__init__(attr="electric_climatisation", name="Electric Climatisation", icon="mdi:radiator")

    @property
    def hvac_mode(self):
        return self.vehicle.electric_climatisation

    @property
    def target_temperature(self):
        return self.vehicle.climatisation_target_temperature

    async def set_temperature(self, temperature):
        await self.vehicle.set_climatisation_target_temperature(temperature)

    async def set_hvac_mode(self, hvac_mode):
        if hvac_mode:
            await self.vehicle.start_electric_climatisation()
        else:
            await self.vehicle.stop_electric_climatisation()


class CombustionClimatisationClimate(Climate):
    def __init__(self):
        super().__init__(attr="combustion_climatisation", name="Combustion Climatisation", icon="mdi:radiator")

    def configurate(self, **config):
        self.spin = config.get('spin', '')

    @property
    def hvac_mode(self):
        return self.vehicle.combustion_climatisation

    @property
    def target_temperature(self):
        return self.vehicle.climatisation_target_temperature

    async def set_temperature(self, temperature):
        await self.vehicle.set_climatisation_target_temperature(temperature)

    async def set_hvac_mode(self, hvac_mode):
        if hvac_mode:
            await self.vehicle.start_combustion_climatisation(self.spin)
        else:
            await self.vehicle.stop_combustion_climatisation(self.spin)


class Position(Instrument):
    def __init__(self):
        super().__init__(component="device_tracker", attr="position", name="Position")

    @property
    def is_mutable(self):
        return False

    @property
    def state(self):
        state = super().state or {}
        return (
            state.get("lat", "?"),
            state.get("lng", "?"),
            state.get("timestamp", None),
            state.get("speed", None),
            state.get("heading", None),
        )

    @property
    def str_state(self):
        state = super().state or {}
        ts = state.get("timestamp", None)
        return (
            state.get("lat", "?"),
            state.get("lng", "?"),
            str(ts.astimezone(tz=None)) if ts else None,
            state.get("speed", None),
            state.get("heading", None),
        )


class DoorLock(Instrument):
    def __init__(self):
        super().__init__(component="lock", attr="door_locked", name="Door locked")

    def configurate(self, **config):
        self.spin = config.get('spin', '')

    @property
    def is_mutable(self):
        return True

    @property
    def str_state(self):
        return "Locked" if self.state else "Unlocked"

    @property
    def state(self):
        return self.vehicle.door_locked

    @property
    def is_locked(self):
        return self.state

    async def lock(self):
        return await self.vehicle.lock_car(self.spin)

    async def unlock(self):
        return await self.vehicle.unlock_car(self.spin)


class TrunkLock(Instrument):
    def __init__(self):
        super().__init__(component="lock", attr="trunk_locked", name="Trunk locked")

    @property
    def is_mutable(self):
        return True

    @property
    def str_state(self):
        return "Locked" if self.state else "Unlocked"

    @property
    def state(self):
        return self.vehicle.trunk_locked

    @property
    def is_locked(self):
        return self.state

    async def lock(self):
        return None

    async def unlock(self):
        return None

# Switches


class RequestUpdate(Switch):
    def __init__(self):
        super().__init__(attr="request_in_progress", name="Request In Progress", icon="mdi:car-connected")

    @property
    def state(self):
        return self.vehicle.request_in_progress

    async def turn_on(self):
        await self.vehicle.trigger_request_update()

    async def turn_off(self):
        pass

    @property
    def assumed_state(self):
        return False


class ElectricClimatisation(Switch):
    def __init__(self):
        super().__init__(attr="electric_climatisation", name="Electric Climatisation", icon="mdi:radiator")

    @property
    def state(self):
        return self.vehicle.electric_climatisation

    async def turn_on(self):
        await self.vehicle.start_electric_climatisation()

    async def turn_off(self):
        await self.vehicle.stop_electric_climatisation()

    @property
    def assumed_state(self):
        return False


class Charging(Switch):
    def __init__(self):
        super().__init__(attr="charging", name="Charging", icon="mdi:battery")

    @property
    def state(self):
        return self.vehicle.charging

    async def turn_on(self):
        await self.vehicle.start_charging()

    async def turn_off(self):
        await self.vehicle.stop_charging()

    @property
    def assumed_state(self):
        return False


class WindowHeater(Switch):
    def __init__(self):
        super().__init__(attr="window_heater", name="Window Heater", icon="mdi:car-defrost-rear")

    @property
    def state(self):
        return self.vehicle.window_heater

    async def turn_on(self):
        await self.vehicle.start_window_heater()

    async def turn_off(self):
        await self.vehicle.stop_window_heater()

    @property
    def assumed_state(self):
        return False


class CombustionEngineHeating(Switch):
    def __init__(self):
        super().__init__(attr="combustion_engine_heating", name="Combustion Engine Heating", icon="mdi:radiator")

    def configurate(self, **config):
        self.spin = config.get('spin', '')
        self.combustionengineheatingduration = config.get('combustionengineheatingduration', 30)

    @property
    def state(self):
        return self.vehicle.combustion_engine_heating

    async def turn_on(self):
        await self.vehicle.start_combustion_engine_heating(spin=self.spin,combustionengineheatingduration=self.combustionengineheatingduration)

    async def turn_off(self):
        await self.vehicle.stop_combustion_engine_heating()

    @property
    def assumed_state(self):
        return False


class CombustionClimatisation(Switch):
    def __init__(self):
        super().__init__(attr="combustion_climatisation", name="Combustion Climate Heating", icon="mdi:radiator")

    def configurate(self, **config):
        self.spin = config.get('spin', '')
        self.combustionengineclimatisationduration = config.get('combustionengineclimatisationduration', 30)

    @property
    def state(self):
        return self.vehicle.combustion_climatisation

    async def turn_on(self):
        await self.vehicle.start_combustion_climatisation(spin=self.spin, combustionengineclimatisationduration=self.combustionengineclimatisationduration)

    async def turn_off(self):
        await self.vehicle.stop_combustion_climatisation()

    @property
    def assumed_state(self):
        return False


def create_instruments():
    return [
        Position(),
        DoorLock(),
        TrunkLock(),
        RequestUpdate(),
        ElectricClimatisation(),
        ElectricClimatisationClimate(),
        CombustionClimatisation(),
        #CombustionClimatisationClimate(),
        Charging(),
        WindowHeater(),
        CombustionEngineHeating(),
        Sensor(
            attr="distance",
            name="Odometer",
            icon="mdi:speedometer",
            unit="km",
        ),
        Sensor(
            attr="battery_level",
            name="Battery level",
            icon="mdi:battery",
            unit="%",
        ),
        Sensor(
            attr="adblue_level",
            name="Adblue level",
            icon="mdi:fuel",
            unit="km",
        ),
        Sensor(
            attr="fuel_level",
            name="Fuel level",
            icon="mdi:fuel",
            unit="%",
        ),
        Sensor(
            attr="service_inspection",
            name="Service inspection",
            icon="mdi:garage",
            unit="",
        ),
        Sensor(
            attr="oil_inspection",
            name="Oil inspection",
            icon="mdi:oil",
            unit="",
        ),
        Sensor(
            attr="last_connected",
            name="Last connected",
            icon="mdi:clock",
            unit="",
        ),
        Sensor(
            attr="charging_time_left",
            name="Charging time left",
            icon="mdi:battery-charging-100",
            unit="min",
        ),
        Sensor(
            attr="electric_range",
            name="Electric range",
            icon="mdi:car-electric",
            unit="km",
        ),
        Sensor(
            attr="combustion_range",
            name="Combustion range",
            icon="mdi:car",
            unit="km",
        ),
        Sensor(
            attr="combined_range",
            name="Combined range",
            icon="mdi:car",
            unit="km",
        ),
        Sensor(
            attr="charge_max_ampere",
            name="Charger max ampere",
            icon="mdi:flash",
            unit="A",
        ),
        Sensor(
            attr="climatisation_target_temperature",
            name="Climatisation target temperature",
            icon="mdi:thermometer",
            unit="°C",
        ),
        Sensor(
            attr="trip_last_average_speed",
            name="Last trip average speed",
            icon="mdi:speedometer",
            unit="km/h",
        ),
        Sensor(
            attr="trip_last_average_electric_consumption",
            name="Last trip average electric consumption",
            icon="mdi:car-battery",
            unit="kWh/100 km",
        ),
        Sensor(
            attr="trip_last_average_fuel_consumption",
            name="Last trip average fuel consumption",
            icon="mdi:fuel",
            unit="l/100 km",
        ),
        Sensor(
            attr="trip_last_duration",
            name="Last trip duration",
            icon="mdi:clock",
            unit="min",
        ),
        Sensor(
            attr="trip_last_length",
            name="Last trip length",
            icon="mdi:map-marker-distance",
            unit="km",
        ),
        Sensor(
            attr="trip_last_recuperation",
            name="Last trip recuperation",
            icon="mdi:battery-plus",
            unit="kWh/100 km",
        ),
        Sensor(
            attr="trip_last_average_auxillary_consumption",
            name="Last trip average auxillary consumption",
            icon="mdi:flash",
            unit="kWh/100 km",
        ),
        Sensor(
            attr="trip_last_total_electric_consumption",
            name="Last trip total electric consumption",
            icon="mdi:car-battery",
            unit="kWh/100 km",
        ),
        Sensor(
            attr="combustion_engine_heatingventilation_status",
            name="Combustion engine heating/ventilation status",
            icon="mdi:radiator",
            unit="",
        ),
        BinarySensor(
            attr="external_power",
            name="External power",
            device_class="plug"
        ),
        BinarySensor(
            attr="parking_light",
            name="Parking light",
            device_class="light"
        ),
        BinarySensor(
            attr="climatisation_without_external_power",
            name="Climatisation without external power",
            device_class="power"
        ),
        BinarySensor(
            attr="door_locked",
            name="Doors locked",
            device_class="lock",
            reverse_state=True
        ),
        BinarySensor(
            attr="door_closed_left_front",
            name="Door closed left front",
            device_class="door",
            reverse_state=True
        ),
        BinarySensor(
            attr="door_closed_right_front",
            name="Door closed right front",
            device_class="door",
            reverse_state=True
        ),
        BinarySensor(
            attr="door_closed_left_back",
            name="Door closed left back",
            device_class="door",
            reverse_state=True
        ),
        BinarySensor(
            attr="door_closed_right_back",
            name="Door closed right back",
            device_class="door",
            reverse_state=True
        ),
        BinarySensor(
            attr="trunk_locked",
            name="Trunk locked",
            device_class="lock",
            reverse_state=True
        ),
        BinarySensor(
            attr="trunk_closed",
            name="Trunk closed",
            device_class="door",
            reverse_state=True
        ),
        BinarySensor(
            attr="sunroof_closed",
            name="Sunroof closed",
            device_class="window",
            reverse_state=True
        ),
        BinarySensor(
            attr="windows_closed",
            name="Windows closed",
            device_class="window",
            reverse_state=True
        ),
        BinarySensor(
            attr="window_closed_left_front",
            name="Window closed left front",
            device_class="window",
            reverse_state=True
        ),
        BinarySensor(
            attr="window_closed_left_back",
            name="Window closed left back",
            device_class="window",
            reverse_state=True
        ),
        BinarySensor(
            attr="window_closed_right_front",
            name="Window closed right front",
            device_class="window",
            reverse_state=True
        ),
        BinarySensor(
            attr="window_closed_right_back",
            name="Window closed right back",
            device_class="window",
            reverse_state=True
        )
        # BinarySensor(
        #     attr="request_in_progress",
        #     name="Request in progress",
        #     device_class="connectivity"
        # ),
    ]


class Dashboard:
    def __init__(self, vehicle, **config):
        _LOGGER.debug("Setting up dashboard with config :%s", config)
        self.instruments = [
            instrument
            for instrument in create_instruments()
            if instrument.setup(vehicle, **config)
        ]
