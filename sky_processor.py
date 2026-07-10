import os
import math
import requests
import json
from datetime import datetime
import pytz
from suncalc import get_position
import paho.mqtt.client as mqtt

# --- GLOBALS & CONFIG ---
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

    # --- 5. THE LATE PWM WAKE-UP (RESTORED: 35° to 55°) ---
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
        
        # FILTER MODE CROSSFADE
        r = int(255 - (factor * 55))       
        g = int(210 - (factor * 60) + (turbidity * 1.5))  
        b = max(0, int(200 - (factor * 200) - (turbidity * 2.0))) 
        
        if clouds > 25:
