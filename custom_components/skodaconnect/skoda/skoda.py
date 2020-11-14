#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Communicate with Skoda Connect."""
import re
import time
import logging
import asyncio
import hashlib

from sys import version_info, argv
from datetime import timedelta, datetime
from urllib.parse import urlsplit, urljoin, parse_qs, urlparse
from json import dumps as to_json
from collections import OrderedDict
import aiohttp
from bs4 import BeautifulSoup
from utilities import find_path, is_valid_path, read_config, json_loads
from base64 import b64decode, b64encode

from aiohttp import ClientSession, ClientTimeout
from aiohttp.hdrs import METH_GET, METH_POST

version_info >= (3, 0) or exit('Python 3 required')

_LOGGER = logging.getLogger(__name__)

TIMEOUT = timedelta(seconds=30)

HEADERS_SESSION = {
    'Connection': 'keep-alive',    
    'Content-Type': 'application/json',
    "X-Client-Id": '7f045eee-7003-4379-9968-9355ed2adb06%40apps_vw-dilab_com',
    "X-App-Version": '3.2.6',
    "X-App-Name": 'cz.skodaauto.connect',
    "Accept-charset": "UTF-8",
    #"Accept": "application/json,*/*",
    "Accept": "application/json",
    'User-Agent': 'okhttp/3.7.0'
}

HEADERS_AUTH = {
    'Connection': 'keep-alive',
    'Accept': 'application/json,text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,\
        image/apng,*/*;q=0.8,application/signed-exchange;v=b3',
    'Content-Type': 'application/x-www-form-urlencoded',
    'User-Agent': 'OneConnect/200605002 CFNetwork/1128 Darwin/19.6.0'
}

BASE_SESSION = 'https://msg.volkswagen.de'
BASE_AUTH = 'https://identity.vwgroup.io'
CLIENT_ID = '7f045eee-7003-4379-9968-9355ed2adb06%40apps_vw-dilab_com'

class Connection:
    """ Connection to Skoda connect """

    def __init__(self, session, username, password, guest_lang='en'):
        """ Initialize """
        self._session = session
        self._session_headers = HEADERS_SESSION.copy()
        self._session_base = BASE_SESSION
        self._session_auth_headers = HEADERS_AUTH.copy()
        self._session_auth_base = BASE_AUTH
        self._session_guest_language_id = guest_lang

        self._session_auth_ref_url = BASE_SESSION
        self._session_logged_in = False
        self._session_first_update = False
        self._session_auth_username = username
        self._session_auth_password = password

        self._vin = ""

        _LOGGER.debug('Using service <%s>', self._session_base)
        
        self._jarCookie = ""
        self._state = {}

    def _clear_cookies(self):
        self._session._cookie_jar._cookies.clear()

    async def _login(self):
        """ Reset session in case we would like to login again """
        self._session_headers = HEADERS_SESSION.copy()
        self._session_auth_headers = HEADERS_AUTH.copy()

        def extract_csrf(req):
            return re.compile('<meta name="_csrf" content="([^"]*)"/>').search(req).group(1)

        def extract_guest_language_id(req):
            return req.split('_')[1].lower()

        def getNonce():
            ts = "%d" % (time.time())
            sha256 = hashlib.sha256()
            sha256.update(ts.encode())
            return (b64encode(sha256.digest()).decode("utf-8")[:-1])

        try:
            # remove cookies from session as we are doing a new login
            self._clear_cookies()

            # Request landing page and get auth URL:
            req = await self._session.get(
                url="https://identity.vwgroup.io/.well-known/openid-configuration"                
            )
            if req.status != 200:
                return ""
            response_data =  await req.json()
            authorizationEndpoint = response_data["authorization_endpoint"]
            authissuer = response_data["issuer"]

            # Get authorization 
            # https://identity.vwgroup.io/oidc/v1/authorize?nonce=yVOPHxDmksgkMo1HDUp6IIeGs9HvWSSWbkhPcxKTGNU&response_type=code id_token token&scope=openid mbb&ui_locales=de&redirect_uri=skodaconnect://oidc.login/&client_id=7f045eee-7003-4379-9968-9355ed2adb06%40apps_vw-dilab_com             
            req = await self._session.get(
                url=authorizationEndpoint+'?nonce='+getNonce()+'&response_type=code id_token token&scope=openid mbb&ui_locales=de&redirect_uri=skodaconnect://oidc.login/&client_id='+CLIENT_ID,
                headers=self._session_auth_headers                
            )
            if req.status != 200:
                return ""
            response_data = await req.text()
            responseSoup = BeautifulSoup(response_data, 'html.parser')
            mailform = dict([(t["name"],t["value"]) for t in responseSoup.find('form', id='emailPasswordForm').find_all("input", type="hidden")])
            mailform["email"] = self._session_auth_username
            pe_url = authissuer+responseSoup.find('form', id='emailPasswordForm').get('action')

            # POST email
            # https://identity.vwgroup.io/signin-service/v1/xxx@apps_vw-dilab_com/login/identifier
            self._session_auth_headers['Referer'] = authorizationEndpoint
            self._session_auth_headers['Origin'] = authissuer
            req = await self._session.post(
                url=pe_url,
                headers=self._session_auth_headers,
                data = mailform               
            )
            if req.status != 200:
                return ""
            response_data = await req.text()
            responseSoup = BeautifulSoup(response_data, 'html.parser')
            pwform = dict([(t["name"],t["value"]) for t in responseSoup.find('form', id='credentialsForm').find_all("input", type="hidden")])
            pwform["password"] = self._session_auth_password
            pw_url = authissuer+responseSoup.find('form', id='credentialsForm').get('action')

            # POST password
            # https://identity.vwgroup.io/signin-service/v1/xxx@apps_vw-dilab_com/login/authenticate
            self._session_auth_headers['Referer'] = pe_url
            self._session_auth_headers['Origin'] = authissuer
            excepted = False
            
            req = await self._session.post(
                url=pw_url,
                headers=self._session_auth_headers,
                data = pwform,
                allow_redirects=False
            )
            if req.status != 302:
                return ""

            # https://identity.vwgroup.io/oidc/v1/oauth/sso?clientId=xxx@apps_vw-dilab_com&relayState=xxx&userId=xxxGUID&HMAC=xxxx
            ref_url_1 = req.headers.get("location")
            req = await self._session.get(ref_url_1, allow_redirects=False, headers=self._session_auth_headers)
            if req.status != 302:
                return ""            

            # https://identity.vwgroup.io/oidc/v1/oauth/client/callback?clientId=xxx@apps_vw-dilab_com&relayState=xxx&userId=xxxGUID&HMAC=xxx
            ref_url_3 = req.headers.get('location')
            req = await self._session.get(
                url=ref_url_3,
                allow_redirects=False,
                headers=self._session_auth_headers
            )
            if req.status != 302:
                return ""

            # skodaconnect://oidc.login/#code=xxx&access_token=xxx&expires_in=3600&token_type=bearer&id_token=xxx 
            skodaURL = req.headers.get('location')

            # get tokens
            # https://tokenrefreshservice.apps.emea.vwapps.io/exchangeAuthCode
            jwtauth_code = parse_qs(urlparse(skodaURL).fragment).get('code')[0]
            jwtaccess_token = parse_qs(urlparse(skodaURL).fragment).get('access_token')[0]
            jwtid_token = parse_qs(urlparse(skodaURL).fragment).get('id_token')[0]
            
            tokenBody = {
                "auth_code": jwtauth_code,
                "id_token":  jwtid_token,
                "brand": "skoda"
            }
            tokenURL = "https://tokenrefreshservice.apps.emea.vwapps.io/exchangeAuthCode"
            req = await self._session.post(
                url=tokenURL,
                headers=self._session_auth_headers,
                data = tokenBody,
                allow_redirects=False
            )
            if req.status != 200:
                return ""
            
            vwtok = await req.json()
            atoken = vwtok["access_token"]
            rtoken = vwtok["refresh_token"]
            
            # another tokens
            # https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth/mobile/oauth2/v1/token
            tokenBody2 =  {
                "grant_type": "id_token",
                "token": jwtid_token,
                "scope": "sc2:fal"
            }
            req = await self._session.post(
                    url='https://mbboauth-1d.prd.ece.vwg-connect.com/mbbcoauth/mobile/oauth2/v1/token',
                    headers= {
                        "User-Agent": "okhttp/3.7.0",
                        "X-App-Version": "3.2.6",
                        "X-App-Name": "cz.skodaauto.connect",
                        "X-Client-Id": "28cd30c6-dee7-4529-a0e6-b1e07ff90b79",
                        "Host": "mbboauth-1d.prd.ece.vwg-connect.com",
                    },
                    #self._session_headers,
                    data = tokenBody2,
                    allow_redirects=False
                )
            if req.status > 400:
                _LOGGER.debug("Tokens wrong")
                return ""
            else:
                _LOGGER.debug("Tokens OK")
            rtokens = await req.json()
            atoken = rtokens["access_token"]
            rtoken = rtokens["refresh_token"]
 
            # Update headers for requests            
            self._session_headers['Authorization'] = "Bearer " + atoken            
            self._session_logged_in = True
            return True

        except Exception as error:
            _LOGGER.error('Failed to login to Skoda Connect, %s' % error)
            self._session_logged_in = False
            return False

    async def _request(self, method, url, **kwargs):
        """Perform a query to the Skoda Connect"""
        # try:
        _LOGGER.debug("Request for %s", url)        

        async with self._session.request(
            method,
            url,
            headers=self._session_headers,
            timeout=ClientTimeout(total=TIMEOUT.seconds),
            cookies=self._jarCookie,
            **kwargs
        ) as response:
            response.raise_for_status()

            if self._jarCookie != "":
                self._jarCookie.update(response.cookies)
            else:
                self._jarCookie = response.cookies

            res = await response.json(loads=json_loads)
            _LOGGER.debug(f'Received [{response.status}] response: {res}')
            return res
        # except Exception as error:
        #     _LOGGER.warning(
        #         "Failure when communcating with the server: %s", error
        #     )
        #     raise

    async def _logout(self):
        await self.post('-/logout/revoke')
        # remove cookies from session as we have logged out
        self._clear_cookies()

    def _make_url(self, ref, vin=''):  
        replacedUrl = re.sub("\$vin", vin, ref)  
        if ("://" in replacedUrl):
            #already server contained in URL
            return replacedUrl
        else:
            return urljoin( self._session_auth_ref_url, replacedUrl)

    async def get(self, url, vin=''):
        """Perform a get query to the online service."""
        return await self._request(METH_GET, self._make_url(url, vin))

    async def post(self, url, vin='', **data):
        """Perform a post query to the online service."""
        if data:
            return await self._request(METH_POST, self._make_url(url, vin), **data)
        else:
            return await self._request(METH_POST, self._make_url(url, vin))

    async def update(self):
        """Update status."""
        try:
            if self._session_first_update:
                if not await self.validate_login:
                    _LOGGER.info('Session expired, creating new login session to skoda connect.')
                    await self._login()
            else:
                self._session_first_update = True

            # fetch vehicles
            _LOGGER.debug('Fetching vehicles')
            
            # get vehicles
            if "Content-Type" in self._session_headers:
                del self._session_headers["Content-Type"]
            loaded_vehicles = await self.get(
                url='https://msg.volkswagen.de/fs-car/usermanagement/users/v1/skoda/CZ/vehicles'
            )
            _LOGGER.debug('URL loaded')

            # update vehicles
            if loaded_vehicles.get('userVehicles', {}).get('vehicle', []):
                _LOGGER.debug('Vehicle JSON string exists')
                for vehicle in loaded_vehicles.get('userVehicles').get('vehicle'):
                    vehicle_url = vehicle
                    _LOGGER.debug('Vehicle_URL %s', vehicle_url)
                    self._state.update({vehicle_url: dict()})
                    # if vehicle_url not in self._state:
                    #     _LOGGER.debug('Vehicle_URL not in states, adding')
                    #     self._state.update({vehicle_url: dict()})
                    # else:
                    #     _LOGGER.debug('Vehicle_URL in states, updating')
                    #     for key, value in vehicle.items():
                    #         self._state[vehicle_url].update({key: value})

            _LOGGER.debug('Going to call vehicle updates')
            # get vehicle data
            for vehicle in self.vehicles:
                # update data in all vehicles
                await vehicle.update()
            return True
        except (IOError, OSError, LookupError) as error:
            _LOGGER.warning(f'Could not update information from skoda connect: {error}')

    async def update_vehicle(self, vehicle):
        url = vehicle._url
        self._vin=url
        _LOGGER.debug(f'Updating vehicle status {vehicle.vin}')
        
        #https://msg.volkswagen.de/fs-car/promoter/portfolio/v1/skoda/CZ/vehicle/$vin/carportdata
        try:
            
            response = await self.get('fs-car/promoter/portfolio/v1/skoda/CZ/vehicle/$vin/carportdata', vin=url)            
            if response.get('carportData', {}) :
                self._state[url].update(
                    {'carportData': response.get('carportData', {})}
                )
            else:
                _LOGGER.debug(f'Could not fetch carportData: {response}')
        except Exception as err:
            _LOGGER.debug(f'Could not fetch carportData, error: {err}')

        #https://msg.volkswagen.de/fs-car/bs/cf/v1/skoda/CZ/vehicles/$vin/position
        try:
            
            response = await self.get('fs-car/bs/cf/v1/skoda/CZ/vehicles/$vin/position', vin=url)            
            if response.get('findCarResponse', {}) :
                self._state[url].update(
                    {'findCarResponse': response.get('findCarResponse', {})}
                )
            else:
                _LOGGER.debug(f'Could not fetch position: {response}')
        except Exception as err:
            _LOGGER.debug(f'Could not fetch position, error: {err}')

        #https://msg.volkswagen.de/fs-car/bs/vsr/v1/skoda/CZ/vehicles/$vin/status
        try:
            
            response = await self.get('fs-car/bs/vsr/v1/skoda/CZ/vehicles/$vin/status', vin=url)            
            if response.get('StoredVehicleDataResponse', {}).get('vehicleData', {}).get('data', {})[0].get('field', {})[0] :
                self._state[url].update(
                    {'StoredVehicleDataResponse': response.get('StoredVehicleDataResponse', {})}
                )                
                self._state[url].update(
                    {'StoredVehicleDataResponseParsed' :  dict([(e["id"],e if "value" in e else "") for f in [s["field"] for s in response["StoredVehicleDataResponse"]["vehicleData"]["data"]] for e in f]) }
                )
            else:
                _LOGGER.debug(f'Could not fetch StoredVehicleDataResponse: {response}')
        except Exception as err:
            _LOGGER.debug(f'Could not fetch StoredVehicleDataResponse, error: {err}')
        
        #TRIP DATA
        #https://msg.volkswagen.de/fs-car/bs/tripstatistics/v1/skoda/CZ/vehicles/TMBJJ7NS3L8500308/tripdata/shortTerm?newest
        # -or- shortTerm?type=list -or- longTerm?type=list
        try:            
            response = await self.get('fs-car/bs/tripstatistics/v1/skoda/CZ/vehicles/$vin/tripdata/shortTerm?newest', vin=url)            
            if response.get('tripData', {}):
                self._state[url].update(
                    {'tripstatistics': response.get('tripData', {})}
                )                                
            else:
                _LOGGER.debug(f'Could not fetch tripstatistics: {response}')
        except Exception as err:
            _LOGGER.debug(f'Could not fetch tripstatistics, error: {err}')

        # Heating status
        # https://msg.volkswagen.de/fs-car/bs/rs/v1/skoda/CZ/vehicles/$vin/status
        try:
            
            response = await self.get('fs-car/bs/rs/v1/skoda/CZ/vehicles/$vin/status', vin=url)            
            if response.get('statusResponse', {}) :
                self._state[url].update(
                    {'heating': response.get('statusResponse', {})}
                )
            else:
                _LOGGER.debug(f'Could not fetch heating: {response}')
        except Exception as err:
            _LOGGER.debug(f'Could not fetch heating, error: {err}')

    def vehicle(self, vin):
        """Return vehicle for given vin."""
        return next(
            (
                vehicle
                for vehicle in self.vehicles
                if vehicle.unique_id == vin.lower()
            ), None
        )

    @property
    def vehicles(self):
        """Return vehicle state."""
        return (Vehicle(self, url) for url in self._state)

    def vehicle_attrs(self, vehicle_url):
        return self._state.get(vehicle_url)

    @property
    async def validate_login(self):
        try:
            response = await self.get('fs-car/promoter/portfolio/v1/skoda/CZ/vehicle/$vin/carportdata', vin=self._vin)            
            if response.get('carportData', {}) :            
                return True
            else:
                return False
        except (IOError, OSError) as error:
            _LOGGER.warning('Could not validate login: %s', error)
            return False
        except (aiohttp.client_exceptions.ClientResponseError) as error:
            if (error.status == 401):
                _LOGGER.info(f'Could not validate login - unauthorized, need to login again')
                return False
        except Exception as error:
            _LOGGER.warning(f'Could not validate login2: {error}')
            return False

    @property
    def logged_in(self):
        return self._session_logged_in


class Vehicle:
    def __init__(self, conn, url):
        self._connection = conn
        self._url = url        

    async def update(self):
        # await self._connection.update(request_data=False)
        await self._connection.update_vehicle(self)

    async def get(self, query):
        """Perform a query to the online service."""
        req = await self._connection.get(query, self._url)
        return req

    async def post(self, query, **data):
        """Perform a query to the online service."""
        req = await self._connection.post(query, self._url, **data)
        return req

    async def call(self, query, **data):
        """Make remote method call."""
        try:
            if not await self._connection.validate_login:
                _LOGGER.info('Session expired, reconnecting to skoda connect.')
                await self._connection._login()

            res = await self.post(query, **data)
            if res.get('performActionResponse', {}).get('requestId', False):
                _LOGGER.info('Message delivered, requestId=%s', res.get('performActionResponse', {}).get('requestId', 0))
                return True
            else:
                _LOGGER.warning(f'Failed to execute {query}, response is:{str(res)}')
                return

        except Exception as error:
            _LOGGER.warning(f'Failure to execute: {error}')
    
    async def requestSecToken(self,spin):
        try:             
            response = await self.get(self._connection._make_url('https://mal-1a.prd.ece.vwg-connect.com/api/rolesrights/authorization/v2/vehicles/$vin/services/rheating_v1/operations/P_QSACT/security-pin-auth-requested', vin=self.vin))
            secToken = response["securityPinAuthInfo"]["securityToken"]
            challenge = response["securityPinAuthInfo"]["securityPinTransmission"]["challenge"]
            securpin = await self.generateSecurPin(challenge, spin)
            body = "{ \"securityPinAuthentication\": { \"securityPin\": { \"challenge\": \""+challenge+"\", \"securityPinHash\": \""+securpin+"\" }, \"securityToken\": \""+secToken+"\" }}"

            self._connection._session_headers["Content-Type"]="application/json"
            response = await self.post('https://mal-1a.prd.ece.vwg-connect.com/api/rolesrights/authorization/v2/security-pin-auth-completed', data=body)
            del self._connection._session_headers["Content-Type"]
            return response["securityToken"]
        except Exception as err:
            _LOGGER.error(f'Could not generate security token for active  (maybe wrong SPIN?), error: {err}')

    async def generateSecurPin(self,challenge, pin):                
        pinArray = bytearray.fromhex(pin);        
        byteChallenge = bytearray.fromhex(challenge);                     
        pinArray.extend(byteChallenge)        
        return hashlib.sha512(pinArray).hexdigest()

    @property
    def attrs(self):
        return self._connection.vehicle_attrs(self._url)

    def has_attr(self, attr):
        return is_valid_path(self.attrs, attr)

    def get_attr(self, attr):
        return find_path(self.attrs, attr)

    def dashboard(self, **config):
        from . import dashboardskoda        
        return dashboardskoda.Dashboard(self, **config)

    @property
    def vin(self):
        #return self.attrs.get('vin').lower()
        return self._url

    @property
    def unique_id(self):
        return self.vin

    @property
    def last_connected(self):
        """Return when vehicle was last connected to skoda connect"""
        last_connected = self.attrs.get('StoredVehicleDataResponse').get('vehicleData').get('data')[0].get('field')[0].get('tsCarSentUtc')
        #if last_connected:
            #last_connected = f'{last_connected[0]}  {last_connected[1]}'
         #   date_patterns = ["%Y-%m-%dT%H:%M:%S", "%d.%m.%Y %H:%M", "%d-%m-%Y %H:%M"]
            #for date_pattern in date_patterns:
                #try:
                    #return datetime.strptime(last_connected, date_pattern).strftime("%Y-%m-%d %H:%M:%S")
                #except ValueError:
                    #pass
        return last_connected

    @property
    def is_last_connected_supported(self):
        """Return when vehicle was last connected to skoda connect"""
        if self.attrs.get('StoredVehicleDataResponse', {}).get('vehicleData', {}).get('data', {})[0].get('field', {})[0].get('tsCarSentUtc', []):
            return True

    @property
    def climatisation_target_temperature(self):
        #Not implemented for SKODA
        return self.attrs.get('vehicleEmanager', {}).get('rpc', {}).get('settings',{}).get('targetTemperature', 0)

    @property
    def is_climatisation_target_temperature_supported(self):
        #Not implemented for SKODA
        return self.is_climatisation_supported

    @property
    def climatisation_without_external_power(self):
        #Not implemented for SKODA
        return self.attrs.get('vehicleEmanager', {}).get('rpc', {}).get('settings', {}).get('climatisationWithoutHVPower', False)

    @property
    def is_climatisation_without_external_power_supported(self):
        #Not implemented for SKODA
        return self.is_climatisation_supported

    @property
    def service_inspection(self):
        """Return time left for service inspection"""
        return self.attrs.get('StoredVehicleDataResponseParsed')['0x0203010004'].get('value')
        

    @property
    def is_service_inspection_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0203010004' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def oil_inspection(self):
        """Return time left for service inspection"""
        return self.attrs.get('StoredVehicleDataResponseParsed')['0x0203010002'].get('value')

    @property
    def is_oil_inspection_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0203010002' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def adblue_level(self):
        return self.attrs.get('StoredVehicleDataResponseParsed')['0x02040C0001'].get('value',0)

    @property
    def is_adblue_level_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x02040C0001' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def battery_level(self):
        #Not implemented for SKODA
        return self.attrs.get('vehicleStatus', {}).get('batteryLevel', 0)

    @property
    def is_battery_level_supported(self):
        #Not implemented for SKODA
        if type(self.attrs.get('vehicleStatus', {}).get('batteryLevel', False)) in (float, int):
            return True

    @property
    def charge_max_ampere(self):
        #Not implemented for SKODA
        """Return charge max ampere"""
        return self.attrs.get('vehicleEmanager').get('rbc').get('settings').get('chargerMaxCurrent')

    @property
    def is_charge_max_ampere_supported(self):
        #Not implemented for SKODA
        if type(self.attrs.get('vehicleEmanager', {}).get('rbc', {}).get('settings', {}).get('chargerMaxCurrent', False)) in (float, int):
            return True

    @property
    def parking_light(self):
        """Return true if parking light is on"""
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301010001'].get('value',0))
        if response != 2:
            return True
        else:
            return False

    @property
    def is_parking_light_supported(self):
        """Return true if parking light is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301010001' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def distance(self):
        value = self.attrs.get('StoredVehicleDataResponseParsed')['0x0101010002'].get('value',0)
        if value:
            return int(value)

    @property
    def is_distance_supported(self):
        """Return true if distance is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0101010002' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def position(self):
        """Return  position."""
        posObj = self.attrs.get('findCarResponse')
        lat = int(posObj.get('Position').get('carCoordinate').get('latitude'))/1000000
        lng = int(posObj.get('Position').get('carCoordinate').get('longitude'))/1000000
        parkingTime = posObj.get('parkingTimeUTC')  
        output = {
            "lat" : lat,
            "lng" : lng,
            "timestamp" : parkingTime
        }        
        return output

    @property
    def is_position_supported(self):
        """Return true if vehichle has position."""
        if self.attrs.get('findCarResponse', {}).get('Position', {}).get('carCoordinate', {}).get('latitude', False):
            return True

    @property
    def model(self):
        """Return model"""
        return self.attrs.get('carportData').get('modelName')

    @property
    def is_model_supported(self):
        if self.attrs.get('carportData').get('modelName',False):
            return True

    @property
    def model_year(self):
        """Return model year"""
        return self.attrs.get('carportData').get('modelYear')

    @property
    def is_model_year_supported(self):
        if self.attrs.get('carportData').get('modelYear',False):
            return True

    @property
    def model_image(self):
        #Not implemented for SKODA
        """Return model image"""
        return self.attrs.get('imageUrl')

    @property
    def is_model_image_supported(self):
        #Not implemented for SKODA
        if self.attrs.get('imageUrl', False):
            return True

    @property
    def charging(self):
        #Not implemented for SKODA
        """Return status of charging."""
        response = self.attrs.get('vehicleEmanager', {}).get('rbc', {}).get('status', {}).get('chargingState', {})
        if response == 'CHARGING':
            return True
        else:
            return False

    @property
    def is_charging_supported(self):
        #Not implemented for SKODA
        """Return true if vehichle has heater."""
        if type(self.attrs.get('vehicleEmanager', {}).get('rbc', {}).get('status', {}).get('batteryPercentage', False)) in (float, int):
            return True

    @property
    def electric_range(self):
        #Not implemented for SKODA
        return self.attrs.get('vehicleStatus', {}).get('batteryRange', 0)

    @property
    def is_electric_range_supported(self):
        #Not implemented for SKODA
        if type(self.attrs.get('vehicleStatus', {}).get('batteryRange', False)) in (float, int):
            return True

    @property
    def combustion_range(self):
        value = self.attrs.get('StoredVehicleDataResponseParsed')['0x0301030005'].get('value',0)
        if value:
            return int(value)

    @property
    def is_combustion_range_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301030005' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def combined_range(self):
        #Not implemented for SKODA
        return self.attrs.get('vehicleStatus', {}).get('totalRange', 0)

    @property
    def is_combined_range_supported(self):
        #Not implemented for SKODA
        if type(self.attrs.get('vehicleStatus', {}).get('totalRange', False)) in (float, int):
            return True

    @property
    def fuel_level(self):
        value = self.attrs.get('StoredVehicleDataResponseParsed')['0x030103000A'].get('value',0)
        if value:
            return int(value)

    @property
    def is_fuel_level_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x030103000A' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def external_power(self):
        #Not implemented for SKODA
        """Return true if external power is connected."""
        check = self.attrs.get('vehicleEmanager', {}).get('rbc', {}).get('status', {}).get('pluginState', {})
        if check == 'CONNECTED':
            return True
        else:
            return False

    @property
    def is_external_power_supported(self):
        #Not implemented for SKODA
        """External power supported."""
        if self.attrs.get('vehicleEmanager', {}).get('rbc', {}).get('status', {}).get('pluginState', False):
            return True

    @property
    def electric_climatisation(self):
        #Not implemented for SKODA
        """Return status of climatisation."""
        climatisation_type = self.attrs.get('vehicleEmanager', {}).get('rpc', {}).get('settings', {}).get('electric', False)
        status = self.attrs.get('vehicleEmanager', {}).get('rpc', {}).get('status', {}).get('climatisationState', '')
        if status in ['HEATING', 'COOLING'] and climatisation_type is True:
            return True
        else:
            return False

    @property
    def is_climatisation_supported(self):
        #Not implemented for SKODA
        """Return true if vehichle has heater."""
        response = self.attrs.get('vehicleEmanager', {}).get('rpc', {}).get('climaterActionState', '')
        if response == 'AVAILABLE' or response == 'NO_PLUGIN':
            return True

    @property
    def is_electric_climatisation_supported(self):
        #Not implemented for SKODA
        """Return true if vehichle has heater."""
        return self.is_climatisation_supported

    @property
    def combustion_climatisation(self):        
        """Return status of combustion climatisation."""
        return self.attrs.get('heating', {}).get('climatisationStateReport', {}).get('climatisationState', False) == 'ventilation'

    @property
    def is_combustion_climatisation_supported(self):        
        """Return true if vehichle has combustion climatisation."""         
        if self.attrs.get('heating', {}).get('climatisationStateReport', {}).get('climatisationState', False):
            return True

    @property
    def window_heater(self):
        #Not implemented for SKODA
        """Return status of window heater."""
        ret = False
        status_front = self.attrs.get('vehicleEmanager', {}).get('rpc', {}).get('status', {}).get('windowHeatingStateFront', '')
        if status_front == 'ON':
            ret = True

        status_rear = self.attrs.get('vehicleEmanager', {}).get('rpc', {}).get('status', {}).get('windowHeatingStateRear', '')
        if status_rear == 'ON':
            ret = True
        return ret

    @property
    def is_window_heater_supported(self):
        #Not implemented for SKODA
        """Return true if vehichle has heater."""
        if self.is_electric_climatisation_supported:
            if self.attrs.get('vehicleEmanager', {}).get('rpc', {}).get('status', {}).get('windowHeatingAvailable', False):
                return True

    @property
    def combustion_engine_heating(self):
        """Return status of combustion engine heating."""
        return self.attrs.get('heating', {}).get('climatisationStateReport', {}).get('climatisationState', False) == 'heating'

    @property
    def is_combustion_engine_heating_supported(self):
        """Return true if vehichle has combustion engine heating."""
        if self.attrs.get('heating', {}).get('climatisationStateReport', {}).get('climatisationState', False):
            return True

    @property
    def windows_closed(self):        
        return (self.window_closed_left_front and self.window_closed_left_back and self.window_closed_right_front and self.window_closed_right_back)

    @property
    def is_windows_closed_supported(self):
        """Return true if window state is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301050001' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def window_closed_left_front(self):
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301050001'].get('value',0))
        if response == 3:
            return True
        else:
            return False
        
    @property
    def is_window_closed_left_front_supported(self):
        """Return true if window state is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301050001' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def window_closed_right_front(self):
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301050005'].get('value',0))
        if response == 3:
            return True
        else:
            return False

    @property
    def is_window_closed_right_front_supported(self):
        """Return true if window state is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301050005' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def window_closed_left_back(self):
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301050003'].get('value',0))
        if response == 3:
            return True
        else:
            return False

    @property
    def is_window_closed_left_back_supported(self):
        """Return true if window state is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301050003' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def window_closed_right_back(self):
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301050007'].get('value',0))
        if response == 3:
            return True
        else:
            return False

    @property
    def is_window_closed_right_back_supported(self):
        """Return true if window state is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301050007' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def sunroof_closed(self):
        response = self.attrs.get('StoredVehicleDataResponseParsed')['0x030105000B'].get('value',0)
        if response == 3:
            return True
        else:
            return False

    @property
    def is_sunroof_closed_supported(self):
        """Return true if sunroof state is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x030105000B' in self.attrs.get('StoredVehicleDataResponseParsed'):
                if (int(self.attrs.get('StoredVehicleDataResponseParsed')['0x030105000B'].get('value',0)) == 0):
                    return False
                else:
                    return True
            else:
                return False

    @property
    def charging_time_left(self):
        #Not implemented for SKODA
        if self.external_power:
            hours = self.attrs.get('vehicleEmanager', {}).get('rbc', {}).get('status', {}).get('chargingRemaningHour', 0)
            minutes = self.attrs.get('vehicleEmanager', {}).get('rbc', {}).get('status', {}).get('chargingRemaningMinute', 0)
            if hours and minutes:
                # return 0 if we are not able to convert the values we get from skoda connect.
                try:
                    return (int(hours) * 60) + int(minutes)
                except Exception:
                    pass
        return 0

    @property
    def is_charging_time_left_supported(self):
        #Not implemented for SKODA
        return self.is_charging_supported

    @property
    def door_locked(self):        
        #LEFT FRONT
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040001'].get('value',0))
        if response != 2:
            return False
        #LEFT REAR
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040004'].get('value',0))
        if response != 2:
            return False
        #RIGHT FRONT
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040007'].get('value',0))
        if response != 2:
            return False
        #RIGHT REAR
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x030104000A'].get('value',0))
        if response != 2:
            return False

        return True

    @property
    def is_door_locked_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301040001' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def door_closed_left_front(self):
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040002'].get('value',0))
        if response == 3:
            return True
        else:
            return False

    @property
    def is_door_closed_left_front_supported(self):
        """Return true if window state is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301040002' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def door_closed_right_front(self):
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040008'].get('value',0))
        if response == 3:
            return True
        else:
            return False

    @property
    def is_door_closed_right_front_supported(self):
        """Return true if window state is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301040008' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def door_closed_left_back(self):
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x0301040005'].get('value',0))
        if response == 3:
            return True
        else:
            return False

    @property
    def is_door_closed_left_back_supported(self):
        """Return true if window state is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x0301040005' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def door_closed_right_back(self):
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x030104000B'].get('value',0))
        if response == 3:
            return True
        else:
            return False

    @property
    def is_door_closed_right_back_supported(self):
        """Return true if window state is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x030104000B' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def trunk_closed(self):
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x030104000E'].get('value',0))
        if response == 3:
            return True
        else:
            return False

    @property
    def is_trunk_closed_supported(self):
        """Return true if window state is supported"""
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x030104000E' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def trunk_locked(self):
        response = int(self.attrs.get('StoredVehicleDataResponseParsed')['0x030104000D'].get('value',0))
        if response == 2:
            return True
        else:
            return False

    @property
    def is_trunk_locked_supported(self):
        if self.attrs.get('StoredVehicleDataResponseParsed', {}):
            if '0x030104000D' in self.attrs.get('StoredVehicleDataResponseParsed'):
                return True
            else:
                return False

    @property
    def request_in_progress(self):
        #Not implemented for SKODA
        check = self.attrs.get('vehicleStatus', {}).get('requestStatus', {})
        if check == 'REQUEST_IN_PROGRESS':
            return True
        else:
            return False

    @property
    def is_request_in_progress_supported(self):
        #Not implemented for SKODA
        response = self.attrs.get('vehicleStatus', {}).get('requestStatus', {})
        if response or response is None:
            return True

    # trips
    @property
    def trip_last_entry(self):        
        return self.attrs.get('tripstatistics', {})

    @property
    def trip_last_average_speed(self):
        return self.trip_last_entry.get('averageSpeed')

    @property
    def is_trip_last_average_speed_supported(self):        
        response = self.trip_last_entry
        if response and type(response.get('averageSpeed')) in (float, int):
            return True

    @property
    def trip_last_average_electric_consumption(self):
        return self.trip_last_entry.get('averageElectricConsumption')

    @property
    def is_trip_last_average_electric_consumption_supported(self):
        response = self.trip_last_entry
        if response and type(response.get('averageElectricConsumption')) in (float, int):
            return True

    @property
    def trip_last_average_fuel_consumption(self):
        return int(self.trip_last_entry.get('averageFuelConsumption'))/10

    @property
    def is_trip_last_average_fuel_consumption_supported(self):
        response = self.trip_last_entry
        if response and type(response.get('averageFuelConsumption')) in (float, int):
            return True

    @property
    def trip_last_average_auxillary_consumption(self):
        return self.trip_last_entry.get('averageAuxiliaryConsumption')

    @property
    def is_trip_last_average_auxillary_consumption_supported(self):
        response = self.trip_last_entry
        if response and type(response.get('averageAuxiliaryConsumption')) in (float, int):
            return True

    @property
    def trip_last_duration(self):
        return self.trip_last_entry.get('traveltime')

    @property
    def is_trip_last_duration_supported(self):
        response = self.trip_last_entry
        if response and type(response.get('traveltime')) in (float, int):
            return True

    @property
    def trip_last_length(self):
        return self.trip_last_entry.get('mileage')

    @property
    def is_trip_last_length_supported(self):
        response = self.trip_last_entry
        if response and type(response.get('mileage')) in (float, int):
            return True

    @property
    def trip_last_recuperation(self):
        #Not implemented for SKODA
        return self.trip_last_entry.get('recuperation')

    @property
    def is_trip_last_recuperation_supported(self):
        #Not implemented for SKODA
        response = self.trip_last_entry
        if response and type(response.get('recuperation')) in (float, int):
            return True

    @property
    def trip_last_total_electric_consumption(self):
        #Not implemented for SKODA
        return self.trip_last_entry.get('totalElectricConsumption')

    @property
    def is_trip_last_total_electric_consumption_supported(self):
        #Not implemented for SKODA
        response = self.trip_last_entry
        if response and type(response.get('totalElectricConsumption')) in (float, int):
            return True

    # actions
    async def trigger_request_update(self):
        if self.is_request_in_progress_supported:
            if not self.request_in_progress:
                resp = await self.call('-/vsr/request-vsr', dummy='data')
                if not resp or (isinstance(resp, dict) and resp.get('errorCode') != '0'):
                    _LOGGER.error('Failed to request vehicle update')
                else:
                    await self.update()
                    return resp
            else:
                _LOGGER.warning('Request update is already in progress')
        else:
            _LOGGER.error('No request update support.')

    async def lock_car(self, spin):
        if spin:
            resp = await self.call('-/vsr/remote-lock', spin=spin)
            if not resp:
                _LOGGER.warning('Failed to lock car')
            else:
                await self.update()
                return resp
        else:
            _LOGGER.error('Invalid SPIN provided')

    async def unlock_car(self, spin):
        if spin:
            resp = await self.call('-/vsr/remote-unlock', spin=spin)
            if not resp:
                _LOGGER.warning('Failed to unlock car')
            else:
                await self.update()
                return resp
        else:
            _LOGGER.error('Invalid SPIN provided')

    async def start_electric_climatisation(self):
        """Turn on/off climatisation."""
        if self.is_electric_climatisation_supported:
            resp = await self.call('-/emanager/trigger-climatisation', triggerAction=True, electricClima=True)
            if not resp:
                _LOGGER.warning('Failed to start climatisation')
            else:
                await self.update()
                return resp
        else:
            _LOGGER.error('No climatization support.')

    async def stop_electric_climatisation(self):
        """Turn on/off climatisation."""
        if self.is_electric_climatisation_supported:
            resp = await self.call('-/emanager/trigger-climatisation', triggerAction=False, electricClima=True)
            if not resp:
                _LOGGER.warning('Failed to stop climatisation')
            else:
                await self.update()
                return resp
        else:
            _LOGGER.error('No climatization support.')

    async def start_window_heater(self):
        """Turn on/off window heater."""
        if self.is_window_heater_supported:
            resp = await self.call('-/emanager/trigger-windowheating', triggerAction=True)
            if not resp:
                _LOGGER.warning('Failed to start window heater')
            else:
                await self.update()
                return resp
        else:
            _LOGGER.error('No climatization support.')

    async def stop_window_heater(self):
        """Turn on/off window heater."""
        if self.is_window_heater_supported:
            resp = await self.call('-/emanager/trigger-windowheating', triggerAction=False)
            if not resp:
                _LOGGER.warning('Failed to stop window heater')
        else:
            await self.update()
            _LOGGER.error('No window heating support.')

    async def start_combustion_engine_heating(self, spin, combustionengineheatingduration):
        if spin:
            if self.is_combustion_engine_heating_supported:
                secToken = await self.requestSecToken(spin)                                
                url = "fs-car/bs/rs/v1/skoda/CZ/vehicles/$vin/action"
                data = "{ \"performAction\": { \"quickstart\": { \"climatisationDuration\": "+str(combustionengineheatingduration)+", \"startMode\": \"heating\", \"active\": true } } }"
                if "Content-Type" in self._connection._session_headers:
                    contType = self._connection._session_headers["Content-Type"]
                else:
                    contType = ''

                try:
                    self._connection._session_headers["Content-Type"] = "application/vnd.vwg.mbb.RemoteStandheizung_v2_0_2+json"
                    self._connection._session_headers["x-mbbSecToken"] = secToken
                    resp = await self.call(url, data=data)
                    if not resp:
                        _LOGGER.warning('Failed to start combustion engine heating')
                    else:
                        time.sleep(30)
                        await self.update()
                        if not self.combustion_engine_heating:
                            time.sleep(60)
                            await self.update()
                        return 
                except Exception as error:
                    _LOGGER.error('Failed to start combustion engine heating - %s' % error)
                
                #Cleanup headers
                if "x-mbbSecToken" in self._connection._session_headers: del self._connection._session_headers["x-mbbSecToken"]
                if "Content-Type" in self._connection._session_headers: del self._connection._session_headers["Content-Type"]
                if contType: self._connection._session_headers["Content-Type"]=contType
            else:
                _LOGGER.error('No combustion engine heating support.')
        else:
            _LOGGER.error('Invalid SPIN provided')

    async def stop_combustion_engine_heating(self):
        if self.is_combustion_engine_heating_supported or self.is_combustion_climatisation_supported:
            url = "fs-car/bs/rs/v1/skoda/CZ/vehicles/$vin/action"
            data = "{ \"performAction\": { \"quickstop\": { \"active\": false } } }"
            if "Content-Type" in self._connection._session_headers:
                contType = self._connection._session_headers["Content-Type"]
            else:
                contType = ''

            try:
                self._connection._session_headers["Content-Type"] = "application/vnd.vwg.mbb.RemoteStandheizung_v2_0_2+json"                
                resp = await self.call(url, data=data)
                if not resp:
                    _LOGGER.warning('Failed to stop combustion engine heating')
                else:
                    await self.update()
                    return 
            except Exception as error:
                _LOGGER.error('Failed to stop combustion engine heating - %s' % error)
            
            #Cleanup headers
            if "Content-Type" in self._connection._session_headers: del self._connection._session_headers["Content-Type"]
            if contType: self._connection._session_headers["Content-Type"]=contType
        else:
            _LOGGER.error('No combustion engine heating support.')

    async def start_combustion_climatisation(self, spin, combustionengineclimatisationduration):
        if spin:
            if self.is_combustion_climatisation_supported:
                secToken = await self.requestSecToken(spin)                                
                url = "fs-car/bs/rs/v1/skoda/CZ/vehicles/$vin/action"
                data = "{ \"performAction\": { \"quickstart\": { \"climatisationDuration\": "+str(combustionengineclimatisationduration)+", \"startMode\": \"ventilation\", \"active\": true } } }"
                if "Content-Type" in self._connection._session_headers:
                    contType = self._connection._session_headers["Content-Type"]
                else:
                    contType = ''

                try:
                    self._connection._session_headers["Content-Type"] = "application/vnd.vwg.mbb.RemoteStandheizung_v2_0_2+json"
                    self._connection._session_headers["x-mbbSecToken"] = secToken
                    resp = await self.call(url, data=data)
                    if not resp:
                        _LOGGER.warning('Failed to start combustion engine climatisation')
                    else:
                        time.sleep(30)
                        await self.update()
                        if not self.combustion_climatisation:
                            time.sleep(60)
                            await self.update()                        
                except Exception as error:
                    _LOGGER.error('Failed to start combustion engine climatisation - %s' % error)
                
                #Cleanup headers
                if "x-mbbSecToken" in self._connection._session_headers: del self._connection._session_headers["x-mbbSecToken"]
                if "Content-Type" in self._connection._session_headers: del self._connection._session_headers["Content-Type"]
                if contType: self._connection._session_headers["Content-Type"]=contType
            else:
                _LOGGER.error('No combustion engine climatisation support.')
        else:
            _LOGGER.error('Invalid SPIN provided')

    async def stop_combustion_climatisation(self):
        return await self.stop_combustion_engine_heating()

    async def start_charging(self):
        """Turn on/off window heater."""
        if self.is_charging_supported:
            resp = await self.call('-/emanager/charge-battery', triggerAction=True, batteryPercent='100')
            if not resp:
                _LOGGER.warning('Failed to start charging')
            else:
                await self.update()
                return resp
        else:
            _LOGGER.error('No charging support.')

    async def stop_charging(self):
        """Turn on/off window heater."""
        if self.is_charging_supported:
            resp = await self.call('-/emanager/charge-battery', triggerAction=False, batteryPercent='99')
            if not resp:
                _LOGGER.warning('Failed to stop charging')
            else:
                await self.update()
                return resp
        else:
            _LOGGER.error('No charging support.')

    async def set_climatisation_target_temperature(self, target_temperature):
        """Turn on/off window heater."""
        if self.is_electric_climatisation_supported:
        #or self.is_combustion_climatisation_supported:
            resp = await self.call('-/emanager/set-settings', chargerMaxCurrent=None, climatisationWithoutHVPower=None, minChargeLimit=None, targetTemperature=target_temperature)
            if not resp:
                _LOGGER.warning('Failed to set target temperature for climatisation')
            else:
                await self.update()
                return resp
        else:
            _LOGGER.error('No climatisation support.')

    async def get_status(self, timeout=10):
        """Check status from call"""
        retry_counter = 0
        while retry_counter < timeout:
            resp = await self.call('-/emanager/get-notifications', data='dummy')
            data = resp.get('actionNotificationList', {})
            if data:
                return data
            time.sleep(1)
            retry_counter += 1
        return False

    def __str__(self):
        return self.vin

    @property
    def json(self):
        def serialize(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
        return to_json(
            OrderedDict(sorted(self.attrs.items())),
            indent=4,
            default=serialize
        )


async def main():
    """Main method."""
    if "-v" in argv:
        logging.basicConfig(level=logging.INFO)
    elif "-vv" in argv:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.ERROR)

    logging.basicConfig(level=logging.DEBUG)

    async with ClientSession(headers={'Connection': 'keep-alive'}) as session:
        connection = Connection(session, **read_config())
        if await connection._login():
            if await connection.update():
                for vehicle in connection.vehicles:
                    print(f'Vehicle id: {vehicle}')
                    print('Supported sensors:')
                    for instrument in vehicle.dashboard().instruments:
                        print(f' - {instrument.name} (domain:{instrument.component}) - {instrument.str_state}')
                    #print(vehicle.last_connected)
                    #print(vehicle.service_inspection)
                    #print(vehicle.position)
                    #print(await vehicle.requestSecToken("1234"))
                    #ts = vehicle.position.get('timestamp')
                    #print(ts.astimezone(tz=None))
            #await connection._logout()
                    #await vehicle.start_combustion_engine_heating("1234", 20)
                    #await vehicle.update()
                    #await vehicle.stop_combustion_engine_heating()
            

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    # loop.run(main())
    loop.run_until_complete(main())
