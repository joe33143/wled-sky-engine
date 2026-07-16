# day_effects.py

def get_day_payload(r, g, b, pwm, clouds, base_phase_name):
    """Applies daytime animations and secondary colors to the LERP baseline."""
    c = clouds / 100.0
    col1 = [r, g, b, 0]
    
    # Default to solid, static clear sky
    fx = 0
    sx = 128
    ix = 128
    col2 = [0, 0, 0, 0]
    col3 = [0, 0, 0, 0]
    phase_name = base_phase_name
    
    # --- EFFECT SELECTION ---
    if clouds >= 25:
        # Cloudy Day: Aurora Effect (Updated for WLED 16)
        fx = 38
        sx = int(20 + (c * 50)) # Rolls faster with more clouds
        ix = 150 
        
        # Calculate dynamic shadow and highlight based on the LERP daytime color
        col2 = [int(r * 0.7), int(g * 0.7), int(b * 0.7), 0] # 30% Darker
        col3 = [int(min(255, r * 1.2)), int(min(255, g * 1.2)), int(min(255, b * 1.3)), 0] # 20% Brighter
        phase_name += f" [Rolling Clouds: {clouds}%]"
    else:
        phase_name += " [Clear Sky]"

    return phase_name, col1, col2, col3, pwm, fx, sx, ix
