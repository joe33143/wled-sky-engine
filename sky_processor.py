python

    import os
    import math
    import requests
    import json
    from datetime import datetime
    import pytz
    from suncalc import get_position
    import paho.mqtt.client as mqtt
    
    # --- ENVIRONMENT VARIABLES FROM GITHUB SECRETS ---
    WEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
    AIO_USERNAME = os.getenv("AIO_USERNAME")
    AIO_KEY = os.getenv("AIO_KEY")
    
    # Adafruit MQTT Configuration
    MQTT_BROKER = "://adafruit.com"
    MQTT_PORT = 1883
    MQTT_TOPIC = f"{AIO_USERNAME}/feeds/wled-sky/api" # Adding /api allows WLED to parse raw JSON payloads
    
    LAT = 25.3176                     # Varanasi Latitude
    LON = 83.0062                     # Varanasi Longitude
    
    def get_realtime_turbidity():
        """Fetches air pollution metrics for Varanasi to calculate atmospheric haze."""
        url = f"http://openweathermap.org{LAT}&lon={LON}&appid={WEATHER_API_KEY}"
        try:
            response = requests.get(url, timeout=5).json()
            components = response['list']['components']
            
            # Coarse dust particles (pm10) and NO2 heavily impact red/orange scattering
            pm10 = components.get('pm10', 20)
            no2 = components.get('no2', 15)
            
            # Base turbidity is 2.0 (clean air). Scale it upward based on dust concentration.
            calculated_turbidity = 2.0 + (pm10 / 30.0) + (no2 / 20.0)
            return min(15.0, max(2.0, calculated_turbidity))
        except Exception as e:
            print(f"Weather API fallback used. Error: {e}")
            return 5.0 # Fallback default turbidity if API fails
    
    def calculate_sky_rgb(turbidity):
        """Calculates custom RGB values using sun angle and current turbidity."""
        now = datetime.now(pytz.utc)
        pos = get_position(now, LON, LAT)
        altitude_deg = math.degrees(pos['altitude'])
        
        # Night time rule (Sun below twilight threshold)
        if altitude_deg <= -6:
            return [15, 20, 40] # Night deep ink blue
            
        if altitude_deg > 12:
            # Daylight state: High turbidity bleeds yellow/orange into the pale blue sky
            r = int(140 + (turbidity * 5))
            g = int(190 + (turbidity * 2))
            b = int(255 - (turbidity * 4))
        else:
            # Golden Hour & Sunset transition state
            factor = (altitude_deg + 6) / 18.0  # Normalize scale across the sunset horizon window
            
            r = 255
            g = int(70 + (factor * 90) + (turbidity * 4))
            b = int(20 + (factor * 60) - (turbidity * 2))
            
        return [max(0, min(255, x)) for x in (r, g, b)]
    
    def main():
        # 1. Verify secrets are loaded
        if not WEATHER_API_KEY or not AIO_USERNAME or not AIO_KEY:
            print("Error: Missing required environment secrets. Check GitHub settings.")
            return
    
        # 2. Gather data and compute
        turbidity = get_realtime_turbidity()
        rgb = calculate_sky_rgb(turbidity)
        
        # 3. Build WLED native JSON state structure
        wled_payload = {
            "on": True,
            "bri": 255,
            "seg": [{"col": [rgb, [0,0,0], [0,0,0]]}]
        }
        
        # 4. Publish to Adafruit IO via MQTT
        client = mqtt.Client(client_id=f"VaranasiSky_{AIO_USERNAME}", callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        client.username_pw_set(AIO_USERNAME, AIO_KEY)
        
        print(f"Connecting to Adafruit IO...")
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        
        print(f"Publishing to topic: {MQTT_TOPIC}")
        info = client.publish(MQTT_TOPIC, json.dumps(wled_payload), qos=1)
        info.wait_for_publish() # Ensure data transfers completely before closing script
        
        client.loop_stop()
        client.disconnect()
        print(f"Successfully sent data. Turbidity: {turbidity:.2f} -> RGB: {rgb}")
    
    if __name__ == "__main__":
        main()
    

Use code with caution.
