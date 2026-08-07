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
    r, g, b = rgb_list[0], rgb_list[1], rgb_list[2]
    if r == 0 and g == 0 and b == 0:
        return [0, 0, 0, 0]
    mn = min(r, g, b)
    mx = max(r, g, b)
    if mx == mn: 
        return [255, 255, 255, 0] 
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
    keys = [
        (-6,   35,  45,  75,   0),  
        (0,   120, 110, 140,  18),  
        (10,  190, 185, 205,  40),  
        (35,  240, 235, 235, 100),  
        (55,  255, 250, 245, 160),  
        (90,  255, 255, 255, 200)   
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
        
        ist_tz = pytz.timezone('Asia/Kolkata')
        now_ist = datetime.now(ist_tz)
        time_float = now_ist.hour + (now_ist.minute / 60.0)

        effective_alt = alt
        if alt <= 0 and (16.0 <= time_float < 21.0):
            effective_alt = 0

        if effective_alt <= -6:
            phase, col1, col2, col3, pwm, fx, sx, ix, pal = night_effects.get_night_payload(moon, clouds, is_stormy)
        else:
            r, g, b, base_pwm, base_phase = calculate_base_day_colors(effective_alt, clouds, turbidity)
            phase, col1, col2, col3, pwm, fx, sx, ix, pal = day_effects.get_day_payload(r, g, b, base_pwm, clouds, base_phase, is_stormy)

        # ----------------------------------------------------
        # --- VIVID BOOST (Always run now) ---
        # ----------------------------------------------------
        col1 = [min(255, int(c * 1.1)) for c in col1[:3]] + [0]
        col2 = [min(255, int(c * 1.8)) for c in col2[:3]] + [0]
        col3 = [min(255, int(c * 1.8)) for c in col3[:3]] + [0]

        # ----------------------------------------------------
        # --- EXPANSION ZONE: Tank Saturated Extension ---
        # ----------------------------------------------------
        exp_fx = 0  
        exp_sx = 128
        exp_ix = 128
        exp_pal = 0

        exp_col1 = get_saturated_color(col1)
        exp_col2 = get_saturated_color(col2)
        exp_col3 = get_saturated_color(col3)

        if is_stormy:
            exp_fx = 57  
            exp_sx = 220 
            exp_ix = 200  
            # Tank gets lightning too, but keeps saturated colors
            exp_col1 = get_saturated_color(col1)
            exp_col2 = get_saturated_color(col2)
            exp_col3 = [0, 0, 0, 0]
        elif "Rainy" in phase:
            exp_col1 = [106, 149, 255, 0]
            exp_col2 = [148, 148, 148, 0]

        # ----------------------------------------------------
        # --- THE CLOCK-BASED CEILING HANDOFF ---
        # ----------------------------------------------------
        wled_transition = 50
        rgb_multiplier = 1.0
        calculated_pwm = pwm

        if time_float < 7.0:
            pwm = 0
            rgb_multiplier = 1.0

        elif 7.0 <= time_float < 7.5:
            progress = (time_float - 7.0) / 0.5
            pwm = int(10 * progress)
            rgb_multiplier = 1.0
            phase += " [PRE-DAWN PWM FILL]"

        elif 7.5 <= time_float < 8.0:
            progress = (time_float - 7.5) / 0.5 
            pwm = int(10 + (calculated_pwm - 10) * progress)
            rgb_multiplier = 1.0 - progress
            wled_transition = 200 
            phase += " [MORNING HANDOFF]"

        elif 8.0 <= time_float < 17.0:
            if is_stormy:
                pwm = calculated_pwm 
                rgb_multiplier = 1.0
                phase += " [DAYTIME STORM - RGB Active]"
            elif clouds >= 30:
                pwm = calculated_pwm 
                rgb_multiplier = 1.0
                phase += " [DAYTIME CLOUDS - RGB Active]"
            else:
                pwm = calculated_pwm
                rgb_multiplier = 0.0
                fx = 0  
                phase += " [MAIN RGB OFF - Clear Sky]"

        elif 17.0 <= time_float < 18.0:
            progress = (time_float - 17.0) / 1.0
            pwm = int(calculated_pwm - ((calculated_pwm - 18) * progress))
            rgb_multiplier = progress
            wled_transition = 200
            phase += " [EVENING HANDOFF]"

        elif 18.0 <= time_float < 20.0:
            pwm = max(calculated_pwm, 18)
            rgb_multiplier = 1.0

        elif 20.0 <= time_float < 21.0:
            pwm = 0
            rgb_multiplier = 1.0
            if time_float < 20.25:
                wled_transition = 200
            phase += " [8PM PWM OFF]"

        else:
            pwm = 0
            rgb_multiplier = 1.0
            if 21.0 <= time_float < 21.25:
                wled_transition = 290

        # Apply multiplier uniformly to Main RGB
        col1 = [int(c * rgb_multiplier) for c in col1[:3]] + [0]
        col2 = [int(c * rgb_multiplier) for c in col2[:3]] + [0]
        col3 = [int(c * rgb_multiplier) for c in col3[:3]] + [0]

        # ----------------------------------------------------
        # --- SEGMENT 1 (PWM) CONFIGURATION ---
        # ----------------------------------------------------
        pwm_bri = pwm
        pwm_fx = 0
        pwm_sx = 128
        pwm_ix = 128
        pwm_col1 = [235, 235, 235, 235]
        pwm_col2 = [0, 0, 0, 0]

        if is_stormy:
            pwm_bri = 255 # Max segment brightness so flashes are violent
            pwm_fx = 57   # Lightning effect!
            pwm_sx = 220
            pwm_ix = 200
            # Flash color is bright white
            pwm_col1 = [255, 255, 255, 255]
            
            # Background scales between a floor of 15% (38) and a ceiling of 50% of calculated_pwm
            storm_bg = max(int(255 * 0.15), int(calculated_pwm * 0.50))
            pwm_col2 = [storm_bg, storm_bg, storm_bg, storm_bg]

        # ----------------------------------------------------
        
        payload = {
            "on": True,
            "bri": 255, 
            "transition": wled_transition, 
            "seg": [
                {
                    "id": 0, 
                    "col": [col1, col2, col3], 
                    "cct": 38,   
                    "fx": fx, "sx": sx, "ix": ix, "pal": pal 
                },
                {
                    "id": 1, 
                    "bri": pwm_bri, 
                    "col": [pwm_col1, pwm_col2, [0,0,0,0]], 
                    "cct": 127,  
                    "fx": pwm_fx,
                    "sx": pwm_sx,
                    "ix": pwm_ix
                },
                {
                    "id": 2, 
                    "col": [exp_col1, exp_col2, exp_col3], 
                    "cct": 127,  
                    "fx": exp_fx, "sx": exp_sx, "ix": exp_ix, "pal": exp_pal
                }
            ]
        }
        
        print(f"[{phase}] -> FX: {fx} | Base RGB: {col1[:3]} | PWM: {pwm} | Trans: {wled_transition/10}s")
        publish_result = client.publish(MQTT_TOPIC, json.dumps(payload), qos=1)
        publish_result.wait_for_publish(timeout=10) 
        
    except Exception as e:
        print(f"Error during execution: {e}")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
    
