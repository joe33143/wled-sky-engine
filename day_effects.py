# day_effects.py

def get_day_payload(r, g, b, pwm, clouds, base_phase_name, is_stormy=False):
    """Applies daytime animations with warmer highlights and PWM fill."""
    c = clouds / 100.0
    
    # Limit the desaturation so it never goes completely flat grey. 
    # It will retain at least 30% of its original warm daytime color even at 100% clouds.
    if clouds >= 75:
        grey = (r + g + b) // 3
        fade = ((clouds - 75) / 25.0) * 0.7 
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

    if is_stormy:
        fx = 43  
        sx = 60  
        ix = 100 
        col1 = [60, 90, 130, 0]  
        col2 = [int(r * 0.15), int(g * 0.15), int(b * 0.15), 0]  
        pwm = max(int(pwm * 0.15), 10) # Minimum 4% fill so it isn't pitch black
        phase_name += " [DISTANT STORM ACTIVE]"
        return phase_name, col1, col2, col3, pwm, fx, sx, ix
    
    if clouds < 30:
        phase_name += " [Clear Sky]"
        
    elif clouds < 75:
        fx = 38
        sx = int(20 + (c * 50)) 
        ix = 100 
        # Base is much brighter (95% instead of 85%)
        col2 = [int(r * 0.95), int(g * 0.85), int(b * 0.70), 0]
        # Highlights are skewed to push warmer tones (130% Red, 115% Green, 100% Blue)
        col3 = [int(min(255, r * 2.6)), int(min(255, g * 1.5)), int(min(255, b * 1.00)), 0]
        
        # Add 6% PWM fill light to brighten the tank
        pwm = max(pwm, 8) 
        phase_name += f" [Rolling Clouds: {clouds}%]"
        
    else:
        fx = 38
        sx = 10  # Slow crawl instead of frozen 0
        ix = 100
        col2 = [int(r * 0.95), int(g * 0.85), int(b * 0.70), 0]
        col3 = [int(min(255, r * 2.6)), int(min(255, g * 1.5)), int(min(255, b * 1.00)), 0]
        
        # Add 10% PWM fill light to punch through the heavy overcast
        pwm = max(pwm, 25) 
        phase_name += f" [Overcast Crawl: {clouds}%]"

    return phase_name, col1, col2, col3, pwm, fx, sx, ix
