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
            return "TRIGGER_NIGHT_PRESET", "00000000"
        
        if clouds > 30:
            moon_factor *= (1.0 - ((clouds - 30) / 70.0) * 0.5)
            
        # Segment 1: Dedicated moonlight RGB
        r = int(40 + (moon_factor * 60))   
        g = int(80 + (moon_factor * 80))   
        b = int(150 + (moon_factor * 105)) 
        
        # Segment 3: PWM is completely OFF at night to prevent muddy light
        seg3_hex = "00000000"
        seg1_rgb = [max(0, min(255, x)) for x in (r, g, b)]
        
        return seg1_rgb, seg3_hex
            
    # --- 2. DAYTIME ENGINE ---
    elif altitude_deg > 12:
        # Segment 3: PWM runs high, scaling down slightly if it's very cloudy
        pwm_val = 255 - int(clouds * 0.85) # Drops to ~170 on heavily overcast days
        seg3_hex = f"{pwm_val:02X}{pwm_val:02X}{pwm_val:02X}{pwm_val:02X}"
        
        # Segment 1: Warm amber base to offset the 6500K cold white
        r = 255
        g = int(180 + (turbidity * 1.5))
        b = int(100 - (turbidity * 2.0))
        
        if clouds > 25:
            # Shift towards a cooler, neutral tone by suppressing red/amber
            cloud_factor = (clouds - 25) / 75.0  
            r = int(r * (1.0 - (cloud_factor * 0.3)))
            g = int(g * (1.0 - (cloud_factor * 0.1)))
            b = int(b + (cloud_factor * 40)) # Boost blue slightly for overcast feel
            
        seg1_rgb = [max(0, min(255, x)) for x in (r, g, b)]
        return seg1_rgb, seg3_hex
        
    # --- 3. TWILIGHT / GOLDEN HOUR ENGINE ---
    else:
        factor = (altitude_deg + 6) / 18.0  
        
        # Segment 3: PWM ramps down smoothly to the physical floor limit (106 / 6A)
        pwm_val = 106 + int(factor * 64) 
        seg3_hex = f"{pwm_val:02X}{pwm_val:02X}{pwm_val:02X}{pwm_val:02X}"
        
        # Segment 1: Deep, saturated sunset colors take over visually
        r = 255
        g = int(60 + (factor * 110) + (turbidity * 4))
        b = int(15 + (factor * 40) - (turbidity * 2))
        
        if clouds > 40:
            # Clouds scatter the light, creating moodier purple/deep hues
            g = int(g * 0.7)
            b = int(b * 1.5)
            
        seg1_rgb = [max(0, min(255, x)) for x in (r, g, b)]
        return seg1_rgb, seg3_hex

def main():
    if not WEATHER_API_KEY:
        print("Error: Missing OpenWeather API Key.")
        return

    turbidity, clouds = get_weather_and_turbidity()
    seg1_state, seg3_state = calculate_sky_state(turbidity, clouds)
    
    # MASTER BRIGHTNESS LOCKED TO 100%
    master_brightness = 255

    # --- REPOSITORY HOSTED PRESET LOADING MECHANISM ---
    if seg1_state == "TRIGGER_NIGHT_PRESET":
        print("Dark night reached. Pulling custom profile dark_night_preset.json...")
        try:
            with open("dark_night_preset.json", "r") as f:
                wled_payload = json.load(f)
            
            # Ensure preset respects the 100% master brightness rule and turns off PWM
            wled_payload["bri"] = master_brightness
            if "seg" in wled_payload:
                # Add or update Segment 3 to be OFF
                wled_payload["seg"].append({"id": 3, "col": ["00000000"]})
                
            print("Successfully loaded
