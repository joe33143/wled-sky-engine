# day_effects.py

def get_day_payload(r, g, b, pwm, clouds, base_phase_name):
    """Applies daytime animations and desaturates heavy overcast skies."""
    c = clouds / 100.0
    
    # --- DESATURATION ENGINE FOR HEAVY CLOUDS ---
    # A real overcast sky isn't orange/blue, it's grey. 
    # This washes out the color towards neutral grey as clouds pass 75%.
    if clouds >= 75:
        grey = (r + g + b) // 3
        fade = (clouds - 75) / 25.0  # 0.0 at 75%, 1.0 at 100%
        r = int(r + (grey - r) * fade)
        g = int(g + (grey - g) * fade)
        b = int(b + (grey - b) * fade)

    col1 = [r, g, b, 0]
    
    # Default state (Clear)
    fx = 0
    sx = 128
    ix = 128
    col2 = [0, 0, 0, 0]
    col3 = [0, 0, 0, 0]
    phase_name = base_phase_name
    
    # --- EFFECT 3-TIER SELECTION ---
    if clouds < 30:
        phase_name += " [Clear Sky]"
        
    elif clouds < 75:
        # Broken Clouds: Rolling Aurora
        fx = 38
        sx = int(20 + (c * 50)) 
        ix = 100 
        col2 = [int(r * 0.85), int(g * 0.85), int(b * 0.85), 0]
        col3 = [int(min(255, r * 1.10)), int(min(255, g * 1.10)), int(min(255, b * 1.10)), 0]
        phase_name += f" [Rolling Clouds: {clouds}%]"
        
    else:
        # Overcast: Keep the cloudy texture, but FREEZE the motion (sx = 0)
        fx = 38
        sx = 0  # Speed 0 stops the rolling animation
        ix = 100
        col2 = [int(r * 0.85), int(g * 0.85), int(b * 0.85), 0]
        col3 = [int(min(255, r * 1.10)), int(min(255, g * 1.10)), int(min(255, b * 1.10)), 0]
        phase_name += f" [Overcast Frozen: {clouds}%]"

    return phase_name, col1, col2, col3, pwm, fx, sx, ix
