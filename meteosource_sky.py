import os
import time
import math
import requests
import json
import ephem
import paho.mqtt.client as mqtt
from datetime import datetime
import pytz

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
    new_moon_ref = datetime(2000, 1, 6, 18, 14, tzinfo=pytz.utc)
    synodic_month = 29.530588853
    now = datetime.now(pytz.utc)
    days = (now - new_moon_ref).total_seconds() / 86400.0
    phase = (days % synodic_month) / synodic_month
    return (1 - math.cos(phase * 2 * math.pi)) / 2

def get_weather_and_turbidity():
    clouds = 0
    turbidity = 5.0
    is_stormy = False
    
    if not METEOSOURCE_API_KEY:
        return clouds, turbidity, is_stormy

    weather_url = f"https://www.meteosource.com/api/v1/free/point?lat={LAT}&lon={LON}&sections=current&key={METEOSOURCE_API_KEY}"
    try:
        response = requests.get(weather_url, timeout=10)
        if response.status_code == 200:
            summary = response.json().get("current", {}).get("summary", "").lower()
            
            if "thunder" in summary or "storm" in summary:
                is_stormy = True
                clouds = 100
            elif "clear" in summary: clouds = 0
            elif "mostly clear" in summary: clouds = 20
            elif "partly cloudy" in summary: clouds = 50
            elif "mostly cloudy" in summary: clouds = 80
            elif "overcast" in summary or "cloudy" in summary: clouds = 100
            else: clouds = 30
    except Exception as e:
        print(f"Failed to fetch weather: {e}")
        
    return clouds, turbidity, is_stormy

def get_solar_altitude():
    observer = ephem.Observer()
    observer.lat, observer.lon = str(LAT), str(LON)
    observer.date = datetime.now(pytz.utc)
    sun = ephem.Sun()
    sun.compute(observer)
    return math.degrees(sun.alt)

def calculate_base_day_colors(altitude_deg, clouds, turbidity):
    c = clouds / 100.0
# NEW Full-Range Keyframes capped at 75% peak PWM
    keys = [
        (-20, 35,  45,  60,  0),     
        (0,   150, 90,  100, 0),     
        (10,  255, 166, 0,   10),     
        (35,  255, 215, 180, 16),    
        (55,  255, 220, 180, 32),   
        (90,  255, 220, 180, 64)    # Full Noon: Capped at ~75% brightness (190)
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

    dim = 1.0 - (c * 0.5)
    r *= dim; g *= dim; b *= dim

    r += (turbidity * 3.5)
    g += (turbidity * 2.5)
    b -= (turbidity * 1.5)

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
        clouds, turbidity, is_stormy = get_weather_and_turbidity()
        moon = get_moon_illumination()
        
        # --- LOGIC ROUTER ---
        if alt <= -6:
            phase, col1, col2, col3, pwm, fx, sx, ix = night_effects.get_night_payload(moon, clouds, is_stormy)
        else:
            r, g, b, base_pwm, base_phase = calculate_base_day_colors(alt, clouds, turbidity)
            phase, col1, col2, col3, pwm, fx, sx, ix = day_effects.get_day_payload(r, g, b, base_pwm, clouds, base_phase, is_stormy)
        
        # ----------------------------------------------------
        # --- EXPANSION ZONE: SIDE & BUBBLER LEDS ---
        # ----------------------------------------------------
        # Default behavior: smoothly mirror the main sky
        exp_col1, exp_col2, exp_col3 = col1, col2, col3
        exp_fx, exp_sx, exp_ix = fx, sx, ix

        # The Silent "Heat Lightning" override for storms
        if is_stormy:
            exp_fx = 43  # Lightning Effect
            exp_sx = 25  # Extremely slow, lazy frequency
            exp_ix = 80  # Soft fade, no sharp strobing
            
            # Faint, glowing indigo for the ambient/bubbler strikes
            exp_col1 = [25, 35, 60, 0] 
            # Very dark background so it blends into the gloomy storm
            exp_col2 = [0, 0, 1, 0]    
            exp_col3 = [0, 0, 0, 0]

        # ----------------------------------------------------
        
        payload = {
            "on": True,
            "bri": 255, # Master brightness stays maxed out
            "transition": 30, 
            "seg": [
                {
                    "id": 0, # Main Sky RGB
                    "col": [col1, col2, col3], 
                    "fx": fx, "sx": sx, "ix": ix, "pal": 0
                },
                {
                    "id": 1, # Main PWM White
                    "bri": pwm,  # <-- PWM now controls the Segment Brightness slider directly!
                    "col": [[235, 235, 235, 235]], # <-- Locked to ebebebeb
                    "fx": 0 
                },
                {
                    "id": 2, # Left RGB (3px)
                    "col": [exp_col1, exp_col2, exp_col3], 
                    "fx": exp_fx, "sx": exp_sx, "ix": exp_ix, "pal": 0
                },
                {
                    "id": 3, # Right RGB (3px)
                    "col": [exp_col1, exp_col2, exp_col3], 
                    "fx": exp_fx, "sx": exp_sx, "ix": exp_ix, "pal": 0
                },
                {
                    "id": 4, # Bubbler RGB (4px)
                    "col": [exp_col1, exp_col2, exp_col3], 
                    "fx": exp_fx, "sx": exp_sx, "ix": exp_ix, "pal": 0
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
