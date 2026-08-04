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

def get_saturated_color(rgb_list):
    """Pushes an RGB color to 100% saturation while keeping its hue."""
    r, g, b = rgb_list[0], rgb_list[1], rgb_list[2]
    if r == 0 and g == 0 and b == 0:
        return [0, 0, 0, 0]
    
    mn = min(r, g, b)
    mx = max(r, g, b)
    if mx == mn: 
        return [255, 255, 255, 0] # Fallback if it's pure grey
    
    # Strip the white and scale the highest color to 255
    r_sat = int((r - mn) * 255 / (mx - mn))
    g_sat = int((g - mn) * 255 / (mx - mn))
    b_sat = int((b - mn) * 255 / (mx - mn))
    
    return [r_sat, g_sat, b_sat, 0]

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

    # --- SMOOTHED, NEUTRALIZED KEYFRAMES (High-PWM Edition) ---
    keys = [
        # (Alt, R,   G,   B,  PWM)
        (-6,   35,  45,  75,   0),  # Hand-off to Night Engine
        (0,   120, 110, 140,  18),  # Sunset/Sunrise 
        (10,  190, 185, 205,  40),  # Early Morning 
        (35,  240, 235, 235, 100),  # Mid-Morning 
        (55,  255, 250, 245, 160),  # Late Morning
        (90,  255, 255, 255, 200)   # Solar Noon (Max PWM)
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

    # Cloud Dimming
    dim = 1.0 - (c * 0.5)
    r *= dim; g *= dim; b *= dim

    # Dust/Pollution Scattering
    r += (turbidity * 3.5); g += (turbidity * 2.5); b -= (turbidity * 1.5)

    pwm = pwm * (1.0 - (c * 0.1)) 

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
            phase, col1, col2, col3, pwm, fx, sx, ix, pal = night_effects.get_night_payload(moon, clouds, is_stormy)
        else:
            r, g, b, base_pwm, base_phase = calculate_base_day_colors(alt, clouds, turbidity)
            phase, col1, col2, col3, pwm, fx, sx, ix, pal = day_effects.get_day_payload(r, g, b, base_pwm, clouds, base_phase, is_stormy)
        
        # ----------------------------------------------------
        # --- EVENING PWM OVERRIDE (Fades out by 10:30 PM) ---
        # ----------------------------------------------------
        ist_tz = pytz.timezone('Asia/Kolkata')
        now_ist = datetime.now(ist_tz)
        
        time_float = now_ist.hour + (now_ist.minute / 60.0)
        
        if 17.0 <= time_float <= 22.5:
            if time_float < 22.0:
                evening_pwm = 18
            else:
                fade_factor = (22.5 - time_float) / 0.5  
                evening_pwm = int(18 * fade_factor)
                
            pwm = max(pwm, evening_pwm)

        # ----------------------------------------------------
        # --- EXPANSION ZONE: 6-Pixel Saturated Extension ---
        # ----------------------------------------------------
        exp_fx = 0  
        exp_sx = 128
        exp_ix = 128
        exp_pal = 0

        # 1. Grab the colors for the tank bubbler BEFORE we turn the main RGB off
        exp_col1 = get_saturated_color(col1)
        exp_col2 = get_saturated_color(col2)
        exp_col3 = get_saturated_color(col3)

        if is_stormy:
            exp_fx = 57  
            exp_sx = 207 
            exp_ix = 129  
            exp_col1 = [106, 149, 255, 0] 
            exp_col2 = [112, 112, 112, 0]    
            exp_col3 = [0, 0, 0, 0]
            
        elif "Rainy" in phase:
            exp_col1 = [106, 149, 255, 0]
            exp_col2 = [148, 148, 148, 0]

        # ==========================================
        # POWER SAVING OVERRIDE: MAIN RGB OFF if PWM > 34
        # ==========================================
        # 2. Now that the tank has its saturated colors, we can kill the main ceiling RGB
        if pwm > 34 and not is_stormy:
            col1 = [0, 0, 0, 0]
            col2 = [0, 0, 0, 0]
            col3 = [0, 0, 0, 0]
            fx = 0  # Kill all animations on main strip
            phase += " [MAIN RGB DISABLED]"

        # ----------------------------------------------------

        payload = {
            "on": True,
            "bri": 255, 
            "transition": 30, 
            "seg": [
                {
                    "id": 0, # Main Sky RGB
                    "col": [col1, col2, col3], 
                    "cct": 38,   
                    "fx": fx, "sx": sx, "ix": ix, "pal": pal 
                },
                {
                    "id": 1, # Main PWM White
                    "bri": pwm, 
                    "col": [[235, 235, 235, 235]], 
                    "cct": 127,  
                    "fx": 0 
                },
                {
                    "id": 2, # Unified 6-Pixel Extension RGB
                    "col": [exp_col1, exp_col2, exp_col3], 
                    "cct": 127,  # Shifts the White Balance to the perfect middle
                    "fx": exp_fx, "sx": exp_sx, "ix": exp_ix, "pal": exp_pal
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
