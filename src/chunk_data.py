# --- src/chunk_data.py ---
import numpy as np
from noise import pnoise2
import random

# Importiere alle nötigen IDs (inklusive ID_WATER)
from .block_definitions import (
    ID_AIR, ID_GRASS, ID_DIRT, ID_STONE,
    ID_OAK_LOG, ID_LEAVES, ID_SAND, ID_CACTUS, ID_WATER
)

# --- Globale Config ---
CHUNK_SIZE = 16
MAX_HEIGHT = 64
RENDER_DISTANCE_CHUNKS = 11 # 8

# Meeresspiegel (Alles darunter wird mit Wasser gefüllt)
SEA_LEVEL = 26

BLOCK_DATA_SHAPE = (CHUNK_SIZE + 2, MAX_HEIGHT, CHUNK_SIZE + 2)

# --- NOISE-SETTINGS ---
BASE_SCALE = 0.005
DETAIL_SCALE = 0.040
MAIN_OCTAVES = 5
MAIN_AMPLITUDE = MAX_HEIGHT * 0.6
FLAT_BASE_HEIGHT = 20
EXPONENT = 2.5

# --- BIOM SETTINGS ---
# Kleiner Scale = Große Biome.
BIOME_SCALE = 0.003
# Alles über 0.1 wird Wüste
BIOME_THRESHOLD = 0.1


def place_tree(block_data, x, z, y_surface):
    """Platziert einen einfachen Eichenbaum."""
    LOG_HEIGHT = 4
    CROWN_RADIUS = 2
    y_start = y_surface + 1
    top_log_y = y_start + LOG_HEIGHT

    # Stamm
    for y in range(y_start, top_log_y):
        if y < MAX_HEIGHT:
            block_data[x, y, z] = ID_OAK_LOG

    # Krone
    crown_center_y = top_log_y
    for cy in range(crown_center_y - 1, crown_center_y + 2):
        if cy >= MAX_HEIGHT: continue
        current_radius = CROWN_RADIUS if cy < crown_center_y + 1 else 1

        for cx in range(x - current_radius, x + current_radius + 1):
            for cz in range(z - current_radius, z + current_radius + 1):
                if 0 < cx < CHUNK_SIZE + 1 and 0 < cz < CHUNK_SIZE + 1:
                    # Nicht den Stamm überschreiben
                    if not (cx == x and cz == z):
                        # Nur in Luft platzieren (nicht Wasser oder Stein überschreiben)
                        if block_data[cx, cy, cz] == ID_AIR:
                            block_data[cx, cy, cz] = ID_LEAVES


def place_cactus(block_data, x, z, y_surface):
    """Platziert einen Kaktus (Höhe 1 bis 3)."""
    height = random.randint(1, 3)
    for i in range(height):
        y = y_surface + 1 + i
        if y < MAX_HEIGHT:
            # Nur in Luft platzieren
            if block_data[x, y, z] == ID_AIR:
                block_data[x, y, z] = ID_CACTUS


def generate_chunk_block_data(cx, cz):
    block_data = np.full(BLOCK_DATA_SHAPE, ID_AIR, dtype=np.float32)

    base_x = cx * CHUNK_SIZE - 1
    base_z = cz * CHUNK_SIZE - 1
    heightmap = {}
    biome_map = {}

    # 1. Terrain & Biome Map Generierung
    for x in range(CHUNK_SIZE + 2):
        for z in range(CHUNK_SIZE + 2):
            wx = base_x + x
            wz = base_z + z

            # --- BIOME NOISE ---
            biome_val = pnoise2(wx * BIOME_SCALE, wz * BIOME_SCALE, octaves=2, base=777)
            is_desert = biome_val > BIOME_THRESHOLD
            biome_map[(x, z)] = is_desert

            # --- HÖHEN NOISE ---
            base_noise_raw = pnoise2(wx * BASE_SCALE, wz * BASE_SCALE,
                                     octaves=MAIN_OCTAVES, repeatx=1024, repeaty=1024, base=111)
            detail_noise_raw = pnoise2(wx * DETAIL_SCALE, wz * DETAIL_SCALE,
                                       octaves=1, repeatx=1024, repeaty=1024, base=222)

            combined_noise = base_noise_raw * 0.7 + detail_noise_raw * 0.3
            normalized_noise = (combined_noise + 1.0) * 0.5
            exp_noise = normalized_noise ** EXPONENT
            final_height = exp_noise * MAIN_AMPLITUDE + FLAT_BASE_HEIGHT

            height = int(max(1.0, min(final_height, MAX_HEIGHT - 3))) + 3
            heightmap[(x, z)] = height

            # --- BLOCK FILLING ---
            for y in range(MAX_HEIGHT):
                # A) LANDSCHAFT (Solide Blöcke)
                if y < height:
                    if is_desert:
                        # Wüste: Sand oben, Sandstein/Stein darunter
                        if y >= height - 3:
                            block_data[x, y, z] = ID_SAND
                        else:
                            block_data[x, y, z] = ID_STONE
                    else:
                        # STRAND-CHECK: Ist die Oberfläche nah am Wasser?
                        # Wenn ja -> Sand statt Gras/Erde
                        is_beach = (height <= SEA_LEVEL + 2)

                        if is_beach:
                            if y >= height - 2:
                                block_data[x, y, z] = ID_SAND
                            else:
                                block_data[x, y, z] = ID_STONE
                        else:
                            # Normales Grasland/Gebirge
                            if y == height - 1:
                                block_data[x, y, z] = ID_GRASS
                            elif y >= height - 4:
                                block_data[x, y, z] = ID_DIRT
                            else:
                                block_data[x, y, z] = ID_STONE

                # B) WASSER (Füllt Luft unter dem Meeresspiegel auf)
                elif y <= SEA_LEVEL:
                    # Wenn hier noch nichts ist (Luft), dann mach Wasser rein
                    if block_data[x, y, z] == ID_AIR:
                        block_data[x, y, z] = ID_WATER

    # 2. Vegetation (Bäume und Kakteen)
    TREE_PROBABILITY = 0.20
    CACTUS_PROBABILITY = 0.15
    SAFETY_MARGIN = 2

    for x in range(1, CHUNK_SIZE + 1):
        for z in range(1, CHUNK_SIZE + 1):

            if (x < SAFETY_MARGIN or x > CHUNK_SIZE + 1 - SAFETY_MARGIN or
                    z < SAFETY_MARGIN or z > CHUNK_SIZE + 1 - SAFETY_MARGIN):
                continue

            wx = base_x + x
            wz = base_z + z

            # Oberfläche bestimmen (Höchster Block - 1)
            y_surface = heightmap[(x, z)] - 1

            # WICHTIG: Keine Vegetation unter Wasser!
            if y_surface < SEA_LEVEL:
                continue

            is_desert = biome_map[(x, z)]

            if is_desert:
                # KAKTUS (Nur auf Sand)
                if block_data[x, y_surface, z] == ID_SAND:
                    chance = (pnoise2(wx * 0.5, wz * 0.5, base=888) + 1) * 0.5
                    if chance < CACTUS_PROBABILITY:
                        place_cactus(block_data, x, z, y_surface)
            else:
                # BAUM (Nur auf Gras)
                # Durch die Strand-Logik wachsen Bäume jetzt automatisch nicht mehr am Strand,
                # da dort Sand liegt, kein Gras.
                if block_data[x, y_surface, z] == ID_GRASS:
                    chance = (pnoise2(wx * 0.2, wz * 0.2, base=999) + 1) * 0.5
                    if chance < TREE_PROBABILITY:
                        place_tree(block_data, x, z, y_surface)

    return block_data