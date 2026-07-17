# day_effects.py

# Notice the 7th argument added here: is_stormy=False
def get_day_payload(r, g, b, pwm, clouds, base_phase_name, is_stormy=False):
    """Applies daytime animations, desaturation, and thunderstorms."""
    c = clouds / 100.0
    
    if clouds >= 75:
        grey = (r + g + b) // 3
        fade = (clouds - 75) / 25.0 
        r = int(r + (grey - r) * fade)
        g = int(g + (grey - g) * fade)
        b = int(b + (grey - b) * fade)

    col1 = [r, g, b, 0]
    fx = 0
    sx = 128
    ix = 128
    col2 = [0, 0, 0, 0]
    col3 = [0, 0, 0, 0]
    phase_name = base_phase_name

    # --- STORM OVERRIDE ---
    if is_stormy:
        fx = 43  # WLED Lightning
        sx = 60  # Lower frequency (distant, occasional strikes)
        ix = 100 # Softer, smoother fade out
        col1 = [60, 90, 130, 0]  # Faint, muted electric blue
        col2 = [int(r * 0.15), int(g * 0.15), int(b * 0.15), 0]  # Very dark daylight background
        pwm = int(pwm * 0.15)
        phase_name += " [DISTANT STORM ACTIVE]"
        return phase_name, col1, col2, col3, pwm, fx, sx, ix
    
    # --- NORMAL EFFECT 3-TIER SELECTION ---
    if clouds < 30:
        phase_name += " [Clear Sky]"
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
