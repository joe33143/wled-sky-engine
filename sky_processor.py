import os
import math
import requests
import json
import ssl
from datetime import datetime
import pytz
from suncalc import get_position
import paho.mqtt.client as mqtt

# --- ENVIRONMENT VARIABLES FROM GITHUB SECRETS ---
WEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

# New HiveMQ Secrets (We will set these up next)
HIVEMQ_HOST = os.getenv("HIVEMQ_HOST")         
HIVEMQ_USERNAME = os.getenv("HIVEMQ_USERNAME")
HIVEMQ_PASSWORD = os.getenv("HIVEMQ_PASSWORD")

# HiveMQ Cloud strictly uses Port 8883 for secure connections
MQTT_PORT = 8883
# Clean, simple topic! No groups required.
MQTT_TOPIC = "joe33143/wled-sky/api"

LAT = 25.3176                     
LON = 83.0062                     

def get_realtime_turbidity():
    url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={LAT}&lon={LON}&appid={WEATHER_API_KEY}"
    try:
        response = requests.get(url, timeout=5).json()
        components = response['list'][0]['components']
        pm10 = components.get('pm10', 20)
        no2 = components.get('no2', 15)
        calculated_turbidity = 2.0 + (pm10 / 30.0) + (no2 / 20.0)
        return min(15.0, max(2.0, calculated_turbidity))
    except Exception as e:
        print(f"Air Pollution API fallback used. Error: {e}")
        return 5.0 

def calculate_sky_rgb(turbidity):
    now = datetime.now(pytz.utc)
    pos = get_position(now, LON, LAT)
    altitude_deg = math.degrees(pos['altitude'])
    
    if altitude_deg <= -6:
        return [0, 0, 15]
            
    if altitude_deg > 12:
        r = int(140 + (turbidity * 5))
        g = int(190 + (turbidity * 2))
        b = int(255 - (turbidity * 4))
    else:
        factor = (altitude_deg + 6) / 18.0  
        r = 255
        g = int(70 + (factor * 90) + (turbidity * 4))
        b = int(20 + (factor * 60) - (turbidity * 2))
            
    return [max(0, min(255, x)) for x in (r, g, b)]

def main():
    if not WEATHER_API_KEY or not HIVEMQ_HOST or not HIVEMQ_USERNAME or not HIVEMQ_PASSWORD:
        print("Error: Missing required environment secrets. Did you add the HiveMQ ones to GitHub?")
        return

    turbidity = get_realtime_turbidity()
    rgb = calculate_sky_rgb(turbidity)
    
    wled_payload = {
        "on": True,
        "bri": 255,
        "seg": [{
            "id": 1,
            "start": 0,
            "stop": 90,
            "col": [rgb] 
        }]
    }

    client = mqtt.Client(f"VaranasiSky_Publisher_{HIVEMQ_USERNAME}")
    client.username_pw_set(HIVEMQ_USERNAME, HIVEMQ_PASSWORD)
    
    # REQUIRED FOR HIVEMQ CLOUD: Enable SSL/TLS encryption
    client.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)
    
    print(f"Connecting to HiveMQ Cloud...")
    client.connect(HIVEMQ_HOST, MQTT_PORT, 60)
    client.loop_start()
    
    print(f"Publishing to topic: {MQTT_TOPIC}")
    info = client.publish(MQTT_TOPIC, json.dumps(wled_payload), qos=1)
    info.wait_for_publish() 
    
    client.loop_stop()
    client.disconnect()
    print(f"Successfully sent data. Turbidity: {turbidity:.2f} -> RGB: {rgb}")

if __name__ == "__main__":
    main()
