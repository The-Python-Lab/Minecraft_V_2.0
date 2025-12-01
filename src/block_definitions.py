# --- src/block_definitions.py ---
import numpy as np

# --- Block-IDs ---
ID_AIR = -1.0
ID_GRASS = 0.0
ID_DIRT = 1.0
ID_STONE = 2.0
ID_OAK_LOG = 3.0
ID_LEAVES = 4.0
ID_SAND = 5.0
ID_CACTUS = 6.0
ID_WATER = 7.0  # <--- ID 7

# --- Textur-Indizes (MÜSSEN LÜCKENLOS SEIN!) ---
TEX_INDEX_GRASS_TOP = 0.0
TEX_INDEX_GRASS_SIDE = 1.0
TEX_INDEX_DIRT = 2.0
TEX_INDEX_STONE = 3.0
TEX_INDEX_LOG_SIDE = 4.0
TEX_INDEX_LOG_TOP = 5.0
TEX_INDEX_LEAVES = 6.0
TEX_INDEX_SAND = 7.0
TEX_INDEX_CACTUS_SIDE = 8.0
TEX_INDEX_CACTUS_TOP = 9.0
TEX_INDEX_HOTBAR = 10.0
TEX_INDEX_WATER = 11.0  # <--- Das ist die 12. Textur (Zählung beginnt bei 0)

# --- Numba Arrays ---
# ID_WATER muss hier drin sein, damit man durchlaufen kann
NON_SOLID_BLOCKS_NUMBA = np.array([ID_AIR, ID_LEAVES, ID_WATER], dtype=np.float32)

OAK_LOG_TEXTURES = np.array([
    TEX_INDEX_LOG_TOP, TEX_INDEX_LOG_TOP,
    TEX_INDEX_LOG_SIDE, TEX_INDEX_LOG_SIDE,
    TEX_INDEX_LOG_SIDE, TEX_INDEX_LOG_SIDE
], dtype=np.float32)

GRASS_TEXTURES = np.array([
    TEX_INDEX_GRASS_TOP, TEX_INDEX_DIRT,
    TEX_INDEX_GRASS_SIDE, TEX_INDEX_GRASS_SIDE,
    TEX_INDEX_GRASS_SIDE, TEX_INDEX_GRASS_SIDE
], dtype=np.float32)

CACTUS_TEXTURES = np.array([
    TEX_INDEX_CACTUS_TOP, TEX_INDEX_CACTUS_TOP,
    TEX_INDEX_CACTUS_SIDE, TEX_INDEX_CACTUS_SIDE,
    TEX_INDEX_CACTUS_SIDE, TEX_INDEX_CACTUS_SIDE
], dtype=np.float32)

# Wasser Texturen
WATER_TEXTURES = np.array([
    TEX_INDEX_WATER, TEX_INDEX_WATER,
    TEX_INDEX_WATER, TEX_INDEX_WATER,
    TEX_INDEX_WATER, TEX_INDEX_WATER
], dtype=np.float32)

# --- Texture Config ---
# WICHTIG: Prüfe, ob "assets/water.png" wirklich existiert!
TEXTURE_CONFIG = {
    TEX_INDEX_GRASS_TOP: "assets/grass.png",
    TEX_INDEX_GRASS_SIDE: "assets/grass_side.png",
    TEX_INDEX_DIRT: "assets/dirt.png",
    TEX_INDEX_STONE: "assets/stone.png",
    TEX_INDEX_LOG_SIDE: "assets/oak_log.png",
    TEX_INDEX_LOG_TOP: "assets/oak_log_top.png",
    TEX_INDEX_LEAVES: "assets/leaves.png",
    TEX_INDEX_SAND: "assets/sand.png",
    TEX_INDEX_CACTUS_SIDE: "assets/cactus_side_3.png",
    TEX_INDEX_CACTUS_TOP: "assets/cactus_top_2.png",
    TEX_INDEX_HOTBAR: "assets/hotbar.png",
    TEX_INDEX_WATER: "assets/water.png",  # <--- Datei muss da sein
}

BLOCK_HARDNESS = {
    ID_GRASS: 0.6,
    ID_DIRT: 0.5,
    ID_STONE: 1.5,
    ID_OAK_LOG: 2.0,
    ID_LEAVES: 0.2,
    ID_SAND: 0.5,
    ID_CACTUS: 0.4,
    ID_WATER: 0.0,
    ID_AIR: 0.0
}

DEFAULT_HARDNESS = 1.0

def get_texture_paths():
    sorted_keys = sorted(TEXTURE_CONFIG.keys())
    return [TEXTURE_CONFIG[key] for key in sorted_keys]