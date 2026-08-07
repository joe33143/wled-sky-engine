def get_night_payload(moon_factor, clouds, is_stormy=False):
    c = max(clouds, 100 if is_stormy else 0) / 100.0
    moon_ceiling = 0.08  
    
    r = 4 + (moon_factor * 65 * moon_ceiling)
    g = 5 + (moon_factor * 68 * moon_ceiling)
    b = 7 + (moon_factor * 72 * moon_ceiling)
    
    dim = 1.0 - (c * 0.5)
    r = int(max(0, min(255, r * dim)))
    g = int(max(0, min(255, g * dim)))
    b = int(max(0, min(255, b * dim)))

    if (clouds >= 75 or is_stormy):
        grey = (r + g + b) // 3
        fade = 0.7 
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

    if is_stormy or clouds >= 75:
        fx = 88 
        sx = 40 if is_stormy else 25 
        ix = 150
        col2 = [int(r * 0.95), int(g * 0.95), int(b * 0.95), 0]
        col3 = [int(min(255, r * 1.30)), int(min(255, g * 1.15)), int(min(255, b * 1.00)), 0]
        phase_name += " [THUNDER STORM ACTIVE]" if is_stormy else f" [Overcast: {clouds}%]"

    elif clouds < 30:
        fx = 0
        sx = 128
        ix = 128 
        pal = 0
        phase_name += " [Clear Sky]"
    else:
        fx = 38
        sx = int(20 + (c * 50))  
        ix = 100
        col2 = [int(r * 0.95), int(g * 0.95), int(b * 0.95), 0]
        col3 = [int(min(255, r * 1.30)), int(min(255, g * 1.15)), int(min(255, b * 1.00)), 0]
        phase_name += f" [Rolling Clouds: {clouds}%]"
        
    return phase_name, col1, col2, col3, pwm, fx, sx, ix, pal
    
