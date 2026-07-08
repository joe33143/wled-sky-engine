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

    # --- 2. THE COLOR HOLD (-6° to 15°) ---
    elif altitude_deg <= 15:
        factor = (altitude_deg + 6) / 21.0  
        
        r = 255
        g = int(40 + (factor * 80) + (turbidity * 4))
        b = int(10 + (factor * 20) - (turbidity * 2))
        
        if clouds > 40:
            g = int(g * 0.7)
            b = int(b * 1.5)
            
        seg1_rgbw = [0, 0, 0, 0] # PWM OFF

    # --- 3. THE WIDE RAMP (15° to 35°) ---
    elif altitude_deg <= 35:
        factor = (altitude_deg - 15) / 20.0  
        
        # FIX: PWM now strictly scales within your hardware's 105-137 range
        base_pwm = 105 + int(factor * 32) 
        
        # Clouds subtract a max of 15 steps so it never accidentally drops below 105
        cloud_dim = int((clouds / 100.0) * 15)
        pwm_val = max(105, min(137, base_pwm - cloud_dim))
        seg1_rgbw = [pwm_val, pwm_val, pwm_val, pwm_val]
        
        r = 255
        g = int(120 + (factor * 80) + (turbidity * 1.5))
        b = int(30 + (factor * 150) - (turbidity * 2.0))
        
        if clouds > 25:
            cloud_factor = (clouds - 25) / 75.0  
            r = int(r * (1.0 - (cloud_factor * 0.3)))
            g = int(g * (1.0 - (cloud_factor * 0.1)))
            b = int(b + (cloud_factor * 40)) 

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
