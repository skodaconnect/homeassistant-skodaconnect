![Version](https://img.shields.io/github/v/release/lendy007/homeassistant-skodaconnect?include_prereleases)
![PyPi](https://img.shields.io/pypi/v/skodaconnect?label=latest%20pypi)
![Downloads](https://img.shields.io/github/downloads/lendy007/homeassistant-skodaconnect/total)

# Skoda Connect - An home assistant plugin to add integration with your car

## This is fork of [robinostlund/homeassistant-volkswagencarnet](https://github.com/robinostlund/homeassistant-volkswagencarnet) where I am trying to modify the code to support Skoda Connect. Most of the credits goes to robinostlund! Stressing again - plugin still under development.

### What is working
- odometer
- fuel level, range, adblue level
- lock status, window status
- last trip info
- position
- auxiliary heating/ventilation control
- electric engine related information 
- electric climatisation and window_heater information

## What is NOT working / under development
- start/stop electric climatisation and window_heater
- for auxiliary heating/ventilation - after enabling you need to wait about 2 minutes to get true status if it is really enabled or not
- trigger status refresh from car - for status changes where car doesn't report it automatically to server (for example car was unlocked on the garden and you just lock it) it still shows old status until car will upload new status or status is refreshed from Skoda Connect App

### Install
Clone or copy the repository and copy the folder 'homeassistant-skodaconnect/custom_component/skodaconnect' into '<config dir>/custom_components'
    
## Configure

Add a volkswagencarnet configuration block to your `<config dir>/configuration.yaml`:
```yaml
skodaconnect:
    username: <username for skoda connect>
    password: <password for skoda connect>
    spin: <S-PIN for skoda connect>
    combustion_engine_heating_duration: <allowed values 10,20,30,40,50,60 (minutes)>
    combustion_engine_climatisation_duration: <allowed values 10,20,30,40,50,60 (minutes)>
    scandinavian_miles: false
    scan_interval:
        minutes: 5
    name:
        wvw1234567812356: 'Kodiaq'
    resources:
        - combustion_engine_heating         
        - combustion_climatisation
        - distance
        - position
        - service_inspection
        - oil_inspection
        - door_locked
        - trunk_locked
        - request_in_progress
        - fuel_level        
        - windows_closed        
        - adblue_level
        - climatisation_target_temperature
        - last_connected
        - combustion_range
        - trip_last_average_speed
        - trip_last_average_fuel_consumption
        - trip_last_duration
        - trip_last_length
        - parking_light
        - door_closed_left_front        
        - door_closed_left_back
        - door_closed_right_front
        - door_closed_right_back
        - trunk_closed
        - window_closed_left_front
        - window_closed_left_back
        - window_closed_right_front
        - window_closed_right_back
        - sunroof_closed
        - service_inspection_km
        - oil_inspection_km
        - outside_temperature
        - electric_climatisation
        - window_heater
        - charging
        - battery_level
        - charging_time_left
        - electric_range
        - combined_range
        - charge_max_ampere
        - climatisation_target_temperature
        - external_power
        - climatisation_without_external_power
        - charging_cable_connected
        - charging_cable_locked
        - trip_last_average_electric_consumption
        - hood_closed
```

* **resources:** if not specified, it will create all supported entities

* **spin:** (optional) required for supporting combustion engine heating start/stop.

* **scan_interval:** (optional) specify in minutes how often to fetch status data from carnet. (default 5 min, minimum 1 min)

* **scandinavian_miles:** (optional) specify true if you want to change from km to mil on sensors

* **name:** (optional) map the vehicle identification number (VIN) to a friendly name of your car. This name is then used for naming all entities. See the configuration example. (by default, the VIN is used). VIN need to be entered lower case

## Automations

In this example we are sending notifications to an ios device

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
        custom_components.skodaconnect: debug
        custom_components.skodaconnect.climate: debug
        custom_components.skodaconnect.lock: debug
        custom_components.skodaconnect.device_tracker: debug
        custom_components.skodaconnect.switch: debug
        custom_components.skodaconnect.binary_sensor: debug
        custom_components.skodaconnect.sensor: debug
 ```

