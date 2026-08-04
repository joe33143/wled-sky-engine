def get_day_payload(r, g, b, pwm, clouds, base_phase_name, is_stormy=False):
    """Applies daytime animations, injecting specific WLED presets for weather."""
    c = clouds / 100.0
    
    # Base dynamic overcast dimming
    if clouds >= 75 and not is_stormy:
        grey = (r + g + b) // 3
        fade = ((clouds - 75) / 25.0) * 0.7 
        r = int(r + (grey - r) * fade)
        g = int(g + (grey - g) * fade)
        b = int(b + (grey - b) * fade)

    col1 = [r, g, b, 0]
    col2 = [0, 0, 0, 0]
    col3 = [0, 0, 0, 0]
    fx = 0
    sx = 128
    ix = 128
    pal = 0
    phase_name = base_phase_name

    if is_stormy:
        # --- THUNDER STORM PRESET ---
        fx = 57  
        sx = 128  
        ix = 128 
        pal = 9
        col1 = [255, 255, 255, 0]  
        col2 = [56, 56, 56, 0]  
        pwm = max(int(pwm * 0.35), 18)
        phase_name += " [THUNDER STORM ACTIVE]"
        
    elif clouds >= 75:
        # --- RAINY / OVERCAST PRESET ---
        fx = 88
        sx = 96
        ix = 224
        pal = 9
        col1 = [118, 177, 255, 0]
        pwm = max(pwm, 18)
        phase_name += f" [Rainy / Overcast: {clouds}%]"
        
    elif base_phase_name == "Low Sun / Horizon" and clouds < 30:
        # --- DYNAMIC EVENING / SUNSET ---
        fx = 88
        sx = 68
        ix = 160
        pal = 0  
        
        # Boost the natural RGB so the sunset pops organically
        r_boost = int(min(255, r * 1.5))
        g_boost = int(min(255, g * 1.3))
        b_boost = int(min(255, b * 1.1))
        
        col1 = [r_boost, g_boost, b_boost, 0]
        col2 = [int(r_boost * 0.6), int(g_boost * 0.5), int(b_boost * 0.5), 0]
        col3 = [int(r_boost * 0.9), int(g_boost * 0.5), 0, 0] # Warm organic highlight
        
        pwm = max(pwm, 18)
        phase_name += " [Dynamic Evening Preset]"
        
    elif clouds < 30:
        phase_name += " [Clear Sky]"
        
    else:
        # --- PARTLY CLOUDY ---
        fx = 38
        sx = int(20 + (c * 50)) 
        ix = 100 
        pal = 0
        col2 = [int(r * 0.95), int(g * 0.85), int(b * 0.70), 0]
        col3 = [int(min(255, r * 1.3)), int(min(255, g * 1.15)), int(min(255, b * 1.00)), 0]
        pwm = max(pwm, 18) 
        phase_name += f" [Rolling Clouds: {clouds}%]"

    # <-- This is the line that got deleted!
    return phase_name, col1, col2, col3, pwm, fx, sx, ix, pal
    
