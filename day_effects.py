# day_effects.py

def get_day_payload(r, g, b, pwm, clouds, base_phase_name):
    """Applies daytime animations based on broken clouds vs total overcast."""
    c = clouds / 100.0
    col1 = [r, g, b, 0]
    
    # Default state for Clear or Overcast skies
    fx = 0
    sx = 128
    ix = 128
    col2 = [0, 0, 0, 0]
    col3 = [0, 0, 0, 0]
    phase_name = base_phase_name
    
    # --- EFFECT 3-TIER SELECTION ---
    if clouds < 25:
        phase_name += " [Clear Sky]"
        
    elif clouds < 85:
        # Broken Clouds: Sun is peeking through, trigger rolling shadows (WLED 16 Aurora)
        fx = 38
        sx = int(20 + (c * 50)) 
        ix = 150 
        col2 = [int(r * 0.7), int(g * 0.7), int(b * 0.7), 0] # 30% Darker
        col3 = [int(min(255, r * 1.2)), int(min(255, g * 1.2)), int(min(255, b * 1.3)), 0] # 20% Brighter
        phase_name += f" [Rolling Clouds: {clouds}%]"
        
    else:
        # Overcast: Solid, flat, diffused sky. No sun peeking through.
        fx = 0
        phase_name += f" [Overcast Solid: {clouds}%]"

    return phase_name, col1, col2, col3, pwm, fx, sx, ix
