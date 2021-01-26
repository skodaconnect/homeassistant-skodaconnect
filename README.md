![Version](https://img.shields.io/github/v/release/lendy007/homeassistant-skodaconnect?include_prereleases)
![PyPi](https://img.shields.io/pypi/v/skodaconnect?label=latest%20pypi)
![Downloads](https://img.shields.io/github/downloads/lendy007/homeassistant-skodaconnect/total)

# Skoda Connect - An home assistant plugin to add integration with your car

# v1.0.30

## This is fork of [robinostlund/homeassistant-volkswagencarnet](https://github.com/robinostlund/homeassistant-volkswagencarnet) where I am trying to modify the code to support Skoda Connect.

## Big thanks to @Farfar who is making great contribution to this project!

### What is working
- odometer
- fuel level, range, adblue level
- lock status, window status
- last trip info
- position - gps coordinates, vehicleMoving, parkingTime
- auxiliary heating/ventilation control
- electric engine related information
- electric climatisation and window_heater information
- start/stop auxiliary climatisation for PHEV cars
- start/stop electric climatisation and window_heater
- lock/unlock car
- trigger status refresh from car - for status changes where car doesn't report it automatically to server (for example car was unlocked on the garden and you just lock it) it still shows old status until car will upload new status or status is refreshed from Skoda Connect App
- parking heater heating/ventilation (for non-PHEV cars)

### What is NOT working / under development
- climate entitites are somewhat, or totally, broken. Do not use. WIP to enable heating/ventilation option for parking heater and electric/auxiliary for PHEV cars with aux heater. Fix needed for target temp for parking heater.

### Breaking changes
 - combustion heater/ventilation is now named parking heater so it's not mixed up with aux heater for PHEV
 - Many resources have changed names to avoid confusion in the code

### Install
Clone or copy the repository and copy the folder 'homeassistant-skodaconnect/custom_component/skodaconnect' into '<config dir>/custom_components'

## Configure

Add a skodaconnect configuration block to your `<config dir>/configuration.yaml`:
```yaml
skodaconnect:
    username: <username for skoda connect>
    password: <password for skoda connect>
    spin: <S-PIN for skoda connect>
    scandinavian_miles: false
    scan_interval:
        minutes: 1
    name:
        wvw1234567812356: 'Kodiaq'
```
* **username:** (required) the username to your Skoda Connect account

* **password:** (required) the password to your Skoda Connect account

* **spin:** (optional) required for supporting combustion engine heating start/stop.

* **scandinavian_miles:** (optional) set to true if you want to change from km to mi on sensors. Conversion between fahrenheit and celcius is taken care of by Home Assistant.

* **scan_interval:** (optional) specify in minutes how often to fetch status data from Skoda Connect. (default 5 min, minimum 1 min)

* **name:** (optional) map the vehicle identification number (VIN) to a friendly name of your car. This name is then used for naming all entities. See the configuration example. (by default, the VIN is used). VIN need to be entered lower case


Additional optional configuration options, only add if needed:
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

* **response_debug:** (optional) set to true to log raw HTTP data from Skoda Connect. This will flood the log, only enable if needed.

* **resources:** (optional) use to disable entities, if specified only the listed sensors will be created. If not specified all supported entities will be created.

## Automations

In this example we are sending notifications to an ios device. The Android companion app does not currently support dynamic content in notifications (maps etc.)

Save these automations in your automations file `<config dir>/automations.yaml`

### Get notification when your car is on a new place and show a map with start position and end position
```yaml
- id: notify_skoda_position_change
  description: Notify when position has been changed
  alias: Skoda position changed notification
  trigger:
    - platform: state
      entity_id: device_tracker.kodiaq
  action:
    - service: notify.ios_my_ios_device
      data_template:
        title: "Kodiaq Position Changed"
        message: |
          🚗 Skoda Car is now on a new place.
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

### Announce when your car is unlocked but no one is home
```yaml
- id: 'notify_skoda_car_is_unlocked'
  alias: Skoda is at home and unlocked
  trigger:
    - entity_id: binary_sensor.vw_carid_external_power
      platform: state
      to: 'on'
      for: 00:10:00
  condition:
    - condition: state
      entity_id: lock.kodiaq_door_locked
      state: unlocked
    - condition: state
      entity_id: device_tracker.kodiaq
      state: home
    - condition: time
      after: '07:00:00'
      before: '21:00:00'
  action:
    # Notification via push message to smartphone
    - service: notify.device
      data:
        message: "The car is unlocked!"
        target:
          - device/my_device
    # Notification via smart speaker (kitchen)
    - service: media_player.volume_set
      data:
        entity_id: media_player.kitchen
        volume_level: '0.6'
    - service: tts.google_translate_say
      data:
        entity_id: media_player.kitchen
        message: "My Lord, the car is unlocked. Please attend this this issue at your earliest inconvenience!"
```

## Enable debug logging
```yaml
logger:
    default: info
    logs:
        skodaconnect.connection: debug
        skodaconnect.vehicle: debug
        custom_components.skodaconnect: debug
        custom_components.skodaconnect.climate: debug
        custom_components.skodaconnect.lock: debug
        custom_components.skodaconnect.device_tracker: debug
        custom_components.skodaconnect.switch: debug
        custom_components.skodaconnect.binary_sensor: debug
        custom_components.skodaconnect.sensor: debug
 ```
