"""Responsive sizes for the expanded panel; the capsule is never scaled."""
def panel_metrics(width, height):
    scale = min(width / 520, max(1, height - 40) / 630)
    scale = max(0.40, min(1.60, scale))
    return scale
