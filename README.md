![Version](https://img.shields.io/github/v/release/skodaconnect/homeassistant-skodaconnect?include_prereleases)
![PyPi](https://img.shields.io/pypi/v/skodaconnect?label=latest%20library)
![Downloads](https://img.shields.io/github/downloads/skodaconnect/homeassistant-skodaconnect/total)

# **DEPRECATION NOTICE**

This integration only supports the 'old' Skoda API (associated with the old mobile app called _Skoda Essentials_) and will stop working when Skoda shuts down the old API. This is announced to be on December 2nd 2024 but that date has shifted already in the past.

If you are unable to use the Skoda Essentials app then this integration will **not** work for you. This is reported to be the case for newer Skoda accounts.

Development on this integration has essentially completely halted and it will not be updated to support the new app/API.

A new integration is being developed to work with the 'new' Skoda API (associated with the new mobile app called _MySkoda_): https://github.com/skodaconnect/homeassistant-myskoda

The new integration is actively developed and only a few models are (partially) supported at this time. Still we highly encourage everyone to try out the new integration and provide feedback through Github issues or [Discord](https://discord.gg/826X9jEtCh).

# Skoda Connect - A Home Assistant custom component for Skoda Connect/MyŠKODA

If you are new to Home Assistant, please read the [Home Assistant documentation](https://www.home-assistant.io/docs/) first.

This is fork of [robinostlund/homeassistant-volkswagencarnet](https://github.com/robinostlund/homeassistant-volkswagencarnet) modified to support Skoda Connect/MySkoda through native app API (API calls directly to vwg-connect services)

This integration for Home Assistant will fetch data from Skoda Connect servers related to your Skoda Connect enabled car.
Skoda Connect never fetch data directly from car, the car sends updated data to VAG servers on specific events such as lock/unlock, charging events, climatisation events and when vehicle is parked. The integration will then fetch this data from the servers.
When vehicle actions fails or return with no response, a force refresh might help. This will trigger a "wake up" call from VAG servers to the car.
The scan_interval is how often the integration should fetch data from the servers, if there's no new data from the car then entities won't be updated.

This project contains the Home Assistant custom component code. It depends on https://github.com/skodaconnect/skodaconnect which provides the Python library interacting with the Skoda API.

### Supported setups

This integration will only work for your car if you have Skoda Connect/MyŠKODA functionality. Cars using other third party, semi-official, mobile apps such as the "MinSkoda" from ConnectedCars in Denmark won't work.
The library used for API communication is reverse engineered from the MySkoda Android app.
Initial support has been added for SmartLink and newer style API cars, such as the Enyaq iV.

The car privacy settings must be set to "Share my position" for full functionality of this integration. Without this setting, if set to "Use my position", the sensors for position (device tracker), requests remaining and parking time might not work reliably or at all. Set to even stricter privacy setting will limit functionality even further.

### If you encounter problems

If you encounter a problem where the integration can't be setup or if you receive an error that there's unaccepted terms or EULA, it might be because of your mobile app platform.
The underlying library is built by reverse engineering the Android App behavior and thus it use the same client configurations as an Android device. If you only use the app on iPhone/iOS devices it might cause issues with this integration.

Possible workarounds:
- Log in using the **old** "MySkoda Essentials" iOS/Android app (see #198). It should present an EULA or new terms and conditions to be accepted.
- Log in through a web browser (https://www.skoda-connect.com/)

If this does not work for you and the particular problem you are facing, please open an issue and provide as detailed problem description as possible and relevant debug logs.

### What is working, all cars

- Automatic discovery of enabled functions (API endpoints).
- Charging plug connected
- Charging plug locked
- Charger connected (external power)
- Battery level
- Electric range
- Model image, URL in 1080 resolution
- Start/stop charging
- Start/stop Electric climatisation, window_heater and information
- Charger maximum current
  (1-16 tested OK for Superb iV, Enyaq limited to "Maximum"/"Reduced")
- Set departure timers (switch on/off and service call to set parameters)
- Odometer and service info
- Lock, windows, trunk, hood, sunroof and door status
- Position - gps coordinates, if vehicle is moving, time parked
- Device tracker - entity is set to 'not_home' when car is moving

### Additional information/functions VW-Group API ("All" Skodas except Enyaq iV so far)

- Fuel level, range, adblue level
- Last trip info
- start/stop auxiliary climatisation for PHEV cars
- Lock and unlock car
- Parking heater heating/ventilation (for non-electric cars)
- Requests information - latest status, requests remaining until throttled
- Trigger data refresh - this will trigger a wake up call so the car sends new data

### Additional information/functions Skoda native API (Enyaq iV so far)

- Charging power (Watts)
- Charging rate (km per hour)
- Charging time left (minutes)
- Seat heating (???)

### Under development and BETA functionality (may be buggy)

- Config flow multiple vehicles from same account
- SmartLink:
  - Fuel level
  - Odometer
  - Service inspection distance
  - Service inspection time
  - Oil service distance
  - Oil service time
- Skoda Enyaq iV:
  - Start/stop charging (switch)
  - Set charger max current (service call)
  - Set charge limit (service call)

### What is NOT working

- Switches doesn't immediately update "request results" and "request_in_progress". Long running requests will not show up until completed which might take up to 3-5 minutes.
- Config flow convert from yaml config

### Breaking changes

- Combustion heater/ventilation is now named parking heater so it's not mixed up with aux heater for PHEV
- Many resources have changed names to avoid confusion in the code, some have changed from sensor to switch and vice versa. Sensors with trailing "_km" in the name has been renamed to "_distance" for better compatibility between imperial and non-imperial units.
- Major code changes has been made for requests handling.
  - request_in_progress is now a binary sensor instead of a switch
  - force_data_refresh is a new switch with the same functionality as "request_in_progress" previously, it will force refresh data from car

## Installation

### Install with HACS (recomended)

If you have HACS (Home Assistant Community Store) installed, just search for Skoda Connect and install it direct from HACS.
HACS will keep track of updates and you can easly upgrade to the latest version when a new release is available.

If you don't have it installed, check it out here: [HACS](https://community.home-assistant.io/t/custom-component-hacs)

### Manual installation

Clone or copy the repository and copy the folder 'homeassistant-skodaconnect/custom_component/skodaconnect' into '[config dir]/custom_components'.
  Install required python library with (adjust to suit your environment):

```sh
pip install skodaconnect
```

## Enable debug logging

For comprehensive debug logging you can add this to your `<config dir>/configuration.yaml`:

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

- **skodaconnect.connection:** Set the debug level for the Connection class of the Skoda Connect library. This handles the GET/SET requests towards the API

- **skodaconnect.vehicle:** Set the debug level for the Vehicle class of the Skoda Connect library. One object created for every vehicle in account and stores all data.

- **skodaconnect.dashboard:** Set the debug level for the Dashboard class of the Skoda Connect library. A wrapper class between hass component and library.

- **custom_components.skodaconnect:** Set debug level for the custom component. The communication between hass and library.

- **custom_components.skodaconnect.XYZ** Sets debug level for individual entity types in the custom component.

## Configuration

Configuration in configuration.yaml is now deprecated and can interfere with setup of the integration.
To configure the integration, go to Configuration in the side panel of Home Assistant and then select Integrations.
Click on the "ADD INTEGRATION" button in the bottom right corner and search/select skodaconnect.
Follow the steps and enter the required information. Because of how the data is stored and handled in Home Assistant, there will be one integration per vehicle.
Setup multiple vehicles by adding the integration multiple times.

### Configuration options

The integration options can be changed after setup by clicking on the "CONFIGURE" text on the integration.
The options available are:

- **Poll frequency** The interval (in seconds) that the servers are polled for updated data. Several users have reported being rate limited (HTTP 429) when using 60s or lower. It is recommended to start with a value of 120s or 180s. See [#215](https://github.com/skodaconnect/homeassistant-skodaconnect/issues/215).

- **S-PIN** The S-PIN for the vehicle. This is optional and is only needed for certain vehicle requests/actions (auxiliary heater, lock etc).

- **Mutable** Select to allow interactions with vehicle, start climatisation etc.

- **Full API debug logging** Enable full debug logging. This will print the full respones from API to homeassistant.log. Only enable for troubleshooting since it will generate a lot of logs.

- **Resources to monitor** Select which resources you wish to monitor for the vehicle.

- **Distance/unit conversions** Select if you want to convert distance/units.

## Automations

In this example we are sending notifications to an ios device. The Android companion app does not currently support dynamic content in notifications (maps etc.)

Save these automations in your automations file `<config dir>/automations.yaml`

### Use input_select to change pre-heater duration

First create a input_number, via editor in configuration.yaml or other included config file, or via GUI Helpers editor.
It is important to set minimum value to 10, maximum to 60 and step to 10. Otherwise the service call might not work.

```yaml
# configuration.yaml
input_number:
  pheater_duration:
    name: "Pre-heater duration"
    initial: 20
    min: 10
    max: 60
    step: 10
    unit_of_measurement: min
```

Create the automation, in yaml or via GUI editor. You can find the device id by going to Settings->Devices & Services and then clicking on the device for the Skodaconnect vehicle. The device ID will show in the web browser address bar after "/config/devices/device/". The ID can also be found by using the GUI services editor under developer tools. Choose one of the skodaconnect services and choose your vehicle. Change to YAML mode and copy the device ID.

```yaml
# automations.yaml
- alias: Pre-heater duration
  description: ""
  trigger:
    - platform: state
      entity_id: input_number.pheater_duration
  condition: []
  action:
    - service: skodaconnect.set_pheater_duration
      data_template:
        device_id: <Your Device ID for vehicle>
        duration: "{{ (states('input_number.pheater_duration') | float ) | round(0) }}"
  mode: single
```

### Charge rate guesstimate

Thanks to @haraldpaulsen
An estimated charge rate template sensor based on battery capacity and reported time left.
Replace <name> with the name of your vehicle and <capacity> with battery capacity in Wh.

```yaml
template:
  - sensor:
    - name: "Charge speed guesstimate"
      state: >
        {% if is_state('switch.skoda_<name>_charging', 'on') %}
          {% set battery_capacity = <battery-size-in-kwh> | int %}
          {% set charge = { "remaining": states('sensor.skoda_<name>_minimum_charge_level') | int - states('sensor.skoda_<name>_battery_level') | int } %}
          {% set timeleft = states('sensor.skoda_<name>_charging_time_left') | int %}
          {% set chargeleft = battery_capacity * charge.remaining / 100  %}
          {% set chargespeed = chargeleft / (timeleft / 60) %}
          {{ chargespeed | round (1) }}
        {% else %}
          0
        {% endif %}
      unit_of_measurement: "kW"
      state_class: measurement
```

### Get notification when your car is on a new place and show a map with start position and end position

Note: only available for iOS devices since Android companion app does not support this yet.
This might be broken since 1.0.30 when device_tracker changed behaviour.

```yaml
- id: notify_skoda_position_change
  description: Notify when position has been changed
  alias: Skoda position changed notification
  trigger:
    - platform: state
      entity_id: device_tracker.kodiaq
  condition: template
    condition: template
    value_template: "{{ trigger.to_state.state != trigger.from_state.state }}"
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
