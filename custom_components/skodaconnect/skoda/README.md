# Volkswagen Carnet

[![buy me a coffee](https://www.buymeacoffee.com/assets/img/custom_images/yellow_img.png)](https://www.buymeacoffee.com/robinostlund)

![Release](https://img.shields.io/github/workflow/status/robinostlund/volkswagencarnet/Release)
![PyPi](https://img.shields.io/pypi/v/volkswagencarnet)
![Version](https://img.shields.io/github/v/release/robinostlund/volkswagencarnet)

![Downloads a day](https://img.shields.io/pypi/dd/volkswagencarnet)
![Downloads a week](https://img.shields.io/pypi/dw/volkswagencarnet)
![Downloads a month](https://img.shields.io/pypi/dm/volkswagencarnet)

## Information

Retrieve statistics about your Volkswagen from the Volkswagen Carnet online service

No licence, public domain, no guarantees, feel free to use for anything. Please contribute improvements/bugfixes etc.

## Thanks to

- [Wez3](https://github.com/wez3)
- [Reneboer](https://github.com/reneboer)
- [Tubalainen](https://github.com/tubalainen)

For supporting and helping in this project.

## Other related repositories

- [HomeAssistant Component](https://github.com/robinostlund/homeassistant-volkswagencarnet) a custom component for Home Assistant
- [VolkswagenCarnetClient](https://github.com/robinostlund/volkswagencarnet-client) a cli version of this library

## Installation

```sh
[venv-python3] user@localhost:~
$ pip install volkswagencarnet
```

### Example

```python
#!/usr/bin/env python3
import volkswagencarnet
import pprint
import asyncio
import logging

from aiohttp import ClientSession

logging.basicConfig(level=logging.DEBUG)

VW_USERNAME='test@example.com'
VW_PASSWORD='mysecretpassword'


COMPONENTS = {
    'sensor': 'sensor',
    'binary_sensor': 'binary_sensor',
    'lock': 'lock',
    'device_tracker': 'device_tracker',
    'switch': 'switch',
    'climate': 'climate'
}

RESOURCES = [
    'position',
    'distance',
    'electric_climatisation',
    'combustion_climatisation',
    'window_heater',
    'combustion_engine_heating',
    'charging',
    'adblue_level',
    'battery_level',
    'fuel_level',
    'service_inspection',
    'oil_inspection',
    'last_connected',
    'charging_time_left',
    'electric_range',
    'combustion_range',
    'combined_range',
    'charge_max_ampere',
    'climatisation_target_temperature',
    'external_power',
    'parking_light',
    'climatisation_without_external_power',
    'door_locked',
    'trunk_locked',
    'request_in_progress',
    'windows_closed',
    'sunroof_closed',
    'trip_last_average_speed',
    'trip_last_average_electric_consumption',
    'trip_last_average_fuel_consumption',
    'trip_last_duration',
    'trip_last_length'
]

def is_enabled(attr):
    """Return true if the user has enabled the resource."""
    return attr in RESOURCES

async def main():
    """Main method."""
    async with ClientSession(headers={'Connection': 'keep-alive'}) as session:
        connection = volkswagencarnet.Connection(session, VW_USERNAME, VW_PASSWORD)
        if await connection._login():
            if await connection.update():
                # Print overall state
                pprint.pprint(connection._state)

                # Print vehicles
                for vehicle in connection.vehicles:
                    pprint.pprint(vehicle)

                # get all instruments
                instruments = set()
                for vehicle in connection.vehicles:
                    dashboard = vehicle.dashboard(mutable=True)

                    for instrument in (
                            instrument
                            for instrument in dashboard.instruments
                            if instrument.component in COMPONENTS
                            and is_enabled(instrument.slug_attr)):

                        instruments.add(instrument)

                # Output all supported instruments
                for instrument in instruments:
                    print(f'name: {instrument.full_name}')
                    print(f'str_state: {instrument.str_state}')
                    print(f'state: {instrument.state}')
                    print(f'supported: {instrument.is_supported}')
                    print(f'attr: {instrument.attr}')
                    print(f'attributes: {instrument.attributes}')

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    # loop.run(main())
    loop.run_until_complete(main())
```
