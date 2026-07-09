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
        # --- THE CLEAN SINGLE PAYLOAD ---
        wled_payload = {
            "on": True,
            "bri": master_brightness,
            "seg": [
                {
                    "id": 0,
                    "bri": 255,
                    "fx": 0, # Kills any lingering preset effects, forces solid color
                    "col": [seg0_state] 
                },
                {
                    "id": 1,
                    "bri": 255,
                    "fx": 0, # Kills any lingering preset effects, forces solid color
                    "col": [seg1_state]
                }
            ]
        }

    # --- MQTT PUBLISHING ALGORITHM ---
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "VaranasiSky_Publisher_Public")
    except AttributeError:
        client = mqtt.Client("VaranasiSky_Publisher_Public")
    
    print("Connecting to Public HiveMQ...")
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        
        print(f"Publishing payload to topic {MQTT_TOPIC}...")
        
        # Back to a single, reliable push
        info = client.publish(MQTT_TOPIC, json.dumps(wled_payload), qos=1)
        info.wait_for_publish() 
        
        client.loop_stop()
        client.disconnect()
        
        print(f"Sync complete. Seg 0 (RGB): {seg0_state}, Seg 1 (PWM): {seg1_state}")
    except Exception as e:
        print(f"MQTT Operation failed: {e}")

if __name__ == "__main__":
    main()
    
