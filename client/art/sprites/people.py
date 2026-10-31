"""Character sprites as character grids (16x24). Keys come from art/palette.py, '.' is
transparent. The body is built from an upper half per direction plus a leg strip per
walk frame; hair is a separate overlay so every player can pick colour and style.
'left' is 'right' mirrored."""

HEAD_DOWN = [
    "................",
    "................",
    "....kkkkkkkk....",
    "...kssssssssk...",
    "...kssssssssk...",
    "...kssssssssk...",
    "...kskssssksk...",
    "...kssssssssk...",
    "...ksssSSsssk...",
    "....kssssssk....",
    ".....kkkkkk.....",
]
TORSO_DOWN = [
    "....kCccccCk....",
    "...kccCccCcck...",
    "..ksccccccccsk..",
    "..ksccccccccsk..",
    "..kSbbbbbbbbSk..",
    "...kcCccccCck...",
    "...kcccccccck...",
]
HEAD_UP = [
    "................",
    "................",
    "....kkkkkkkk....",
    "...kssssssssk...",
    "...kssssssssk...",
    "...kssssssssk...",
    "...kssssssssk...",
    "...kssssssssk...",
    "...kssssssssk...",
    "....kssssssk....",
    ".....kkkkkk.....",
]
TORSO_UP = [
    "....kcccccck....",
    "...kcccccccck...",
    "..ksccccccccsk..",
    "..ksccccccccsk..",
    "..kSbbbbbbbbSk..",
    "...kcccccccck...",
    "...kcccccccck...",
]
HEAD_RIGHT = [
    "................",
    "................",
    ".....kkkkkkk....",
    "....ksssssssk...",
    "....ksssssssk...",
    "....ksssssssk...",
    "....ksssssksk...",
    "....kssssssssk..",
    "....ksssssssk...",
    ".....ksssssk....",
    "......kkkkk.....",
]
TORSO_RIGHT = [
    ".....kcccck.....",
    "....kcccCcck....",
    "....kccsccck....",
    "....kccsccck....",
    "....kbbSbbbk....",
    "....kcccccck....",
    "....kcccccck....",
]
LEGS_FRONT = [
    [  # standing
        "....kppkkppk....",
        "....kppkkppk....",
        "....kppkkppk....",
        "....kppkkppk....",
        "....kffkkffk....",
        "....kkkkkkkk....",
    ],
    [  # left foot up
        "....kppkkppk....",
        "....kppkkppk....",
        "....kppkkppk....",
        "....kffkkppk....",
        "....kkk.kffk....",
        "........kkkk....",
    ],
    [  # right foot up
        "....kppkkppk....",
        "....kppkkppk....",
        "....kppkkppk....",
        "....kppkkffk....",
        "....kffk.kkk....",
        "....kkkk........",
    ],
]
LEGS_SIDE = [
    [
        ".....kppppk.....",
        ".....kppppk.....",
        ".....kppppk.....",
        ".....kppppk.....",
        ".....kfffffk....",
        ".....kkkkkkk....",
    ],
    [
        ".....kppppk.....",
        "....kpp.kppk....",
        "....kpp.kppk....",
        "...kpp...kppk...",
        "...kffk..kfffk..",
        "...kkk...kkkkk..",
    ],
]
SKIRT_FRONT = "...kcccccccck..."   # nữ: the robe reaches lower
SKIRT_SIDE = "....kcccccck...."

# Hair overlays (rows 0-14 of the 24-row sprite).
HAIR = {
    "ngan": {
        "down": [
            "................",
            "................",
            "....kkkkkkkk....",
            "....HHHHHHHH....",
            "....HHHHHHHH....",
            "....HhHHHHhH....",
            "....H......H....",
            "....h......h....",
        ],
        "up": [
            "................",
            "................",
            "....kkkkkkkk....",
            "....HHHHHHHH....",
            "....HHHHHHHH....",
            "....HHHHHHHH....",
            "....HHHHHHHH....",
            "....HHHHHHHH....",
            "....hHHHHHHh....",
            ".....hHHHHh.....",
        ],
        "right": [
            "................",
            "................",
            ".....kkkkkkk....",
            ".....HHHHHHH....",
            ".....HHHHHHH....",
            ".....HHHHHh.....",
            ".....HHH........",
            ".....HH.........",
            ".....h..........",
        ],
    },
}
_BUN_TOP = {
    "down": ["......kkkk......", ".....kHHHHk.....", "....kkHHHHkk...."],
    "up": ["......kkkk......", ".....kHHHHk.....", "....kkHHHHkk...."],
    "right": ["....kkk.........", "...kHHHk........", "...kHHkkkkkk...."],
}


def _with_rows(base: list[str], rows: dict[int, str]) -> list[str]:
    out = list(base) + ["." * 16] * (15 - len(base))
    for i, r in rows.items():
        out[i] = r
    return out


HAIR["buoi"] = {d: _with_rows(HAIR["ngan"][d], dict(enumerate(_BUN_TOP[d]))) for d in ("down", "up", "right")}
HAIR["dai"] = {
    "down": _with_rows(HAIR["ngan"]["down"], {r: "...HH......HH..." for r in range(6, 14)} | {14: "...hh......hh..."}),
    "up": _with_rows(HAIR["ngan"]["up"], {r: "....HHHHHHHH...." for r in range(10, 15)}),
    "right": _with_rows(HAIR["ngan"]["right"], {r: "....HH.........." for r in range(6, 14)} | {14: "....hh.........."}),
}

TRUC_LAO = [  # the old panda calligrapher (spec 18)
    "................",
    "...kk......kk...",
    "..kKKk....kKKk..",
    "..kKKkkkkkkKKk..",
    "...kWWWWWWWWk...",
    "..kWWWWWWWWWWk..",
    "..kWKKWWWWKKWk..",
    "..kWKwWWWWwKWk..",
    "..kWWWWKKWWWWk..",
    "..kWWWWWWWWWWk..",
    "...kWWWkkWWWk...",
    "....kkkkkkkk....",
    "...kVVVwwVVVkb..",
    "..kKVVVwwVVVKbk.",
    "..kKVVVVVVVVKbk.",
    "..kKKbbbbbbKKbk.",
    "...kVVVVVVVVkkk.",
    "...kVVVVVVVVk...",
    "...kVVVVVVVVk...",
    "...kVnVVVVnVk...",
    "....kKKkkKKk....",
    "....kKKkkKKk....",
    "....kkkkkkkk....",
    "................",
]
TRUC_LAO_BLINK = TRUC_LAO[:7] + ["..kWKKWWWWKKWk.."] + TRUC_LAO[8:]

HORSE = [  # 24x16, facing right (tone-mishap gag: 马 vs 妈)
    [
        "........................",
        "...................kk...",
        "..................kbbk..",
        ".................kbbbbk.",
        "................kbbkbbBk",
        "...kkk.........kbbbbbbBk",
        "..kDDDk.......kbbbbkkkk.",
        ".kDk.kbkkkkkkkbbbbk.....",
        ".k..kbbbbbbbbbbbbbk.....",
        "....kbbbbbbbbbbbbbk.....",
        "....kbbbbbbbbbbbbk......",
        "....kbbkkkkkkkbbbk......",
        "....kbk.......kbk.......",
        "...kbk.........kbk......",
        "...kDk.........kDk......",
        "...kk...........kk......",
    ],
    [
        "........................",
        "...................kk...",
        "..................kbbk..",
        ".................kbbbbk.",
        "................kbbkbbBk",
        "....kkk........kbbbbbbBk",
        "...kDDDk......kbbbbkkkk.",
        "..kDk.kbkkkkkkbbbbk.....",
        "..k..kbbbbbbbbbbbbk.....",
        ".....kbbbbbbbbbbbbk.....",
        ".....kbbbbbbbbbbbk......",
        ".....kbbkkkkkkkbbk......",
        ".....kbk......kbk.......",
        ".....kbk.....kbk........",
        ".....kDk.....kDk........",
        ".....kk......kk.........",
    ],
]
