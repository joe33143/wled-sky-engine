import os
import math
import requests
import json
from datetime import datetime
import pytz
from suncalc import get_position
import paho.mqtt.client as mqtt

WEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "joe33143/wled-sky/api"

LAT = 25.3176                     
LON = 83.0062                     

def get_weather_and_turbidity():
    pollution_url = f"https://api.openweathermap.org/data/2.5/air_pollution?lat={LAT}&lon={LON}&appid={WEATHER_API_KEY}"
    weather_url = f"https://api.openweathermap.org/data/2.5/weather?lat={LAT}&lon={LON}&appid={WEATHER_API_KEY}"
    
    turbidity = 5.0
    clouds = 0  
    
    try:
        res = requests.get(pollution_url, timeout=5).json()
        components = res['list'][0]['components']
        pm10 = components.get('pm10', 20)
        no2 = components.get('no2', 15)
        turbidity = min(15.0, max(2.0, 2.0 + (pm10 / 12.0) + (no2 / 8.0)))
    except Exception as e:
        print(f"Air Pollution API fallback used: {e}")

    try:
        res = requests.get(weather_url, timeout=5).json()
        clouds = res.get('clouds', {}).get('all', 0)
        print(f"Current weather metrics -> Clouds: {clouds}%, Dust Turbidity: {turbidity:.2f}")
    except Exception as e:
        print(f"Weather API fallback used: {e}")
        
    return turbidity, clouds

def calculate_moon_phase():
    now = datetime.now(pytz.utc)
    base_new_moon = datetime(2000, 1, 6, 18, 14, tzinfo=pytz.utc)
    diff = now - base_new_moon
    synodic_month = 29.530588853
    phase_days = diff.total_seconds() / 86400.0 % synodic_month
    normalized_phase = phase_days / synodic_month
    if normalized_phase <= 0.5:
        return normalized_phase * 2.0
    return (1.0 - normalized_phase) * 2.0

def calculate_sky_state(turbidity, clouds):
    now = datetime.now(pytz.utc)
    pos = get_position(now, LON, LAT)
    altitude_deg = math.degrees(pos['altitude'])
    
    r, g, b = 0, 0, 0
    seg1_rgbw = [0, 0, 0, 0]
    
    # --- 1. NIGHTTIME ENGINE (Below -6°) ---
    if altitude_deg <= -6:
        moon_factor = calculate_moon_phase()
        
        if moon_factor < 0.15:
            return "TRIGGER_NIGHT_PRESET", [0, 0, 0, 0]
        
        if clouds > 30:
            moon_factor *= (1.0 - ((clouds - 30) / 70.0) * 0.5)
            
        r = int(10 + (moon_factor * 20))
        g = int(15 + (moon_factor * 30))
        b = int(25 + (moon_factor * 50))
        
        seg1_rgbw = [0, 0, 0, 0] # PWM OFF

    # --- 2. THE LONG MORNING (RGB ONLY: -6° to 35°) ---
    # Holds the PWM off until roughly 8:00 AM in summer.
    # RGB strip handles the entire dawn-to-morning transition.
    elif altitude_deg <= 35:
        factor = (altitude_deg + 6) / 41.0  # Scales across the massive 41-degree morning gap
        
        # Red starts at 150 at dawn, reaches 255 by 8:00 AM
        r = int(150 + (factor * 105)) 
        # Green and Blue steadily climb to create a bright, neutral white by 8:00 AM
        g = int(30 + (factor * 200) + (turbidity * 3))
        b = int(20 + (factor * 200) - (turbidity * 2))
        
        # TRUE OVERCAST DESATURATION
        if clouds > 40:
            cloud_factor = (clouds - 40) / 60.0 
            dim_multiplier = 1.0 - (cloud_factor * 0.65) 
            
            r = int(r * dim_multiplier)
            g = int(g * dim_multiplier * 0.8) 
            b = int((b + 40) * dim_multiplier) 
            
        seg1_rgbw = [0, 0, 0, 0] # PWM STRICTLY OFF UNTIL 8 AM

    # --- 3. THE LATE PWM WAKE-UP (35° to 55°) ---
    # Between 8:00 AM and 10:00 AM. PWM finally ramps up.
    elif altitude_deg <= 55:
        factor = (altitude_deg - 35) / 20.0  
        
        base_pwm = 105 + int(factor * 32) 
        cloud_dim = int((clouds / 100.0) * 15)
        
        # The Trapdoor: Stays off if clouds drop it below the hardware floor
        target_pwm = base_pwm - cloud_dim
        if target_pwm < 105:
            pwm_val = 0
        else:
            pwm_val = min(137, target_pwm)
            
        seg1_rgbw = [pwm_val, pwm_val, pwm_val, pwm_val]
        
        # RGB holds peak daytime brightness, balancing color
        r = 255
        g = int(230 + (factor * 25) + (turbidity * 1.0))
        b = int(220 + (factor * 35) - (turbidity * 2.0))
        
        # OVERCAST DAYTIME DESATURATION
        if clouds > 25:
            cloud_factor = (clouds - 25) / 75.0  
            dim_multiplier = 1.0 - (cloud_factor * 0.5)
            
            r = int(r * dim_multiplier)
            g = int(g * dim_multiplier * 0.9)
            b = int((b + 30) * dim_multiplier)

    # --- 4. FULL DAYTIME (Above 55°) ---
    # Sun is peaking. PWM locked to max hardware limit.
    else:
        base_pwm = 137
        cloud_dim = int((clouds / 100.0) * 15)
        
        target_pwm = base_pwm - cloud_dim
        if target_pwm < 105:
            pwm_val = 0
        else:
            pwm_val = min(137, target_pwm)
            
        seg1_rgbw = [pwm_val, pwm_val, pwm_val, pwm_val]
        
        r = 255
        g = int(255 + (turbidity * 1.5))
        b = int(255 - (turbidity * 2.0))
        
        if clouds > 25:
            cloud_factor = (clouds - 25) / 75.0  
            dim_multiplier = 1.0 - (cloud_factor * 0.5)
            
            r = int(r * dim_multiplier)
            g = int(g * dim_multiplier * 0.9)
            b = int((b + 30) * dim_multiplier)
 
 
    # --- 4. FULL DAYTIME (Above 35°) ---
    else:
        # FIX: Hard ceiling locked at 137
        base_pwm = 137 
        cloud_dim = int((clouds / 100.0) * 15)
        pwm_val = max(105, min(137, base_pwm - cloud_dim))
        seg1_rgbw = [pwm_val, pwm_val, pwm_val, pwm_val]
        
        r = 255
        g = int(200 + (turbidity * 1.5))
        b = int(180 - (turbidity * 2.0))
        
        if clouds > 25:
            cloud_factor = (clouds - 25) / 75.0  
            r = int(r * (1.0 - (cloud_factor * 0.3)))
            g = int(g * (1.0 - (cloud_factor * 0.1)))
            b = int(b + (cloud_factor * 40)) 
            
    # ==========================================
    # GLOBAL HARDWARE RGB CALIBRATION FILTER
    # ==========================================
    cal_r = 1.00  
    cal_g = 0.85  
    cal_b = 0.50  

    raw_r = max(0, min(255, r))
    raw_g = max(0, min(255, g))
    raw_b = max(0, min(255, b))

    # DYNAMIC LOW-END CURVE
    # Slowly crushes the highly efficient green diode as brightness drops.
    # Also gently dims the overall output at the bottom end to prevent it from glaring at night.
    max_val = max(raw_r, raw_g, raw_b)
    
    if max_val < 100:
        # As max_val approaches 0, the dimming_ratio approaches 0
        dimming_ratio = max_val / 100.0 
        
        # Green drops from a 1.0 multiplier at threshold down to roughly 0.35 at pitch black
        low_end_green_factor = 0.35 + (0.65 * dimming_ratio)
        cal_g *= low_end_green_factor
        
        # Red and Blue drop from a 1.0 multiplier down to roughly 0.6 at pitch black
        low_end_base_factor = 0.60 + (0.40 * dimming_ratio)
        cal_r *= low_end_base_factor
        cal_b *= low_end_base_factor

    final_r = int(raw_r * cal_r)
    final_g = int(raw_g * cal_g)
    final_b = int(raw_b * cal_b)

    seg0_rgbw = [max(0, min(255, final_r)), max(0, min(255, final_g)), max(0, min(255, final_b)), 0]
    
    return seg0_rgbw, seg1_rgbw
    

def main():
    if not WEATHER_API_KEY:
        print("Error: Missing OpenWeather API Key.")
        return

    turbidity, clouds = get_weather_and_turbidity()
    seg0_state, seg1_state = calculate_sky_state(turbidity, clouds)
    
    master_brightness = 255

    # --- REPOSITORY HOSTED PRESET LOADING MECHANISM ---
    if seg0_state == "TRIGGER_NIGHT_PRESET":
        print("Dark night reached. Pulling custom profile dark_night_preset.json...")
        try:
            with open("dark_night_preset.json", "r") as f:
                wled_payload = json.load(f)
            
            wled_payload["bri"] = master_brightness
            if "seg" in wled_payload:
                for segment in wled_payload["seg"]:
                    segment["bri"] = 255 
                
                seg1_exists = False
                for segment in wled_payload["seg"]:
                    if segment.get("id") == 1:
                        segment["bri"] = 255
                        segment["col"] = [[0, 0, 0, 0]]
                        seg1_exists = True
                        break
                
                if not seg1_exists:
                    wled_payload["seg"].append({"id": 1, "bri": 255, "col": [[0, 0, 0, 0]]})
                
        except Exception as e:
            print(f"Preset file reading missed. Error: {e}")
            wled_payload = {
                "on": True,
                "bri": master_brightness,
                "seg": [
                    {"id": 0, "start": 0, "stop": 90, "bri": 255, "col": [[5, 5, 20, 0]]},
                    {"id": 1, "start": 90, "stop": 180, "bri": 255, "col": [[0, 0, 0, 0]]}
                ]
            }
    else:
        # Standard Active Tracking Flow - targeting IDs 0 and 1
        wled_payload = {
            "on": True,
            "bri": master_brightness,
            "seg": [
                {
                    "id": 0,
                    "bri": 255,
                    "col": [seg0_state] 
                },
                {
                    "id": 1,
                    "bri": 255,
                    "col": [seg1_state]
                }
            ]
        }

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "VaranasiSky_Publisher_Public")
    except AttributeError:
        client = mqtt.Client("VaranasiSky_Publisher_Public")
    
    print("Connecting to Public HiveMQ...")
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        
        print(f"Publishing payload to topic {MQTT_TOPIC}...")
        info = client.publish(MQTT_TOPIC, json.dumps(wled_payload), qos=1)
        info.wait_for_publish() 
        
        client.loop_stop()
        client.disconnect()
        print(f"Sync complete. Seg 0 (RGB): {seg0_state}, Seg 1 (PWM): {seg1_state}")
    except Exception as e:
        print(f"MQTT Operation failed: {e}")

if __name__ == "__main__":
    main()
