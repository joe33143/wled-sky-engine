import os
import time
import math
import requests
import json
import ephem
import paho.mqtt.client as mqtt
from datetime import datetime
import pytz

# Import your new effect modules
import night_effects
import day_effects

# --- GLOBALS & CONFIG ---
METEOSOURCE_API_KEY = os.getenv("METEOSOURCE_API_KEY")

MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "joe33143/wled-sky/api"
LAT = 25.3176
LON = 83.0062

def lerp(a, b, t):
    return a + (b - a) * t

def get_moon_illumination():
    """Calculates the current physical moon phase (0.0 to 1.0)"""
    new_moon_ref = datetime(2000, 1, 6, 18, 14, tzinfo=pytz.utc)
    synodic_month = 29.530588853
    now = datetime.now(pytz.utc)
    days = (now - new_moon_ref).total_seconds() / 86400.0
    phase = (days % synodic_month) / synodic_month
    
    # 0 = New Moon, 1.0 = Full Moon
    return (1 - math.cos(phase * 2 * math.pi)) / 2

def get_weather_and_turbidity():
    """Fetches real-time cloud data from Meteosource"""
    clouds = 0
    turbidity = 5.0
    
    if not METEOSOURCE_API_KEY:
        return clouds, turbidity

    weather_url = f"https://www.meteosource.com/api/v1/free/point?lat={LAT}&lon={LON}&sections=current&key={METEOSOURCE_API_KEY}"
    try:
        response = requests.get(weather_url, timeout=10)
        if response.status_code == 200:
            summary = response.json().get("current", {}).get("summary", "").lower()
            if "clear" in summary: clouds = 0
            elif "mostly clear" in summary: clouds = 20
            elif "partly cloudy" in summary: clouds = 50
            elif "mostly cloudy" in summary: clouds = 80
            elif "overcast" in summary or "cloudy" in summary: clouds = 100
            else: clouds = 30
    except Exception as e:
        print(f"Failed to fetch weather: {e}")
        
    return clouds, turbidity

def get_solar_altitude():
    """Calculates true solar elevation angle"""
    observer = ephem.Observer()
    observer.lat, observer.lon = str(LAT), str(LON)
    observer.date = datetime.now(pytz.utc)
    sun = ephem.Sun()
    sun.compute(observer)
    return math.degrees(sun.alt)

def calculate_base_day_colors(altitude_deg, clouds, turbidity):
    """Handles the LERP math for daytime phases"""
    c = clouds / 100.0
    
    keys = [
        (-20, 35,  45,  60,  0),
        (0,   80,  50,  60,  0),
        (10,  130, 80,  50,  0),
        (35,  200, 170, 150, 0),
        (55,  255, 220, 180, 108),
        (90,  255, 220, 180, 118)
    ]

    k1, k2 = keys[0], keys[-1]
    for i in range(len(keys) - 1):
        if keys[i][0] <= altitude_deg <= keys[i+1][0]:
            k1, k2 = keys[i], keys[i+1]
            break
            
    if altitude_deg < keys[0][0]: k1 = k2 = keys[0]
    elif altitude_deg > keys[-1][0]: k1 = k2 = keys[-1]

    t = 0.0 if k2[0] == k1[0] else max(0.0, min(1.0, (altitude_deg - k1[0]) / (k2[0] - k1[0])))

    r = lerp(k1[1], k2[1], t)
    g = lerp(k1[2], k2[2], t)
    b = lerp(k1[3], k2[3], t)
    pwm = lerp(k1[4], k2[4], t)

    phase_name = "Low Sun / Horizon" if altitude_deg < 35 else "Daytime"

    # Apply Cloud Dimming
    dim = 1.0 - (c * 0.5)
    r *= dim; g *= dim; b *= dim

    # Apply Warm Haze (Turbidity)
    r += (turbidity * 3.5)
    g += (turbidity * 2.5)
    b -= (turbidity * 1.5)

    # PWM Cloud Throttling
    pwm = pwm * (1.0 - (c * 0.1)) if altitude_deg > 35 else 0.0

    r = int(max(0, min(255, r)))
    g = int(max(0, min(255, g)))
    b = int(max(0, min(255, b)))
    pwm = int(max(0, min(255, pwm)))

    return r, g, b, pwm, phase_name

def main():
    client_id = f"joe33143_sky_{int(time.time())}"
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start() 
    except Exception as e:
        print(f"MQTT Connection failed: {e}")
        return

    try:
        alt = get_solar_altitude()
        clouds, turbidity = get_weather_and_turbidity()
        moon = get_moon_illumination()
        
        # --- LOGIC ROUTER ---
        # If the sun is below -6, route to the night animation engine.
        # Otherwise, calculate daytime LERP and route to the day animation engine.
        if alt <= -6:
            phase, col1, col2, col3, pwm, fx, sx, ix = night_effects.get_night_payload(moon, clouds)
        else:
            r, g, b, base_pwm, base_phase = calculate_base_day_colors(alt, clouds, turbidity)
            phase, col1, col2, col3, pwm, fx, sx, ix = day_effects.get_day_payload(r, g, b, base_pwm, clouds, base_phase)
        
        payload = {
            "on": True,
            "bri": 255,
            "transition": 30, 
            "seg": [
                {
                    "id": 0, 
                    "col": [col1, col2, col3], 
                    "fx": fx, "sx": sx, "ix": ix, "pal": 0
                },
                {
                    "id": 1, 
                    "col": [[pwm, pwm, pwm, pwm]], 
                    "fx": 0 # The PWM Strip MUST stay solid!
                }
            ]
        }
        
        print(f"[{phase}] -> FX: {fx} | Base RGB: {col1[:3]} | PWM: {pwm}")
        publish_result = client.publish(MQTT_TOPIC, json.dumps(payload), qos=1)
        publish_result.wait_for_publish(timeout=10) 
        
    except Exception as e:
        print(f"Error during execution: {e}")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
