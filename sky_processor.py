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

def get_weather_and_turbidity():
    """Pulls air pollution and cloud coverage data to calculate weather factor."""
    pollution_url = f"http://openweathermap.org{LAT}&lon={LON}&appid={WEATHER_API_KEY}"
    weather_url = f"http://openweathermap.org{LAT}&lon={LON}&appid={WEATHER_API_KEY}"
    
    turbidity = 5.0
    clouds = 0  # 0 to 100%
    
    # 1. Fetch Pollution Data
    try:
        res = requests.get(pollution_url, timeout=5).json()
        components = res['list'][0]['components']
        pm10 = components.get('pm10', 20)
        no2 = components.get('no2', 15)
        turbidity = min(15.0, max(2.0, 2.0 + (pm10 / 12.0) + (no2 / 8.0)))
    except Exception as e:
        print(f"Air Pollution API fallback used: {e}")

    # 2. Fetch Cloud Coverage Data
    try:
        res = requests.get(weather_url, timeout=5).json()
        clouds = res.get('clouds', {}).get('all', 0)
        print(f"Current weather metrics -> Clouds: {clouds}%, Dust Turbidity: {turbidity:.2f}")
    except Exception as e:
        print(f"Weather API fallback used: {e}")
        
    return turbidity, clouds

def calculate_sky_rgb(turbidity, clouds):
    now = datetime.now(pytz.utc)
    pos = get_position(now, LON, LAT)
    altitude_deg = math.degrees(pos['altitude'])
    
    # Nighttime: Very dim deep blue
    if altitude_deg <= -6:
        return [0, 0, 15]
            
    if altitude_deg > 12:
        # --- DAYTIME CALIBRATION MATRIX ---
        # Base calibration to balance out the strip's native blue tint (Hardware correction)
        # Bringing Red and Green closer to maximum, while lowering Blue creates a balanced pure white.
        r = int(255)
        g = int(240 + (turbidity * 1.0))
        b = int(200 - (turbidity * 3.0))  # Suppressed blue base to counteract LED tint
        
        # --- CLOUD LAYER COMPENSATION ---
        # If clouds are high, shift colors towards an overcast, cooler gray-white and dim down
        if clouds > 25:
            cloud_factor = (clouds - 25) / 75.0  # Scale effect from 0.0 to 1.0
            r = int(r * (1.0 - (cloud_factor * 0.25)))
            g = int(g * (1.0 - (cloud_factor * 0.20)))
            b = int(b * (1.0 - (cloud_factor * 0.10)))  # Leave blue higher to simulate gray overcast sky
    else:
        # Golden Hour Position (Sunrise / Sunset)
        factor = (altitude_deg + 6) / 18.0  
        r = 255
        g = int(80 + (factor * 110) + (turbidity * 4))
        b = int(20 + (factor * 40) - (turbidity * 2))
        
        # Dim slightly if cloudy during sunset
        if clouds > 50:
            r = int(r * 0.7)
            g = int(g * 0.6)
            b = int(b * 0.6)
            
    return [max(0, min(255, x)) for x in (r, g, b)]

def main():
    if not WEATHER_API_KEY:
        print("Error: Missing OpenWeather API Key.")
        return

    turbidity, clouds = get_weather_and_turbidity()
    rgb = calculate_sky_rgb(turbidity, clouds)
    
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
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        
        print(f"Publishing to topic: {MQTT_TOPIC}")
        info = client.publish(MQTT_TOPIC, json.dumps(wled_payload), qos=1)
        info.wait_for_publish() 
        
        client.loop_stop()
        client.disconnect()
        print(f"Successfully sent data. RGB Result: {rgb}")
    except Exception as e:
        print(f"MQTT Operation failed: {e}")

if __name__ == "__main__":
    main()
