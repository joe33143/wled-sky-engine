# night_effects.py

def get_night_payload(moon_factor, clouds):
    """Generates the colors and animations for the deep night phase."""
    c = clouds / 100.0
    moon_ceiling = 0.08  # 8% max brightness for full moon
    
    # Calculate silver moonlight baseline
    r = 4 + (moon_factor * 65 * moon_ceiling)
    g = 5 + (moon_factor * 68 * moon_ceiling)
    b = 7 + (moon_factor * 72 * moon_ceiling)
    
    # Apply standard cloud dimming
    dim = 1.0 - (c * 0.5)
    r = int(max(0, min(255, r * dim)))
    g = int(max(0, min(255, g * dim)))
    b = int(max(0, min(255, b * dim)))
    
    pwm = 0
    col1 = [r, g, b, 0]
    phase_name = f"Night (Moon: {int(moon_factor * 100)}%)"

    # --- EFFECT SELECTION ---
    if clouds < 30:
        # Clear Night: Glitter Effect
        fx = 73
        sx = 40   # Slow twinkle
        ix = 180  # High density
        col2 = [255, 105, 180, 0]  # Pink Glitter Highlights
        col3 = [138, 43, 226, 0]   # Purple/Blue Glitter Highlights
        phase_name += " [Glitter Active]"
    else:
        # Cloudy Night: Aurora Effect (Updated for WLED 16)
        fx = 38
        sx = int(20 + (c * 50))  # Rolls faster with more clouds
        ix = 150
        # Generate shadow and moonlit highlights dynamically
        col2 = [int(r * 0.7), int(g * 0.7), int(b * 0.7), 0]
        col3 = [int(min(255, r * 1.2)), int(min(255, g * 1.2)), int(min(255, b * 1.3)), 0]
        phase_name += f" [Rolling Clouds: {clouds}%]"
        
    return phase_name, col1, col2, col3, pwm, fx, sx, ix
