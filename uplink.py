#!/usr/bin/python3

'''
=== PREREQUISITES ===
Run in Python 3

Install requests library, via macOS terminal:
pip3 install requests

login.py has these two lines, with the API key from your Dashboard profile (upper-right email login > API access), and organization ID to call (https://dashboard.meraki.com/api/v0/organizations); separated into different file for security.
api_key = '[API_KEY]'
org_id = '[ORG_ID]'

Usage:
python3 uplink.py

=== DESCRIPTION ===
Iterates through all devices, and exports to two CSV files: one for appliance (MX, Z1, Z3, vMX100) networks to collect WAN uplink information, and the other for all other devices (MR, MS, MC, MV) with local uplink info.

Possible statuses:
Active: active and working WAN port
Ready: standby but working WAN port, not the preferred WAN port
Failed: was working at some point but not anymore
Not connected: nothing was ever connected, no cable plugged in
For load balancing, both WAN links would show active.

For any questions, please contact Shiyue (Shay) Cheng, shiychen@cisco.com

EDIT 2022-09-30 - mirkobau
I Added some improvements:
- to web requests
because I noticed Meraki (or my internet access?) disconnected the session while the script was running, and this caused the json.loads(session.get(...)) part to crash.
So I moved all the line of code into a function that managed some basic, HTTP/connection errors and retries the web request 3 times.
After that it returns an empty json array.
- to some fields and their formats (refs.: ['name'] and str() function)
- added firmware and geolocation, to better identify each device
'''

import csv
import datetime
import json
import requests
import sys
import time
#FIXME20220930 'excepts' does not work with my Python 3.x #from excepts import MalformedRequest, StatusUnknown, InternalError
from requests.exceptions import ConnectionError
from http.client import RemoteDisconnected
from urllib3.exceptions import ProtocolError
from http.client import HTTPException

# See below: all CSV values are converted to a string using the str() funcion.
# This convertion is mainly intended for Excel's mis-interpretation of IP addresses like 10.123.096.228: they are seen as numbers with thousands separators in some locales.
# So this class defines some standards for a correct CSV generation.
class csvquoting(csv.Dialect):
  delimiter = ','
  doublequote = True
  quoting = csv.QUOTE_NONNUMERIC
  quotechar = '"'
  lineterminator = "\r\n"
  skipinitialspace = True

def get_network(network_id, networks):
  return [element for element in networks if network_id == element['id']][0]

def jsonload(path):
  # an empty string means there was an error, because we always expect to receive a JSON structure as a response.
  # (please note a minimal JSON structure like {} or [] still is represented by 2 characters, not 0)
  jsondata = ''
  # retry 3 times, then fail
  retries = 3;
  while not 0 < len(jsondata) and 0 < retries:
    try:
      # I decided to bring the base URL here, to make the code more compact, hence more readable.
      jsondata = session.get('https://api.meraki.com/api/v0/' + path, headers=headers).text
    except (ConnectionError, RemoteDisconnected, ProtocolError, HTTPException) as e:
      #FIXME20220930#except (InternalError, StatusUnknown, ConnectionError, RemoteDisconnected, ProtocolError, HTTPException) as e:
      time.sleep(1)
    retries -= 1
  return json.loads(jsondata)

if __name__ == '__main__':
  # Import API key and org ID from login.py
  try:
    import login
    (API_KEY, ORG_ID) = (login.api_key, login.org_id)
  except ImportError:
    API_KEY = input('Enter your Dashboard API key: ')
    ORG_ID = input('Enter your organization ID: ')


  # Find all appliance networks (MX, Z1, Z3, vMX100)
  session = requests.session()
  headers = {'X-Cisco-Meraki-API-Key': API_KEY, 'Content-Type': 'application/json'}
  try:
    name = jsonload('organizations/' + ORG_ID)['name']
  except:
    sys.exit('Incorrect API key or org ID, as no valid data returned')
  networks = jsonload('organizations/' + ORG_ID + '/networks')
  inventory = jsonload('organizations/' + ORG_ID + '/inventory')
  appliances = [device for device in inventory if device['model'][:2] in ('MX', 'Z1', 'Z3', 'vM') and device['networkId'] is not None]
  devices = [device for device in inventory if device not in appliances and device['networkId'] is not None]


  # Output CSV of appliances' info
  today = datetime.date.today()
  csv_file1 = open(name + ' appliances - ' + str(today) + '.csv', 'w', encoding='utf-8')
  fieldnames = ['TimeZone', 'Network', 'Device', 'Serial', 'MAC', 'Model', 'firmware', 'geolocation', 'WAN1 Status', 'WAN1 IP', 'WAN1 Gateway', 'WAN1 Public IP', 'WAN1 DNS', 'WAN1 Static', 'WAN2 Status', 'WAN2 IP', 'WAN2 Gateway', 'WAN2 Public IP', 'WAN2 DNS', 'WAN2 Static', 'Cellular Status', 'Cellular IP', 'Cellular Provider', 'Cellular Public IP', 'Cellular Model', 'Cellular Connection', 'Performance']
  writer = csv.DictWriter(csv_file1, fieldnames=fieldnames, restval='', dialect=csvquoting)
  writer.writeheader()

  # Iterate through appliances
  for appliance in appliances:
    network = get_network(appliance['networkId'], networks)
    network_name = network['name']
    print('Looking into network ' + network_name)
    device_info = jsonload('networks/' + appliance['networkId'] + '/devices/' + appliance['serial'])
    # sometimes I encountered some devices WITHOUT a name,
    # and this produced an error when you access ['name'].
    # So i decided to use ['serial'] as fallback.
    if 'name' in device_info.keys():
      device_name = device_info['name']
    else:
      device_name = device_info['serial']
    try:
      perfscore = jsonload('networks/' + appliance['networkId'] + '/devices/' + appliance['serial'] + '/performance')['perfScore']
    except:
      perfscore = None
    print('Found appliance ' + device_name)
    uplinks_info = dict.fromkeys(['WAN1', 'WAN2', 'Cellular'])
    uplinks_info['WAN1'] = dict.fromkeys(['interface', 'status', 'ip', 'gateway', 'publicIp', 'dns', 'usingStaticIp'])
    uplinks_info['WAN2'] = dict.fromkeys(['interface', 'status', 'ip', 'gateway', 'publicIp', 'dns', 'usingStaticIp'])
    uplinks_info['Cellular'] = dict.fromkeys(['interface', 'status', 'ip', 'provider', 'publicIp', 'model', 'connectionType'])
    uplinks = jsonload('networks/' + appliance['networkId'] + '/devices/' + appliance['serial'] + '/uplink')
    for uplink in uplinks:
      if uplink['interface'] == 'WAN 1':
        for key in uplink.keys():
          uplinks_info['WAN1'][key] = str(uplink[key])
      elif uplink['interface'] == 'WAN 2':
        for key in uplink.keys():
          uplinks_info['WAN2'][key] = str(uplink[key])
      elif uplink['interface'] == 'Cellular':
        for key in uplink.keys():
          uplinks_info['Cellular'][key] = str(uplink[key])
    csvline = {
      'TimeZone':str(network['timeZone'])
      , 'Network': network_name
      , 'Device': device_name
      , 'Serial': appliance['serial']
      , 'MAC': appliance['mac']
      , 'Model': appliance['model']
      , 'firmware': device_info['firmware']
      , 'geolocation': "https://www.google.com/maps/@" + str(device_info['lat']) + "," + str(device_info['lng']) + ",15z"
      , 'WAN1 Status': uplinks_info['WAN1']['status']
      , 'WAN1 IP': uplinks_info['WAN1']['ip']
      , 'WAN1 Gateway': uplinks_info['WAN1']['gateway']
      , 'WAN1 Public IP': uplinks_info['WAN1']['publicIp']
      , 'WAN1 DNS': uplinks_info['WAN1']['dns']
      , 'WAN1 Static': uplinks_info['WAN1']['usingStaticIp']
      , 'WAN2 Status': uplinks_info['WAN2']['status']
      , 'WAN2 IP': uplinks_info['WAN2']['ip']
      , 'WAN2 Gateway': uplinks_info['WAN2']['gateway']
      , 'WAN2 Public IP': uplinks_info['WAN2']['publicIp']
      , 'WAN2 DNS': uplinks_info['WAN2']['dns']
      , 'WAN2 Static': uplinks_info['WAN2']['usingStaticIp']
      , 'Cellular Status': uplinks_info['Cellular']['status']
      , 'Cellular IP': uplinks_info['Cellular']['ip']
      , 'Cellular Provider': uplinks_info['Cellular']['provider']
      , 'Cellular Public IP': uplinks_info['Cellular']['publicIp']
      , 'Cellular Model': uplinks_info['Cellular']['model']
      , 'Cellular Connection': uplinks_info['Cellular']['connectionType']
    }
    if perfscore != None:
      csvline['Performance'] = perfscore
    writer.writerow(csvline)
  csv_file1.close()


  # PLEASE REFER TO ABOVE COMMENTS FOR appliances for an explanation of code below: there are only minor differences.

  # Output CSV of all other devices' info
  csv_file2 = open(name + ' other devices - ' + str(today) + '.csv', 'w', encoding='utf-8')
  fieldnames = ['TimeZone', 'Network', 'Device', 'Serial', 'MAC', 'Model', 'Status', 'IP', 'Gateway', 'Public IP', 'DNS', 'VLAN', 'Static']
  writer = csv.DictWriter(csv_file2, fieldnames=fieldnames, restval='', dialect=csvquoting)
  writer.writeheader()

  # Iterate through all other devices
  for device in devices:
    network = get_network(device['networkId'], networks)
    network_name = network['name']
    print('Looking into network ' + network_name)
    device_info = jsonload('networks/' + device['networkId'] + '/devices/' + device['serial'])
    if 'name' in device_info.keys():
      device_name = device_info['name']
    else:
      device_name = device_info['serial']
    print('Found device ' + device_name)
    uplink_info = dict.fromkeys(['interface', 'status', 'ip', 'gateway', 'publicIp', 'dns', 'vlan', 'usingStaticIp'])
    uplink = jsonload('networks/' + device['networkId'] + '/devices/' + device['serial'] + '/uplink')
    
    # Blank uplink for devices that are down or meshed APs
    if uplink == []:
      continue
    # All other devices have single uplink
    else:
      uplink = uplink[0]
    for key in uplink.keys():
      uplink_info[key] = str(uplink[key])
    csvline = {
      'TimeZone':str(network['timeZone'])
      , 'Network': network_name
      , 'Device': device_name
      , 'Serial': device['serial']
      , 'MAC': device['mac']
      , 'Model': device['model']
      , 'Status': uplink_info['status']
      , 'IP': uplink_info['ip']
      , 'Gateway': uplink_info['gateway']
      , 'Public IP': uplink_info['publicIp']
      , 'DNS': uplink_info['dns']
      , 'VLAN': uplink_info['vlan']
      , 'Static': uplink_info['usingStaticIp']
    }
    writer.writerow(csvline)
  csv_file2.close()
