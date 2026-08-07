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

    if clouds >= 75 and not is_stormy:
        grey = (r + g + b) // 3
        fade = ((clouds - 75) / 25.0) * 0.7 
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
    pal = 0
    phase_name = f"Night (Moon: {int(moon_factor * 100)}%)"

    if is_stormy:
        # --- CALCULATED NIGHT STORM ---
        fx = 57  
        sx = 220  
        ix = 200 
        pal = 0
        
        # Flash color (bright nighttime moon highlight)
        col1 = [min(255, int(r * 4.0)), min(255, int(g * 4.0)), min(255, int(b * 4.0)), 0]  
        # Background (very dark night color)
        col2 = [int(r * 0.2), int(g * 0.2), int(b * 0.2), 0]  
        
        phase_name += " [THUNDER STORM ACTIVE]"
        return phase_name, col1, col2, col3, pwm, fx, sx, ix, pal

    if clouds < 30:
        fx = 0
        sx = 128
        ix = 128 
        pal = 0
        phase_name += " [Clear Sky]"
    elif clouds < 75:
        fx = 38
        sx = int(20 + (c * 50))  
        ix = 100
        col2 = [int(r * 0.95), int(g * 0.95), int(b * 0.95), 0]
        col3 = [int(min(255, r * 1.30)), int(min(255, g * 1.15)), int(min(255, b * 1.00)), 0]
        phase_name += f" [Rolling Clouds: {clouds}%]"
    else:
        fx = 38
        sx = 15  
        ix = 100
        col2 = [int(r * 0.95), int(g * 0.95), int(b * 0.95), 0]
        col3 = [int(min(255, r * 1.30)), int(min(255, g * 1.15)), int(min(255, b * 1.00)), 0]
        phase_name += f" [Overcast Crawl: {clouds}%]"
        
    return phase_name, col1, col2, col3, pwm, fx, sx, ix, pal
    
