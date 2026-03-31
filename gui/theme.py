"""Color palette and shared style constants."""

PALETTE = {
    "bg":           "#0F1923",
    "surface":      "#172A3A",
    "surface_alt":  "#1E3448",
    "accent":       "#00D4AA",
    "accent_hover": "#00B894",
    "danger":       "#FF6B6B",
    "danger_hover": "#EE5A5A",
    "warn":         "#FDCB6E",
    "text":         "#E8EDF2",
    "text_dim":     "#8899AA",
    "border":       "#2A4054",
    "card_bg":      "#1B3244",
}

# Shorthand
P = PALETTE


def severity_color(dias) -> str:
    try:
        d = int(dias)
    except (ValueError, TypeError):
        return P["text_dim"]
    return P["danger"] if d > 120 else P["warn"] if d > 90 else P["accent"]


def confidence_color(conf: str) -> str:
    return {"alta": P["accent"], "media": P["warn"]}.get(conf, P["danger"])


def status_color(status: str) -> str:
    s = status.lower()
    if any(w in s for w in ("done", "termin", "conclu", "fechad")):
        return P["accent"]
    return P["warn"]
