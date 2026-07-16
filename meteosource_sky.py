import os
import time
import math
import requests
import json
import ephem
import paho.mqtt.client as mqtt
from datetime import datetime
import pytz

# --- GLOBALS & CONFIG ---
METEOSOURCE_API_KEY = os.getenv("METEOSOURCE_API_KEY")

MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "joe33143/wled-sky/api"
LAT = 25.3176
LON = 83.0062

# Helper: Linear Interpolation
def lerp(a, b, t):
    return a + (b - a) * t

def get_weather_and_turbidity():
    """Fetches real-time cloud data from Meteosource and applies turbidity baseline"""
    clouds = 0
    turbidity = 5.0  # Lock to baseline for testing since free tier lacks AQI data
    
    if not METEOSOURCE_API_KEY:
        print("Warning: METEOSOURCE_API_KEY environment variable missing. Defaulting to 0% clouds.")
        return clouds, turbidity

    weather_url = f"https://www.meteosource.com/api/v1/free/point?lat={LAT}&lon={LON}&sections=current&key={METEOSOURCE_API_KEY}"
    
    try:
        response = requests.get(weather_url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # Meteosource Free returns strings like "overcast", "clear", etc. in summary
            # or numerical maps. We target standard cloud parsing:
            summary = data.get("current", {}).get("summary", "").lower()
            
            # Map strings to clean percentage blocks safely
            if "clear" in summary:
                clouds = 0
            elif "mostly clear" in summary:
                clouds = 20
            elif "partly cloudy" in summary:
                clouds = 50
            elif "mostly cloudy" in summary:
                clouds = 80
            elif "overcast" in summary or "cloudy" in summary:
                clouds = 100
            else:
                clouds = 30 # Safe default fallback
                
            print(f"Meteosource Live Weather: '{summary}' mapped to {clouds}% Cloud Cover")
        else:
            print(f"API Error: HTTP {response.status_code}. Using fallback.")
    except Exception as e:
        print(f"Failed to fetch weather: {e}")
        
    return clouds, turbidity

def get_solar_altitude():
    """Calculates true solar elevation angle relative to geography"""
    observer = ephem.Observer()
    observer.lat = str(LAT)
    observer.lon = str(LON)
    observer.date = datetime.now(pytz.utc)
    
    sun = ephem.Sun()
    sun.compute(observer)
    
    # Convert from radians to absolute degrees
    return math.degrees(sun.alt)

def calculate_sky_state(altitude_deg, clouds, turbidity, moon_factor=0.5):
    """Calibrated HTML engine translated cleanly to Python core math"""
    c = clouds / 100.0
    
    # Keyframes: [Altitude, R, G, B, PWM]
    keys = [
        (-20, 35,  45,  60,  0),     # Night
        (0,   80,  50,  60,  0),     # Twilight
        (10,  130, 80,  50,  0),     # Golden Hour
        (35,  200, 170, 150, 0),     # Morning Hold
        (55,  255, 220, 180, 108),   # Start Wakeup
        (90,  255, 220, 180, 118)    # Full Noon
    ]

    # Bound target finder
    k1, k2 = keys[0], keys[-1]
    for i in range(len(keys) - 1):
        if keys[i][0] <= altitude_deg <= keys[i+1][0]:
            k1 = keys[i]
            k2 = keys[i+1]
            break
            
    if altitude_deg < keys[0][0]: k1 = k2 = keys[0]
    elif altitude_deg > keys[-1][0]: k1 = k2 = keys[-1]

    t = 0.0 if k2[0] == k1[0] else max(0.0, min(1.0, (altitude_deg - k1[0]) / (k2[0] - k1[0])))

    r = lerp(k1[1], k2[1], t)
    g = lerp(k1[2], k2[2], t)
    b = lerp(k1[3], k2[3], t)
    pwm = lerp(k1[4], k2[4], t)

    # --- LUNAR OVERRIDE ---
    if altitude_deg <= -6:
        moon_ceiling = 0.08
        r = 4 + (moon_factor * 65 * moon_ceiling)
        g = 5 + (moon_factor * 68 * moon_ceiling)
        b = 7 + (moon_factor * 72 * moon_ceiling)

    # --- ATMOSPHERIC FILTERS ---
    dim = 1.0 - (c * 0.5)
    r *= dim; g *= dim; b *= dim

    # Dust Turbidity Vector
    r += (turbidity * 3.5)
    g += (turbidity * 2.5)
    b -= (turbidity * 1.5)

    # 12V PWM Engine Throttling
    pwm = pwm * (1.0 - (c * 0.1)) if altitude_deg > 35 else 0.0

    return (
        int(max(0, min(255, r))),
        int(max(0, min(255, g))),
        int(max(0, min(255, b))),
        int(max(0, min(255, pwm)))
    )

def main():
    # Setup MQTT Client using the updated V2 API to remove the deprecation warning
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        print(f"Connected to MQTT Broker ({MQTT_BROKER}:{MQTT_PORT})")
    except Exception as e:
        print(f"MQTT Connection failed: {e}. Exiting.")
        return

    # Mocking static moon phase for runtime validation
    current_moon = 0.5 

    try:
        # 1. Gather all environment input parameters
        alt = get_solar_altitude()
        clouds, turbidity = get_weather_and_turbidity()
        
        # 2. Process through engine
        r, g, b, pwm = calculate_sky_state(alt, clouds, turbidity, current_moon)
        
        # 3. Formulate the precise WLED JSON structure
        payload = {
            "on": True,
            "bri": 255,
            "transition": 30, # Smooth out network shifts over 3 seconds
            "seg": [
                {"id": 0, "col": [[r, g, b, 0]]},
                {"id": 1, "col": [[pwm, pwm, pwm, pwm]]}
            ]
        }
        
        # 4. Fire over the MQTT broker channel
        print(f"Publishing Alt: {alt:.2f}° | RGB: [{r},{g},{b}] | PWM: {pwm}")
        
        # We use publish and a brief loop call to ensure the network packet actually sends before the script quits
        client.publish(MQTT_TOPIC, json.dumps(payload), qos=1)
        client.loop(2) 
        
        print("Successfully synced to WLED. Shutting down one-shot script.")
        
    except Exception as e:
        print(f"Error during execution: {e}")
        
    finally:
        # Ensure we always disconnect cleanly
        client.disconnect()
# Force a blocking wait until the broker acknowledges the message receipt
        print(f"Publishing Alt: {alt:.2f}° | RGB: [{r},{g},{b}] | PWM: {pwm}")
        publish_result = client.publish(MQTT_TOPIC, json.dumps(payload), qos=1)
        
        # This blocks execution up to 10 seconds to ensure the network stack clears
        publish_result.wait_for_publish(timeout=10) 
        
        if publish_result.is_published():
            print("Broker Confirmed: Payload delivered successfully.")
        else:
            print("Network Error: Packet queued but broker rejected/dropped it.")
if __name__ == "__main__":
    main()
