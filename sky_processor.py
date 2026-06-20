import os
import math
import requests
import json
from datetime import datetime
import pytz
from suncalc import get_position
import paho.mqtt.client as mqtt

WEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

# Fixed: Proper MQTT Broker URL without needing sed replacements
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "joe33143/wled-sky/api"

LAT = 25.3176                     
LON = 83.0062                     

def get_realtime_turbidity():
    # Fixed: Standard 4-space indentation and corrected the OpenWeather API endpoint
    url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={LAT}&lon={LON}&appid={WEATHER_API_KEY}"
    try:
        response = requests.get(url, timeout=5).json()
        components = response['list'][0]['components'] # Note: 'list' usually contains an array in this API
        pm10 = components.get('pm10', 20)
        no2 = components.get('no2', 15)
        
        calculated_turbidity = 2.0 + (pm10 / 12.0) + (no2 / 8.0)
        return min(15.0, max(2.0, calculated_turbidity))
    except Exception as e:
        print(f"Air Pollution API fallback used. Error: {e}")
        return 5.0  # Balanced default daytime dust level for Varanasi

def calculate_sky_rgb(turbidity):
    now = datetime.now(pytz.utc)
    pos = get_position(now, LON, LAT)
    altitude_deg = math.degrees(pos['altitude'])
    
    # Nighttime fallback
    if altitude_deg <= -6:
        return [0, 0, 15]
            
    if altitude_deg > 12:
        # Re-tuned daylight constants: Higher Red and Green to remove the bluish tint
        r = int(235 + (turbidity * 1.0))
        g = int(240 + (turbidity * 0.5))
        b = int(255 - (turbidity * 4.5))
    else:
        # Golden hour positioning
        factor = (altitude_deg + 6) / 18.0  
        r = 255
        g = int(70 + (factor * 110) + (turbidity * 4))
        b = int(20 + (factor * 60) - (turbidity * 2))
            
    return [max(0, min(255, x)) for x in (r, g, b)]

def main():
    global MQTT_BROKER
    
    # Sanitizes the broker string if GitHub runs an old configuration block
    if "://" in MQTT_BROKER or not MQTT_BROKER or MQTT_BROKER == "://hivemq.com":
        MQTT_BROKER = "://hivemq.com"

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
    
    print(f"Connecting to Public HiveMQ at {MQTT_BROKER}...")
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        
        print(f"Publishing to topic: {MQTT_TOPIC}")
        info = client.publish(MQTT_TOPIC, json.dumps(wled_payload), qos=1)
        info.wait_for_publish() 
        
        client.loop_stop()
        client.disconnect()
        print(f"Successfully sent data. Turbidity: {turbidity:.2f} -> RGB: {rgb}")
    except Exception as e:
        print(f"MQTT Connection failed: {e}")

if __name__ == "__main__":
    main()
