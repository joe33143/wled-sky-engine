# night_effects.py

def get_night_payload(moon_factor, clouds):
    """Generates the colors and animations for the deep night phase."""
    c = clouds / 100.0
    moon_ceiling = 0.08  
    
    r = 4 + (moon_factor * 65 * moon_ceiling)
    g = 5 + (moon_factor * 68 * moon_ceiling)
    b = 7 + (moon_factor * 72 * moon_ceiling)
    
    dim = 1.0 - (c * 0.5)
    r = int(max(0, min(255, r * dim)))
    g = int(max(0, min(255, g * dim)))
    b = int(max(0, min(255, b * dim)))
    
    pwm = 0
    col1 = [r, g, b, 0]
    col2 = [0, 0, 0, 0]
    col3 = [0, 0, 0, 0]
    fx = 0
    sx = 128
    ix = 128
    phase_name = f"Night (Moon: {int(moon_factor * 100)}%)"

    # --- EFFECT 3-TIER SELECTION ---
    if clouds < 25:
        # Clear Night: Glitter Effect
        fx = 73
        sx = 40
        ix = 180 
        col2 = [255, 105, 180, 0]  # Pink Glitter
        col3 = [138, 43, 226, 0]   # Purple/Blue Glitter
        phase_name += " [Glitter Active]"
        
    elif clouds < 85:
        # Broken Clouds: Moonlight peeking through
        fx = 38
        sx = int(20 + (c * 50))  
        ix = 150
        col2 = [int(r * 0.7), int(g * 0.7), int(b * 0.7), 0]
        col3 = [int(min(255, r * 1.2)), int(min(255, g * 1.2)), int(min(255, b * 1.3)), 0]
        phase_name += f" [Rolling Clouds: {clouds}%]"
        
    else:
        # Overcast Night: Flat, dark, diffused
        fx = 0
        phase_name += f" [Overcast Solid: {clouds}%]"
        
    return phase_name, col1, col2, col3, pwm, fx, sx, ix
