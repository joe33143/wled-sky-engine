import os
import math
import requests
import json
from datetime import datetime
import pytz
from suncalc import get_position
import paho.mqtt.client as mqtt

# --- GLOBALS & CONFIG ---
# Swapped to look for the Meteosource key
METEOSOURCE_API_KEY = os.getenv("METEOSOURCE_API_KEY")

MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "joe33143/wled-sky/api"
LAT = 25.3176
LON = 83.0062

def get_weather_and_turbidity():
    # Meteosource Free Tier Endpoint
    weather_url = f"https://www.meteosource.com/api/v1/free/point?lat={LAT}&lon={LON}&sections=current&key={METEOSOURCE_API_KEY}"
    
    # Since Meteosource free tier doesn't do AQI pollution data, 
    # we lock turbidity to a baseline of 5.0 for this test script.
    turbidity = 5.0
    clouds = 0  
    
    try:
        res = requests.get(weather_url, timeout=5).json()
        # Meteosource nests their cloud cover percentage inside the 'current' object
        clouds = res.get('current', {}).get('cloud_cover', 0)
        print(f"Meteosource metrics -> Clouds: {clouds}%, Dust Turbidity: {turbidity:.2f}")
    except Exception as e:
        print(f"Meteosource API fallback used: {e}")
        
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
        print(f"Night active -> Moon Phase Illumination: {moon_factor:.2f}")
        
        if moon_factor < 0.15:
            return "TRIGGER_NIGHT_PRESET", [0, 0, 0, 0]
        
        if clouds > 30:
            moon_factor *= (1.0 - ((clouds - 30) / 70.0) * 0.3)
            
        r = int(35 + (moon_factor * 30))
        g = int(45 + (moon_factor * 40))
        b = int(60 + (moon_factor * 60))
        
        seg1_rgbw = [0, 0, 0, 0]

    # --- 2. CIVIL TWILIGHT (-6° to 0°) ---
    elif altitude_deg <= 0:
        factor = (altitude_deg + 6) / 6.0  
        
        night_r, night_g, night_b = 15, 20, 30
        sun_r, sun_g, sun_b = 130, 60, 50
        
        r = int(night_r + (factor * (sun_r - night_r)))
        g = int(night_g + (factor * (sun_g - night_g)) + (turbidity * 1.0))
        b = int(night_b + (factor * (sun_b - night_b)))
        
        if clouds > 40:
            cloud_factor = (clouds - 40) / 60.0 
            dim_multiplier = 1.0 - (cloud_factor * 0.40) 
            
            r = int(r * dim_multiplier)
            g = int(g * dim_multiplier) 
            b = int((b + 10) * dim_multiplier) 
            
        seg1_rgbw = [0, 0, 0, 0] 

    # --- 3. GOLDEN HOUR / HORIZON (0° to 10°) ---
    elif altitude_deg <= 10:
        factor = altitude_deg / 10.0  
        
        r = int(130 + (factor * 125)) 
        g = int(60 + (factor * 150) + (turbidity * 2.0))
        b = int(50 + (factor * 150) - (turbidity * 1.5))
        
        if clouds > 40:
            cloud_factor = (clouds - 40) / 60.0 
            dim_multiplier = 1.0 - (cloud_factor * 0.30) 
            
            r = int(r * dim_multiplier)
            g = int(g * dim_multiplier * 0.95) 
            b = int(b * dim_multiplier) 
            
        seg1_rgbw = [0, 0, 0, 0] 

    # --- 4. THE MORNING HOLD (RGB ONLY: 10° to 35°) ---
    elif altitude_deg <= 35:
        r = 255
        g = int(210 + (turbidity * 1.5))
        b = int(200 - (turbidity * 2.0))

        if clouds > 40:
            cloud_factor = (clouds - 40) / 60.0 
            dim_multiplier = 1.0 - (cloud_factor * 0.30) 
            
            r = int(r * dim_multiplier)
            g = int(g * dim_multiplier * 0.95) 
            b = int(b * dim_multiplier)
            
        seg1_rgbw = [0, 0, 0, 0] 

    # --- 5. THE LATE PWM WAKE-UP (35° to 55°) ---
    elif altitude_deg <= 55:
        factor = (altitude_deg - 35) / 20.0  
        
        PWM_FLOOR = 105
        PWM_MAX = 135
        PWM_RANGE = PWM_MAX - PWM_FLOOR
        
        base_pwm = PWM_FLOOR + int(factor * PWM_RANGE) 
        cloud_dim = int((clouds / 100.0) * 20) 
        
        target_pwm = base_pwm - cloud_dim
        if target_pwm < PWM_FLOOR:
            pwm_val = 0
        else:
            pwm_val = min(PWM_MAX, target_pwm)
            
        seg1_rgbw = [pwm_val, pwm_val, pwm_val, pwm_val]
        
        r = int(255 - (factor * 55))       
        g = int(210 - (factor * 60) + (turbidity * 1.5))  
        b = max(0, int(200 - (factor * 200) - (turbidity * 2.0))) 
        
        # --- OVERCAST BLUE SHIFT ---
        if clouds > 25:
            cloud_factor = (clouds - 25) / 75.0  
            dim_multiplier = 1.0 - (cloud_factor * 0.5)
            
            r = int(r * dim_multiplier * (1.0 - (cloud_factor * 0.45))) 
            g = int(g * dim_multiplier * (1.0 - (cloud_factor * 0.15))) 
            b = int(b * dim_multiplier) + int(cloud_factor * 180) 

    # --- 6. FULL DAYTIME (Above 55°) ---
    else:
        PWM_FLOOR = 105
        PWM_MAX = 135   
        
        base_pwm = PWM_MAX
        cloud_dim = int((clouds / 100.0) * 20)
        
        target_pwm = base_pwm - cloud_dim
        if target_pwm < PWM_FLOOR:
            pwm_val = 0
        else:
            pwm_val = min(PWM_MAX, target_pwm)
            
        seg1_rgbw = [pwm_val, pwm_val, pwm_val, pwm_val]
        
        r = 200
        g = int(150 + (turbidity * 1.5))
        b = 0  
        
        # --- OVERCAST BLUE SHIFT ---
        if clouds > 25:
            cloud_factor = (clouds - 25) / 75.0  
            dim_multiplier = 1.0 - (cloud_factor * 0.5)
            
            r = int(r * dim_multiplier * (1.0 - (cloud_factor * 0.45))) 
            g = int(g * dim_multiplier * (1.0 - (cloud_factor * 0.15))) 
            b = int(b * dim_multiplier) + int(cloud_factor * 180) 

    # ==========================================
    # GLOBAL HARDWARE RGB CALIBRATION FILTER
    # ==========================================
    cal_r = 1.00  
    cal_g = 0.85  
    cal_b = 0.60  

    raw_r = max(0, min(255, r))
    raw_g = max(0, min(255, g))
    raw_b = max(0, min(255, b))

    max_val = max(raw_r, raw_g, raw_b)
    if max_val < 100 and altitude_deg <= 0:
        dimming_ratio = max_val / 100.0 
        low_end_green_factor = 0.35 + (0.65 * dimming_ratio)
        cal_g *= low_end_green_factor
        
        low_end_base_factor = 0.60 + (0.40 * dimming_ratio)
        cal_r *= low_end_base_factor
        cal_b *= low_end_base_factor

    final_r = int(raw_r * cal_r)
    final_g = int(raw_g * cal_g)
    final_b = int(raw_b * cal_b)

    seg0_rgbw = [max(0, min(255, final_r)), max(0, min(255, final_g)), max(0, min(255, final_b)), 0]
    
    return seg0_rgbw, seg1_rgbw

def main():
    if not METEOSOURCE_API_KEY:
        print("Error: Missing Meteosource API Key.")
        return

    turbidity, clouds = get_weather_and_turbidity()
    seg0_state, seg1_state = calculate_sky_state(turbidity, clouds)
    
    master_brightness = 255

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
        wled_payload = {
            "on": True,
            "bri": master_brightness,
            "transition": 20, 
            "seg": [
                {
                    "id": 0,
                    "bri": 255,
                    "fx": 0,  
                    "col": [seg0_state] 
                },
                {
                    "id": 1,
                    "bri": 255,
                    "fx": 0,  
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
