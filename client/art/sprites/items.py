"""Small item/UI sprites as character grids."""

SEED = [  # 16x16 gacha seed; frames 1-2 are cracking (light colour drawn by code)
    [
        "................",
        "................",
        "................",
        "......kkkk......",
        ".....kOooOk.....",
        "....kOooooOk....",
        "....koooWooOk...",
        "...kooooWooOk...",
        "...kOoooooooOk..",
        "...kOooooooOOk..",
        "...kOOoooooOOk..",
        "....kOOooOOOk...",
        ".....kOOOOOk....",
        "......kkkkk.....",
        "................",
        "................",
    ],
]
SEED.append([r for r in SEED[0]])
SEED[1][5] = "....kOooOooOk..."
SEED[1][6] = "....koookoWOk..."
SEED[1][7] = "...koooWkoooOk.."
SEED[1][8] = "...kOookooooOk.."
SEED.append([r for r in SEED[1]])
SEED[2][4] = ".....kOo.Ok....."
SEED[2][5] = "....kOoo..oOk..."
SEED[2][6] = "....kooo.koOOk.."
SEED[2][7] = "...koook..ooOk.."

STONE = [  # 8x8 Linh Thạch icon
    "...kk...",
    "..kaWk..",
    ".kaaAAk.",
    "kaWaAAqk",
    "kaaAAqqk",
    ".kAAqqk.",
    "..kqqk..",
    "...kk...",
]
FRUIT = [  # 8x8 fruit icon (colour swapped for rarity)
    "....n...",
    "...nV...",
    "..kkkk..",
    ".kooooOk",
    "koWooooO",
    "kooooooO",
    ".kOooOOk",
    "..kkkk..",
]
SEED_ICON = [
    "........",
    "...kk...",
    "..kOok..",
    ".kOooOk.",
    ".koWoOk.",
    ".kOooOk.",
    "..kOOk..",
    "...kk...",
]
