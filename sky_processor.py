import os
import math
import requests
import json
import time
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
        print(f"Night active -> Moon Phase Illumination: {moon_factor:.2f}")
        
        if moon_factor < 0.15:
            return "TRIGGER_NIGHT_PRESET", [0, 0, 0, 0]
        
        if clouds > 30:
            moon_factor *= (1.0 - ((clouds - 30) / 70.0) * 0.5)
            
        r = int(10 + (moon_factor * 20))
        g = int(15 + (moon_factor * 30))
        b = int(25 + (moon_factor * 50))
        
        seg1_rgbw = [0, 0, 0, 0] # PWM OFF

    # --- 2. TRUE DAWN (RGB ONLY: -6° to 10°) ---
    # Rapid color shift. Sun breaks the horizon and quickly develops full color.
    elif altitude_deg <= 10:
        factor = (altitude_deg + 6) / 16.0  
        
        r = int(150 + (factor * 105)) 
        g = int(30 + (factor * 180) + (turbidity * 3))
        b = int(20 + (factor * 180) - (turbidity * 2))
        
        if clouds > 40:
            cloud_factor = (clouds - 40) / 60.0 
            dim_multiplier = 1.0 - (cloud_factor * 0.30) 
            
            r = int(r * dim_multiplier)
            g = int(g * dim_multiplier * 0.95) 
            b = int(b * dim_multiplier) 
            
        seg1_rgbw = [0, 0, 0, 0] # PWM OFF

    # --- 2.5 THE MORNING HOLD (RGB ONLY: 10° to 35°) ---
    # Color is fully developed. Holding bright daylight values while waiting for PWM.
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
