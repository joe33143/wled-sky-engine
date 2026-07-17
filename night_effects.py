# night_effects.py

# Notice the 3rd argument added here: is_stormy=False
def get_night_payload(moon_factor, clouds, is_stormy=False):
    """Generates animations and thunderstorms for the deep night phase."""
    c = clouds / 100.0
    moon_ceiling = 0.08  
    
    r = 4 + (moon_factor * 65 * moon_ceiling)
    g = 5 + (moon_factor * 68 * moon_ceiling)
    b = 7 + (moon_factor * 72 * moon_ceiling)
    
    dim = 1.0 - (c * 0.5)
    r = int(max(0, min(255, r * dim)))
    g = int(max(0, min(255, g * dim)))
    b = int(max(0, min(255, b * dim)))

    if clouds >= 75:
        grey = (r + g + b) // 3
        fade = (clouds - 75) / 25.0
        r = int(r + (grey - r) * fade)
        g = int(g + (grey - g) * fade)
        b = int(b + (grey - b) * fade)
    
    pwm = 0
    col1 = [r, g, b, 0]
    col2 = [0, 0, 0, 0]
    col3 = [0, 0, 0, 0]
    fx = 0
    sx = 128
    ix = 128
    phase_name = f"Night (Moon: {int(moon_factor * 100)}%)"

    # --- STORM OVERRIDE ---
    if is_stormy:
        fx = 43  
        sx = 40  # Very occasional distant flashes
        ix = 100 # Gentle fade
        col1 = [30, 50, 80, 0]  # Whisper-faint blue plasma
        col2 = [1, 1, 2, 0]  # Barely-there background
        phase_name += " [DISTANT STORM ACTIVE]"
        return phase_name, col1, col2, col3, pwm, fx, sx, ix

    # --- NORMAL EFFECT 3-TIER SELECTION ---
    if clouds < 30:
        fx = 73
        sx = 40
        ix = 180 
        col2 = [255, 105, 180, 0]  
        col3 = [138, 43, 226, 0]   
        phase_name += " [Glitter Active]"
    elif clouds < 75:
        fx = 38
        sx = int(20 + (c * 50))  
        ix = 100
        col2 = [int(r * 0.85), int(g * 0.85), int(b * 0.85), 0]
        col3 = [int(min(255, r * 1.10)), int(min(255, g * 1.10)), int(min(255, b * 1.10)), 0]
        phase_name += f" [Rolling Clouds: {clouds}%]"
    else:
        fx = 38
        sx = 0  
        ix = 100
        col2 = [int(r * 0.85), int(g * 0.85), int(b * 0.85), 0]
        col3 = [int(min(255, r * 1.10)), int(min(255, g * 1.10)), int(min(255, b * 1.10)), 0]
        phase_name += f" [Overcast Frozen: {clouds}%]"
        
    return phase_name, col1, col2, col3, pwm, fx, sx, ix
