"""Fixed ~32-colour palette: ink-wash + pastel (spec 18). Sprite grids use the one-letter
keys below; '.' is transparent."""

PALETTE = {
    # ink & paper
    "k": "#2B2B2B",  # ink (outlines)
    "K": "#1A1A1A",  # deep ink
    "w": "#F4EBD9",  # rice paper
    "W": "#FFFFFF",
    "g": "#9A9A9A",  # light grey
    "G": "#5A5A5A",  # grey
    # skin
    "s": "#F2C9A0",
    "S": "#D9A27A",
    # hair placeholders (recoloured per character)
    "H": "#2B2B2B",
    "h": "#1A1A1A",
    # cloth: Áo Vải Phàm Nhân (undyed linen)
    "c": "#D8CBB0",
    "C": "#B8A988",
    "p": "#7D6E57",  # trousers
    "f": "#4A3B2A",  # shoes
    # wood / earth
    "b": "#8B5A2B",
    "B": "#B07A45",
    "d": "#7A5230",  # soil
    "D": "#5A3A1E",  # soil dark
    "e": "#9C6B3E",  # soil light
    "y": "#C9B48A",  # path
    "Y": "#A8946A",  # path dark
    # greens
    "l": "#B5D67A",  # leaf light
    "v": "#8DB360",  # grass
    "V": "#6A994E",  # bamboo green
    "n": "#4F7A3A",  # deep green
    # water
    "a": "#8CB8DA",
    "A": "#5B8DB8",
    "q": "#3E6A90",
    # stone
    "t": "#B4B4AC",
    "T": "#8C8C8C",
    # accents
    "r": "#BC4749",  # vermilion
    "R": "#8E3537",
    "o": "#E9C46A",  # gold
    "O": "#C99A3A",
    "i": "#E89AB0",  # blossom pink
    "u": "#4A7CC8",  # rare blue
    "m": "#8E5AC8",  # epic purple
}

RARITY_COLORS = {"common": "#9A9A9A", "rare": "#4A7CC8", "epic": "#8E5AC8", "legendary": "#E9C46A"}

UI = {
    "paper": "#F4EBD9", "paper_dark": "#E3D5BA", "ink": "#2B2B2B", "ink_soft": "#5A5A5A",
    "accent": "#BC4749", "gold": "#E9C46A", "green": "#6A994E", "blue": "#4A7CC8",
    "shadow": (0, 0, 0, 110), "panel_edge": "#8B5A2B",
}


def rgb(hex_or_key: str) -> tuple[int, int, int]:
    h = PALETTE.get(hex_or_key, hex_or_key).lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def shade(hex_color: str, factor: float) -> str:
    r, g, b = rgb(hex_color)
    return "#%02X%02X%02X" % tuple(max(0, min(255, int(c * factor))) for c in (r, g, b))
