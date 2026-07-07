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
    pollution_url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={LAT}&lon={LON}&appid={WEATHER_API_KEY}"
    weather_url = f"http://api.openweathermap.org/data/2.5/weather?lat={LAT}&lon={LON}&appid={WEATHER_API_KEY}"
    
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
    
    # --- 1. NIGHTTIME ENGINE ---
    if altitude_deg <= -6:
        moon_factor = calculate_moon_phase()
        print(f"Night active -> Moon Phase Illumination: {moon_factor:.2f}")
        
        if moon_factor < 0.15:
            return "TRIGGER_NIGHT_PRESET", [0, 0, 0, 0]
        
        if clouds > 30:
            moon_factor *= (1.0 - ((clouds - 30) / 70.0) * 0.5)
            
        # Segment 0 (RGB): Dedicated moonlight 
        r = int(40 + (moon_factor * 60))   
        g = int(80 + (moon_factor * 80))   
        b = int(150 + (moon_factor * 105)) 
        
        seg0_rgbw = [max(0, min(255, x)) for x in (r, g, b)] + [0]
        
        # Segment 1 (PWM): Completely OFF at night 
        seg1_rgbw = [0, 0, 0, 0]
        
        return seg0_rgbw, seg1_rgbw
            
    # --- 2. DAYTIME ENGINE ---
    elif altitude_deg > 12:
        # Segment 1 (PWM): Runs high, using the 4th channel (W) or all channels depending on WLED mapping
        pwm_val = 255 - int(clouds * 0.85)
        seg1_rgbw = [pwm_val, pwm_val, pwm_val, pwm_val]
        
        # Segment 0 (RGB): Warm amber base
        r = 255
        g = int(180 + (turbidity * 1.5))
        b = int(100 - (turbidity * 2.0))
        
        if clouds > 25:
            cloud_factor = (clouds - 25) / 75.0  
            r = int(r * (1.0 - (cloud_factor * 0.3)))
            g = int(g * (1.0 - (cloud_factor * 0.1)))
            b = int(b + (cloud_factor * 40)) 
            
        seg0_rgbw = [max(0, min(255, x)) for x in (r, g, b)] + [0]
        return seg0_rgbw, seg1_rgbw
        
    # --- 3. TWILIGHT / GOLDEN HOUR ENGINE ---
    else:
        factor = (altitude_deg + 6) / 18.0  
        
        # Segment 1 (PWM): Ramps down smoothly to physical floor (106)
        pwm_val = 106 + int(factor * 64) 
        seg1_rgbw = [pwm_val, pwm_val, pwm_val, pwm_val]
        
        # Segment 0 (RGB): Deep sunset colors
        r = 255
        g = int(60 + (factor * 110) + (turbidity * 4))
        b = int(15 + (factor * 40) - (turbidity * 2))
        
        if clouds > 40:
            g = int(g * 0.7)
            b = int(b * 1.5)
            
        seg0_rgbw = [max(0, min(255, x)) for x in (r, g, b)] + [0]
        return seg0_rgbw, seg1_rgbw

def main():
    if not WEATHER_API_KEY:
        print("Error: Missing OpenWeather API Key.")
        return

    turbidity, clouds = get_weather_and_turbidity()
    seg0_state, seg1_state = calculate_sky_state(turbidity, clouds)
    
    # MASTER BRIGHTNESS LOCKED TO 100%
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
                
                # Check for Segment 1 (PWM White)
                seg1_exists = False
                for segment in wled_payload["seg"]:
                    if segment.get("id") == 1:
                        segment["bri"] = 255
                        segment["col"] = [[0, 0, 0, 0]]
                        seg1_exists = True
                        break
                
                # Force append Segment 1 OFF if missing from preset
                if not seg1_exists:
                    wled_payload["seg"].append({"id": 1, "bri": 255, "col": [[0, 0, 0, 0]]})
                
        except Exception as e:
            print(f"Preset file reading missed. Error: {e}")
            wled_payload = {
                "on": True,
                "bri": master_brightness,
                "seg": [
                    {"id": 0, "start": 0, "stop": 90, "bri": 255, "col": [[15, 20, 50, 0]]},
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
    
