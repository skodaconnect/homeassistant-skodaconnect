![Version](https://img.shields.io/github/v/release/farfar/homeassistant-seatconnect?include_prereleases)
![PyPi](https://img.shields.io/pypi/v/seatconnect?label=latest%20pypi)
![Downloads](https://img.shields.io/github/downloads/farfar/homeassistant-seatconnect/total)

# Seat Connect - A Home Assistant custom component for Seat Connect

# v1.0.30
**WARNING!**
***Version 1.0.30 and later has undergone major code changes since release 1.0.27.
If you are updating, be sure to backup all your data***
Major changes are entity names and climate entities are removed.
Supported features are automatically discovered through API calls, this hasn't been tested on all cars and might prove unreliable for some.

## This is fork of [robinostlund/homeassistant-volkswagencarnet](https://github.com/robinostlund/homeassistant-volkswagencarnet) modified to support Seat Connect through native app API (API calls directly to vwg-connect services)
This integration for Home Assistant will fetch data from Seat Connect servers related to your Seat Connect enabled car.
Seat Connect never fetch data directly from car, the car sends updated data to VAG servers on specific events such as lock/unlock, charging events, climatisation events and when vehicle is parked. The integration will then fetch this data from the servers.
When vehicle actions fails or return with no response, a force refresh might help. This will trigger a "wake up" call from VAG servers to the car.
The scan_interval is how often the integration should fetch data from the servers, if there's no new data from the car then entities won't be updated-

### What is working
- odometer and service info
- fuel level, range, adblue level
- lock, windows, trunk, hood, sunroof and door status
- last trip info
- position - gps coordinates, if vehicle is moving, time parked
- electric engine related information - charging, battery level, plug connected and more
- electric climatisation and window_heater information
- start/stop auxiliary climatisation for PHEV cars
- start/stop electric climatisation and window_heater
- lock/unlock car
- parking heater heating/ventilation (for non-PHEV cars)
- requests information - latest status, requests remaining until throttled
- device tracker - entity is set to 'not_home' when car is moving
- trigger data refresh - this will trigger a wake up call so the car sends new data

### What is NOT working / under development
- climate entitites has been removed since they didn't map very well for requests to Seat Connect API.
- switches doesn't immediately update "request reulsts" and "request_in_progress". Long running requests will not show up until next scan interval.

### Breaking changes
- Enabled API endpoints (functions) are discovered through fetching "operationlist". This has not been tested for all cars and might prove unreliable.
- Combustion heater/ventilation is now named parking heater so it's not mixed up with aux heater for PHEV
- Many resources have changed names to avoid confusion in the code, some have changed from sensor to switch and vice versa
- Major code changes has been made for requests handling.
  - request_in_progress is now a binary sensor instead of a switch
  - force_data_refresh is a new switch with the same functionality as "request_in_progress" previously, it will force refresh data from car

## Installation

### Install with HACS (recomended)
If you have HACS (Home Assistant Community Store) installed, just search for Seat Connect and install it direct from HACS.
HACS will keep track of updates and you can easly upgrade to the latest version when a new release is available.

If you don't have it installed, check it out here: [HACS](https://community.home-assistant.io/t/custom-component-hacs)

### Manual installation
Clone or copy the repository and copy the folder 'homeassistant-seatconnect/custom_component/seatconnect' into '<config dir>/custom_components'

## Configure

Add a seatconnect configuration block to your `<config dir>/configuration.yaml`:
```yaml
seatconnect:
    username: <username for seat connect>
    password: <password for seat connect>
    spin: <S-PIN for seat connect>
    scandinavian_miles: false
    scan_interval:
        minutes: 1
    name:
        wvw1234567812356: 'Kodiaq'
```
* **username:** (required) the username to your Seat Connect account

* **password:** (required) the password to your Seat Connect account

* **spin:** (optional) required for supporting combustion engine heating start/stop.

* **scandinavian_miles:** (optional) set to true if you want to change from km to mi on sensors. Conversion between fahrenheit and celcius is taken care of by Home Assistant. (Default: false)

* **scan_interval:** (optional) specify in minutes how often to fetch status data from Seat Connect. (Default: 5 min, minimum 1 min)

* **name:** (optional) map the vehicle identification number (VIN) to a friendly name of your car. This name is then used for naming all entities. See the configuration example. (by default, the VIN is used). VIN need to be entered lower case


Additional optional configuration options, only add if needed!
The resources option will limit what entities gets added to home assistant, only the specified resources will be added if they are supported.
If not specified then the integration will add all supported entities:
```yaml
    response_debug: False
    resources:
       # Binary sensors
        - charging_cable_connected
        - charging_cable_locked
        - door_closed_left_front
        - door_closed_left_back
        - door_closed_right_front
        - door_closed_right_back
        - doors_locked
        - energy_flow
        - external_power
        - hood_closed
        - parking_light
        - request_in_progress
        - sunroof_closed
        - trunk_closed
        - trunk_locked
        - vehicle_moving
        - window_closed_left_front
        - window_closed_left_back
        - window_closed_right_front
        - window_closed_right_back
        - windows_closed
      # Device tracker
        - position
      # Locks
        - door_locked
        - trunk_locked
      # Sensors
        - adblue_level
        - battery_level
        - charger_max_ampere
        - charging_time_left
        - climatisation_target_temperature
        - combined_range
        - combustion_range
        - electric_range
        - fuel_level
        - last_connected
        - last_trip_average_electric_consumption
        - last_trip_average_fuel_consumption
        - last_trip_average_speed
        - last_trip_duration
        - last_trip_length
        - odometer
        - oil_inspection_days
        - oil_inspection_distance
        - outside_temperature
        - parking_time
        - pheater_status
        - pheater_duration
        - request_results
        - requests_remaining
        - service_inspection_days
        - service_inspection_distance
      # Switches
        - auxiliary_climatisation
        - charging
        - climatisation_from_battery
        - electric_climatisation
        - force_data_refresh
        - parking_heater_heating
        - parking_heater_ventilation
        - window_heater
```

* **response_debug:** (optional) set to true to log raw HTTP data from Seat Connect. This will flood the log, only enable if needed. (Default: false)

* **resources:** (optional) use to enable/disable entities. If specified, only the listed entities will be created. If not specified all supported entities will be created.

## Automations

In this example we are sending notifications to an ios device. The Android companion app does not currently support dynamic content in notifications (maps etc.)

Save these automations in your automations file `<config dir>/automations.yaml`

### Get notification when your car is on a new place and show a map with start position and end position
```yaml
- id: notify_seat_position_change
  description: Notify when position has been changed
  alias: Seat position changed notification
  trigger:
    - platform: state
      entity_id: device_tracker.arona
  action:
    - service: notify.ios_my_ios_device
      data_template:
        title: "Arona Position Changed"
        message: |
          🚗 Seat Car is now on a new place.
        data:
          url: /lovelace/car
          apns_headers:
            'apns-collapse-id': 'car_position_state_{{ trigger.entity_id.split(".")[1] }}'
          push:
            category: map
            thread-id: "HA Car Status"
          action_data:
            latitude: "{{trigger.from_state.attributes.latitude}}"
            longitude: "{{trigger.from_state.attributes.longitude}}"
            second_latitude: "{{trigger.to_state.attributes.latitude}}"
            second_longitude: "{{trigger.to_state.attributes.longitude}}"
            shows_traffic: true
```

## Enable debug logging
For comprehensive debug logging you can add this to your `<config dir>/configuration.yaml`:
```yaml
logger:
    default: info
    logs:
        seatconnect.connection: debug
        seatconnect.vehicle: debug
        custom_components.seatconnect: debug
        custom_components.seatconnect.climate: debug
        custom_components.seatconnect.lock: debug
        custom_components.seatconnect.device_tracker: debug
        custom_components.seatconnect.switch: debug
        custom_components.seatconnect.binary_sensor: debug
        custom_components.seatconnect.sensor: debug
 ```
* **seatconnect.connection:** Set the debug level for the Connection class of the Seat Connect library. This handles the GET/SET requests towards the API

* **seatconnect.vehicle:** Set the debug level for the Vehicle class of the Seat Connect library. One object created for every vehicle in account and stores all data.

* **seatconnect.dashboard:** Set the debug level for the Dashboard class of the Seat Connect library. A wrapper class between hass component and library.

* **custom_components.seatconnect:** Set debug level for the custom component. The communication between hass and library.

* **custom_components.seatconnect.XYZ** Sets debug level for individual entity types in the custom component.
