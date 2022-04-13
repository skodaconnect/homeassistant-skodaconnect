![Version](https://img.shields.io/github/v/release/lendy007/homeassistant-skodaconnect?include_prereleases)
![PyPi](https://img.shields.io/pypi/v/skodaconnect?label=latest%20library)
![Downloads](https://img.shields.io/github/downloads/lendy007/homeassistant-skodaconnect/total)

# Skoda Connect - A Home Assistant custom component for Skoda Connect/MyŠKODA

## This is fork of [robinostlund/homeassistant-volkswagencarnet](https://github.com/robinostlund/homeassistant-volkswagencarnet) modified to support Skoda Connect/MySkoda through native app API (API calls directly to vwg-connect services)

This integration for Home Assistant will fetch data from Skoda Connect servers related to your Skoda Connect enabled car.
Skoda Connect never fetch data directly from car, the car sends updated data to VAG servers on specific events such as lock/unlock, charging events, climatisation events and when vehicle is parked. The integration will then fetch this data from the servers.
When vehicle actions fails or return with no response, a force refresh might help. This will trigger a "wake up" call from VAG servers to the car.
The scan_interval is how often the integration should fetch data from the servers, if there's no new data from the car then entities won't be updated.

### Supported setups

This integration will only work for your car if you have Skoda Connect/MyŠKODA functionality. Cars using other third party, semi-official, mobile apps such as the "MinSkoda" from ConnectedCars in Denmark won't work.
Initial support has been added for SmartLink and newer style API cars, such as the Enyaq iV.

The car privacy settings must be set to "Share my position" for full functionality of this integration. Without this setting, if set to "Use my position", the sensors for position (device tracker), requests remaining and parking time might not work reliably or at all. Set to even stricter privacy setting will limit functionality even further.

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

### Additional information/functions VW-Group API ("All" Skodas except Enyaq iV so far)

- Odometer and service info
- Fuel level, range, adblue level
- Lock, windows, trunk, hood, sunroof and door status
- Last trip info
- Position - gps coordinates, if vehicle is moving, time parked
- start/stop auxiliary climatisation for PHEV cars
- Lock and unlock car
- Parking heater heating/ventilation (for non-electric cars)
- Requests information - latest status, requests remaining until throttled
- Device tracker - entity is set to 'not_home' when car is moving
- Trigger data refresh - this will trigger a wake up call so the car sends new data

### Additional information/functions Skoda native API (Enyaq iV so far)

- Charging power (Watts)
- Charging rate (km per hour)
- Charging time left (hours:minute)
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
- Many resources have changed names to avoid confusion in the code, some have changed from sensor to switch and vice versa. Sensors with trailing "_km" in the name has been renamed to "_distance" for better compability between imperial and non-imperial units.
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

## Configuration

Configuration in configuration.yaml is now deprecated and can interfere with setup of the integration.
To configure the integration, go to Configuration in the side panel of Home Assistant and then select Integrations.
Click on the "ADD INTEGRATION" button in the bottom right corner and search/select skodaconnect.
Follow the steps and enter the required information. Because of how the data is stored and handled in Home Assistant, there will be one integration per vehicle.
Setup multiple vehicles by adding the integration multiple times.

### Configuration options

The integration options can be changed after setup by clicking on the "CONFIGURE" text on the integration.
The options available are:

- **Poll frequency** The interval (in minutes) that the servers are polled for updated data.

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

Create the automation, in yaml or via GUI editor.

```yaml
# automations.yaml
- alias: Set pre-heater duration
  trigger:
  - platform: state
    entity_id: input_number.pheater_duration
  action:
  - service: skodaconnect.set_pheater_duration
    data_template:
     vin: <VIN-number of car>
     duration: >
        {{ trigger.to_state.state }}
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
        {% if is_state('switch.<name>_charging', 'on') %}
        {% set maxcharge = <capacity> %}
        {% set percentleft = 100 - states('sensor.<name>_battery_level') | int %}
        {% set hoursleft = states('sensor.<name>_charging_time_left').split(':')[0] | int  %}
        {% set minutesleft = states('sensor.<name>_charging_time_left').split(':')[1] | int %}
        {% set totalminutesleft = hoursleft*60 + minutesleft %}
        {% set chargeleft = maxcharge * percentleft / 100  %}
        {% set chargespeed = chargeleft / (totalminutesleft / 60)  %}
        {{ (chargespeed / 1000) | round(1) }}
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

## Further help or contributions

For questions, further help or contributions you can join the Discord server at <https://discord.gg/826X9jEtCh>
