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

        # Shift time so 1 AM to 5 AM are treated as 25.0 to 29.0.
        # This allows continuous linear math without breaking at midnight.
        adj_time = time_float if time_float >= 6.0 else time_float + 24.0

        effective_alt = alt
        if alt <= 0 and (16.0 <= time_float < 21.0):
            effective_alt = 0

        if effective_alt <= -6:
            phase, col1, col2, col3, pwm, fx, sx, ix, pal = night_effects.get_night_payload(moon, clouds, is_stormy)
        else:
            r, g, b, base_pwm, base_phase = calculate_base_day_colors(effective_alt, clouds, turbidity)
            phase, col1, col2, col3, pwm, fx, sx, ix, pal = day_effects.get_day_payload(r, g, b, base_pwm, clouds, base_phase, is_stormy)

        # --- VIVID BOOST (Always run now unless overridden below) ---
        col1 = [min(255, int(c * 1.1)) for c in col1[:3]] + [0]
        col2 = [min(255, int(c * 1.8)) for c in col2[:3]] + [0]
        col3 = [min(255, int(c * 1.8)) for c in col3[:3]] + [0]

        # --- BASE EXPANSION ZONE ---
        exp_fx, exp_sx, exp_ix, exp_pal = fx, sx, ix, pal
        exp_col1 = get_saturated_color(col1)
        exp_col2 = get_saturated_color(col2)
        exp_col3 = get_saturated_color(col3)

        if is_stormy:
            exp_fx = 38  
            exp_sx = 40 
            exp_ix = 100  
            exp_col1 = get_saturated_color(col1)
            exp_col2 = get_saturated_color(col2)
            exp_col3 = [0, 0, 0, 0]
        elif "Rainy" in phase:
            exp_col1 = [106, 149, 255, 0]
            exp_col2 = [148, 148, 148, 0]

        # ----------------------------------------------------
        # --- YOUR NIGHT PRESET VARIABLES ---
        # ----------------------------------------------------
        np_col1 = [0, 255, 200, 0]
        np_col2 = [0, 0, 0, 0]
        np_col3 = [0, 0, 0, 0]
        np_fx, np_sx, np_ix, np_pal = 88, 96, 103, 43
        
        np_tank_col1 = [255, 255, 255, 0]
        np_tank_ix = 67

        # ----------------------------------------------------
        # --- THE MASTER CLOCK ROUTER ---
        # ----------------------------------------------------
        wled_transition = 50
        seg0_mult = 1.0
        tank_mult = 1.0
        calculated_pwm = pwm
        is_crossfading = False

        if adj_time < 7.0: # Midnight to 7:00 AM Catch-all
            pwm = 0

        elif 7.0 <= adj_time < 7.5:
            progress = (adj_time - 7.0) / 0.5
            pwm = int(10 * progress)
            phase += " [PRE-DAWN PWM FILL]"

        elif 7.5 <= adj_time < 8.0:
            progress = (adj_time - 7.5) / 0.5 
            pwm = int(10 + (calculated_pwm - 10) * progress)
            seg0_mult = 1.0 - progress
            wled_transition = 200 
            phase += " [MORNING HANDOFF]"

        elif 8.0 <= adj_time < 17.0:
            if is_stormy:
                pwm = calculated_pwm 
                phase += " [DAYTIME STORM - RGB Active]"
            elif clouds >= 30:
                pwm = calculated_pwm 
                phase += " [DAYTIME CLOUDS - RGB Active]"
            else:
                pwm = calculated_pwm
                seg0_mult = 0.0
                fx = 0  
                phase += " [MAIN RGB OFF - Clear Sky]"

        elif 17.0 <= adj_time < 18.0:
            progress = (adj_time - 17.0) / 1.0
            pwm = int(calculated_pwm - ((calculated_pwm - 18) * progress))
            seg0_mult = progress
            wled_transition = 200
            phase += " [EVENING HANDOFF]"

        elif 18.0 <= adj_time < 19.5: # 6:00 PM to 7:30 PM
            pwm = max(calculated_pwm, 18)
            phase += " [EVENING HOLD]"

        elif 19.5 <= adj_time < 21.0: # 7:30 PM to 9:00 PM
            pwm = 0
            if not is_stormy:
                # Apply Night Preset Colors & FX
                col1, col2, col3 = np_col1, np_col2, np_col3
                fx, sx, ix, pal = np_fx, np_sx, np_ix, np_pal
                exp_col1, exp_col2, exp_col3 = np_tank_col1, np_col2, np_col3
                exp_fx, exp_sx, exp_ix, exp_pal = np_fx, np_sx, np_tank_ix, np_pal
                
                # Slowly dim both ceiling and tank down to 50%
                progress = (adj_time - 19.5) / 1.5
                seg0_mult = 1.0 - (progress * 0.5)
                tank_mult = seg0_mult
                phase += " [NIGHT PRESET DIMMING]"

        elif 21.0 <= adj_time < 22.0: # 9:00 PM to 10:00 PM
            pwm = 0
            if not is_stormy:
                progress = (adj_time - 21.0) / 1.0
                # Start colors at the 50% brightness they ended at 9pm
                start_c1 = [int(c * 0.5) for c in np_col1]
                start_exp_c1 = [int(c * 0.5) for c in np_tank_col1]
                
                # Crossfade math
                col1 = [int(lerp(start_c1[i], col1[i], progress)) for i in range(3)] + [0]
                exp_col1 = [int(lerp(start_exp_c1[i], exp_col1[i], progress)) for i in range(3)] + [0]
                
                # Keep effect properties until fade completes
                fx, sx, ix, pal = np_fx, np_sx, np_ix, np_pal
                exp_fx, exp_sx, exp_ix, exp_pal = np_fx, np_sx, np_tank_ix, np_pal
                
                is_crossfading = True
                phase += " [FADING TO DEEP NIGHT]"

        elif 22.0 <= adj_time < 22.5: # 10:00 PM to 10:30 PM
            pwm = 0
            phase += " [DEEP NIGHT]"

        elif 22.5 <= adj_time < 27.0: # 10:30 PM to 3:00 AM
            pwm = 0
            if not is_stormy:
                # Turn off ceiling RGB entirely
                seg0_mult = 0.0
                fx = 0
                
                # Keep tank ON with Night Preset at exactly 50% brightness
                exp_col1 = [int(c * 0.5) for c in np_tank_col1]
                exp_col2, exp_col3 = [0,0,0,0], [0,0,0,0]
                exp_fx, exp_sx, exp_ix, exp_pal = np_fx, np_sx, np_tank_ix, np_pal
                is_crossfading = True # skips the uniform multiplier below
                
                phase += " [SLEEP MODE - TANK ONLY]"

        else: # 27.0 to 30.0 (3:00 AM to 6:00 AM)
            pwm = 0
            phase += " [DEEP NIGHT RESUMED]"

        # Apply multiplier uniformly (if not already handled by custom crossfades)
        if not is_crossfading and not is_stormy:
            col1 = [int(c * seg0_mult) for c in col1[:3]] + [0]
            col2 = [int(c * seg0_mult) for c in col2[:3]] + [0]
            col3 = [int(c * seg0_mult) for c in col3[:3]] + [0]
            exp_col1 = [int(c * tank_mult) for c in exp_col1[:3]] + [0]
            exp_col2 = [int(c * tank_mult) for c in exp_col2[:3]] + [0]
            exp_col3 = [int(c * tank_mult) for c in exp_col3[:3]] + [0]

        # ----------------------------------------------------
        # --- SEGMENT 1 (PWM) LIGHTNING CONFIGURATION ---
        # ----------------------------------------------------
        pwm_bri = pwm
        pwm_fx = 0
        pwm_sx = 128
        pwm_ix = 128
        pwm_col1 = [235, 235, 235, 235]
        pwm_col2 = [0, 0, 0, 0]

        if is_stormy:
            # Drop the overall segment brightness at night so lightning isn't blinding
            if adj_time >= 21.0 or adj_time < 7.0:
                pwm_bri = 30 
            else:
                pwm_bri = 255 
                
            pwm_fx = 57  
            pwm_sx = 220
            pwm_ix = 200
            pwm_col1 = [255, 255, 255, 255]
            
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
