#!/usr/bin/python
"""
Author: JP Meijers
Date: 2017-02-26
Based on: https://github.com/rayozzie/ttn-resin-gateway-rpi/blob/master/run.sh
"""
import os
import os.path
import sys
import urllib2
import time
import uuid
import json
import subprocess
try:
  import urlparse
except:
  import urllib.parse as urlparse
try:
  import RPi.GPIO as GPIO
except RuntimeError:
  print("Error importing RPi.GPIO!  This is probably because you need superuser privileges.  You can achieve this by using 'sudo' to run your script")

GWID_PREFIX="FFFE"

if not os.path.exists("mp_pkt_fwd"):
  print ("ERROR: gateway executable not found. Is it built yet?")
  sys.exit(0)

if os.environ.get('HALT') != None:
  print ("*** HALT asserted - exiting ***")
  sys.exit(0)

# Show info about the machine we're running on
print ("*** Resin Machine Info:")
print ("*** Type: "+str(os.environ.get('RESIN_MACHINE_NAME')))
print ("*** Arch: "+str(os.environ.get('RESIN_ARCH')))

if os.environ.get("RESIN_HOST_CONFIG_core_freq")!=None:
  print ("*** Core freq: "+str(os.environ.get('RESIN_HOST_CONFIG_core_freq')))

if os.environ.get("RESIN_HOST_CONFIG_dtoverlay")!=None:
  print ("*** UART mode: "+str(os.environ.get('RESIN_HOST_CONFIG_dtoverlay')))

# Check if we have a configuration for Cayenne.
if os.environ.get("CAYENNE_MONITOR_SCRIPT")!=None:
  print ("*** Enabling Cayenne monitoring ")
  try:
    cayenne_url = 'https://cayenne.mydevices.com/dl/'+os.environ.get("CAYENNE_MONITOR_SCRIPT")
    print ("Downloading script from "+cayenne_url)
    req = urllib2.Request(cayenne_url)
    response = urllib2.urlopen(req, timeout=30)
    cayenne_response = response.read()
    # Write content to file
    tmp_file ="/tmp/"+os.environ.get("CAYENNE_MONITOR_SCRIPT")
    f = open( tmp_file, 'w' )
    f.write( cayenne_response )
    f.close()
    # Execute script
    print ("Executing script from "+tmp_file)
    subprocess.call(["bash", tmp_file, "-v"])
  except urllib2.URLError as err: 
    print ("Unable to fetch configuration from Cayenne. Is your CAYENNE_MONITOR_SCRIPT correct?")


# Check if the correct environment variables are set

print ("*******************")
print ("*** Configuration:")
print ("*******************")

if os.environ.get("GW_ID")==None:
  print ("ERROR: GW_ID required")
  print ("See https://www.thethingsnetwork.org/docs/gateways/registration.html#via-gateway-connector")
  sys.exit(0)

if os.environ.get("GW_KEY")==None:
  print ("ERROR: GW_KEY required")
  print ("See https://www.thethingsnetwork.org/docs/gateways/registration.html#via-gateway-connector")
  sys.exit(0)

# The FFFE should be inserted in the middle (so xxxxxxFFFExxxxxx)
my_eui = format(uuid.getnode(), '012x')
my_eui = my_eui[:6]+GWID_PREFIX+my_eui[6:]
my_eui = my_eui.upper()

print ("Gateway ID:\t"+os.environ.get("GW_ID"))
print ("Gateway EUI:\t"+my_eui)
print ("Gateway Key:\t"+os.environ.get("GW_KEY"))
print ("Has hardware GPS:\t"+str(os.getenv('GW_GPS', False)))
print ("Hardware GPS port:\t"+os.getenv('GW_GPS_PORT', "/dev/ttyAMA0"))


print ("*******************")
print ("*** Fetching config from TTN account server")
print ("*******************")

# Define default configs
description = ""
placement = ""
latitude = os.getenv('GW_REF_LATITUDE', 0)
longitude = os.getenv('GW_REF_LONGITUDE', 0)
altitude = os.getenv('GW_REF_ALTITUDE', 0)
frequency_plan_url = "https://account.thethingsnetwork.org/api/v2/frequency-plans/EU_863_870"

# Fetch config from TTN if TTN is enabled
if(os.getenv('SERVER_TTN', True)):
  # Fetch the URL, if it fails try 30 seconds later again.
  config_response = ""
  try:
    req = urllib2.Request('https://account.thethingsnetwork.org/gateways/'+os.environ.get("GW_ID"))
    req.add_header('Authorization', 'Key '+os.environ.get("GW_KEY"))
    response = urllib2.urlopen(req, timeout=30)
    config_response = response.read()
  except urllib2.URLError as err: 
    print ("Unable to fetch configuration from TTN. Are your GW_ID and GW_KEY correct?")
    sys.exit(0)

  # Parse config
  ttn_config = {}
  try:
    ttn_config = json.loads(config_response)
  except:
    print ("Unable to parse configuration from TTN")
    sys.exit(0)

  frequency_plan = ttn_config.get('frequency_plan', "EU_863_870")
  frequency_plan_url = ttn_config.get('frequency_plan_url', "https://account.thethingsnetwork.org/api/v2/frequency-plans/EU_863_870")

  if "router" in ttn_config:
    router = ttn_config['router'].get('mqtt_address', "mqtt://router.dev.thethings.network:1883")
    router = urlparse.urlparse(router)
    router = router.hostname # mp_pkt_fwd only wants the hostname, not the protocol and port
  else:
    router = "router.dev.thethings.network"

  if "attributes" in ttn_config:
    description = ttn_config['attributes'].get('description', "")
    placement = ttn_config['attributes'].get('placement', "unknown")

  if "antenna_location" in ttn_config:
    latitude = ttn_config['antenna_location'].get('latitude', 0)
    longitude = ttn_config['antenna_location'].get('longitude', 0)
    altitude = ttn_config['antenna_location'].get('altitude', 0)

  fallback_routers = []
  if "fallback_routers" in ttn_config:
    for fb_router in ttn_config["fallback_routers"]:
      if "mqtt_address" in fb_router:
        fallback_routers.append(fb_router["mqtt_address"])


  print ("Router:\t\t\t"+router)
  print ("Frequency plan:\t\t"+frequency_plan)
  print ("Frequency plan url:\t"+frequency_plan_url)
  print ("Gateway description:\t"+description)
  print ("Gateway placement:\t"+placement)
  print ("Latitude:\t\t"+str(latitude))
  print ("Longitude:\t\t"+str(longitude))
  print ("Altitude:\t\t"+str(altitude))
  print ("")
  print ("Fallback routers:")
  for fb_router in fallback_routers:
    print ("\t"+fb_router)
# Done fetching config from TTN


# Retrieve global_conf
global_conf = ""
try:
  response = urllib2.urlopen(frequency_plan_url, timeout=30)
  global_conf = response.read()
except urllib2.URLError as err: 
  print ("Unable to fetch global conf from Github")
  sys.exit(0)

# Write global_coonf
with open('global_conf.json', 'w') as the_file:
  the_file.write(global_conf)


# Build local_conf
gateway_conf = {}
gateway_conf['gateway_ID'] = my_eui
gateway_conf['contact_email'] = os.getenv('GW_CONTACT_EMAIL', "")
gateway_conf['description'] = description

# Use hardware GPS
if(os.getenv('GW_GPS', False)==True):
  print ("Using real GPS")
  gateway_conf['gps'] = True
  gateway_conf['fake_gps'] = False
  gateway_conf['gps_tty_path'] = os.getenv('GW_GPS_PORT', "/dev/ttyAMA0")
# Use fake GPS with coordinates from TTN
elif(os.getenv('GW_GPS', False)==False and latitude!=0 and longitude!=0):
  print ("Using fake GPS")
  gateway_conf['gps'] = True
  gateway_conf['fake_gps'] = True
  gateway_conf['ref_latitude'] = latitude
  gateway_conf['ref_longitude'] = longitude
  gateway_conf['ref_altitude'] = altitude
# No GPS coordinates
else:
  print ("Not sending coordinates")
  gateway_conf['gps'] = False
  gateway_conf['fake_gps'] = False


# Add server configuration
gateway_conf['servers'] = []

# Add TTN server
if(os.getenv('SERVER_TTN', True)):
  server = {}
  server['serv_type'] = "ttn"
  server['server_address'] = router
  server['server_fallbacks'] = fallback_routers
  server['serv_gw_id'] = os.environ.get("GW_ID")
  server['serv_gw_key'] = os.environ.get("GW_KEY")
  server['serv_enabled'] = True
  gateway_conf['servers'].append(server)

# Add up to 3 additional servers
if(os.getenv('SERVER_1_ENABLED', False)):
  server = {}
  if(os.getenv('SERVER_1_TYPE', "semtech")=="ttn"):
    server['serv_type'] = "ttn"
  server['server_address'] = os.environ.get("SERVER_1_ADDRESS")
  server['serv_port_up'] = os.environ.get("SERVER_1_PORTUP")
  server['serv_port_down'] = os.environ.get("SERVER_1_PORTDOWN")
  server['serv_gw_id'] = os.environ.get("SERVER_1_GWID")
  server['serv_gw_key'] = os.environ.get("SERVER_1_GWKEY")
  if(os.getenv('SERVER_1_ENABLED', "false")=="true"):
    server['serv_enabled'] = True
  else:
    server['serv_enabled'] = False
  if(os.getenv('SERVER_1_DOWNLINK', "false")=="true"):
    server['serv_down_enabled'] = True
  else:
    server['serv_down_enabled'] = False
  gateway_conf['servers'].append(server)

if(os.getenv('SERVER_2_ENABLED', False)):
  server = {}
  if(os.getenv('SERVER_2_TYPE', "semtech")=="ttn"):
    server['serv_type'] = "ttn"
  server['server_address'] = os.environ.get("SERVER_2_ADDRESS")
  server['serv_port_up'] = os.environ.get("SERVER_2_PORTUP")
  server['serv_port_down'] = os.environ.get("SERVER_2_PORTDOWN")
  server['serv_gw_id'] = os.environ.get("SERVER_2_GWID")
  server['serv_gw_key'] = os.environ.get("SERVER_2_GWKEY")
  if(os.getenv('SERVER_2_ENABLED', "false")=="true"):
    server['serv_enabled'] = True
  else:
    server['serv_enabled'] = False
  if(os.getenv('SERVER_2_DOWNLINK', "false")=="true"):
    server['serv_down_enabled'] = True
  else:
    server['serv_down_enabled'] = False
  gateway_conf['servers'].append(server)

if(os.getenv('SERVER_3_ENABLED', False)):
  server = {}
  if(os.getenv('SERVER_3_TYPE', "semtech")=="ttn"):
    server['serv_type'] = "ttn"
  server['server_address'] = os.environ.get("SERVER_3_ADDRESS")
  server['serv_port_up'] = os.environ.get("SERVER_3_PORTUP")
  server['serv_port_down'] = os.environ.get("SERVER_3_PORTDOWN")
  server['serv_gw_id'] = os.environ.get("SERVER_3_GWID")
  server['serv_gw_key'] = os.environ.get("SERVER_3_GWKEY")
  if(os.getenv('SERVER_3_ENABLED', "false")=="true"):
    server['serv_enabled'] = True
  else:
    server['serv_enabled'] = False
  if(os.getenv('SERVER_3_DOWNLINK', "false")=="true"):
    server['serv_down_enabled'] = True
  else:
    server['serv_down_enabled'] = False
  
  gateway_conf['servers'].append(server)


# Now write the local_conf out to a file
# Write global_coonf
local_conf = {'gateway_conf': gateway_conf}
with open('local_conf.json', 'w') as the_file:
  the_file.write(json.dumps(local_conf, indent=4))

# Endless loop to reset and restart packet forwarder
while True:
  # Reset the gateway board - this only works for the Raspberry Pi.
  GPIO.setmode(GPIO.BOARD) # hardware pin numbers, just like gpio -1

  if (os.environ.get("GW_RESET_PIN")!=None):
    try:
      pin_number = int(os.environ.get("GW_RESET_PIN"))
      print ("[TTN Gateway]: Resetting concentrator on pin "+str(os.environ.get("GW_RESET_PIN")))
      GPIO.setup(pin_number, GPIO.OUT, initial=GPIO.LOW)
      GPIO.output(pin_number, 0)
      time.sleep(0.1)
      GPIO.output(pin_number, 1)
      time.sleep(0.1)
      GPIO.output(pin_number, 0)
      time.sleep(0.1)
      GPIO.input(pin_number)
      GPIO.cleanup(pin_number)
    except ValueError:
      print ("Can't interpret "+os.environ.get("GW_RESET_PIN")+" as a valid pin number.")

  else:
    print ("[TTN Gateway]: Resetting concentrator on default pin 22.")
    GPIO.setup(22, GPIO.OUT, initial=GPIO.LOW)
    GPIO.output(22, 0)
    time.sleep(0.1)
    GPIO.output(22, 1)
    time.sleep(0.1)
    GPIO.output(22, 0)
    time.sleep(0.1)
    GPIO.input(22)
    GPIO.cleanup(22)

  # Start forwarder
  subprocess.call(["./mp_pkt_fwd"])
  time.sleep(15)
