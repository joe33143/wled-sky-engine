import os
import math
import requests
import json
from datetime import datetime
import pytz
from suncalc import get_position
import paho.mqtt.client as mqtt

WEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

MQTT_BROKER = "://hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "joe33143/wled-sky/api"

LAT = 25.3176                     
LON = 83.0062                     

def get_realtime_turbidity():
    # Corrected API endpoint structure
    url = f"http://openweathermap.org{LAT}&lon={LON}&appid={WEATHER_API_KEY}"
    try:
        response = requests.get(url, timeout=5).json()
        components = response['list'][0]['components']
        pm10 = components.get('pm10', 20)
        no2 = components.get('no2', 15)
        
        calculated_turbidity = 2.0 + (pm10 / 12.0) + (no2 / 8.0)
        return min(15.0, max(2.0, calculated_turbidity))
    except Exception as e:
        print(f"Air Pollution API fallback used. Error: {e}")
        return 6.0 

def calculate_sky_rgb(turbidity):
    now = datetime.now(pytz.utc)
    pos = get_position(now, LON, LAT)
    altitude_deg = math.degrees(pos['altitude'])
    
    if altitude_deg <= -6:
        return [0, 0, 15]
            
    if altitude_deg > 12:
        # Re-tuned values to counter the bluish tint during high sun hours
        r = int(220 + (turbidity * 2.0))
        g = int(235 + (turbidity * 1.0))
        b = int(255 - (turbidity * 5.0))
    else:
        factor = (altitude_deg + 6) / 18.0  
        r = 255
        g = int(70 + (factor * 90) + (turbidity * 4))
        b = int(20 + (factor * 60) - (turbidity * 2))
            
    return [max(0, min(255, x)) for x in (r, g, b)]

def main():
    if not WEATHER_API_KEY:
        print("Error: Missing OpenWeather API Key.")
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

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "VaranasiSky_Publisher_Public")
    except AttributeError:
        client = mqtt.Client("VaranasiSky_Publisher_Public")
    
    print("Connecting to Public HiveMQ...")
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    
    print(f"Publishing to topic: {MQTT_TOPIC}")
    info = client.publish(MQTT_TOPIC, json.dumps(wled_payload), qos=1)
    info.wait_for_publish() 
    
    client.loop_stop()
    client.disconnect()
    print(f"Successfully sent data. Turbidity: {turbidity:.2f} -> RGB: {rgb}")

if __name__ == "__main__":
    main()
