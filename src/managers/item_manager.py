# --- src/managers/item_manager.py ---
import math
import random
import numpy as np
from src.block_definitions import ID_AIR, NON_SOLID_BLOCKS_NUMBA
from src.chunk_data import CHUNK_SIZE # Hinzufügen

# --- EINSTELLUNGEN ---
MAX_ITEMS = 200  # Maximale Anzahl an Items gleichzeitig (Schutz vor Lag)
DESPAWN_TIME = 60.0  # Sekunden, bis ein Item verschwindet
MAGNET_RANGE = 3.0  # Ab wie vielen Blöcken fliegt das Item zum Spieler
PICKUP_RANGE = 1.5  # Ab wann gilt es als "eingesammelt"


class DroppedItem:
    def __init__(self, block_id, position):
        self.block_id = block_id
        self.pos = np.array(position, dtype=np.float32)

        # Kleiner "Pop" nach oben beim Spawnen
        self.velocity = np.array([
            random.uniform(-1.5, 1.5),
            3.5,
            random.uniform(-1.5, 1.5)
        ], dtype=np.float32)

        self.scale = 0.25
        self.rotation = random.random() * 360.0
        self.age = 0.0
        self.is_dead = False

    def update(self, dt, player_pos, world_data):  # world_data HINZUFÜGEN
        self.age += dt

        if self.age > DESPAWN_TIME:
            self.is_dead = True
            return

        # 1. Magnet-Effekt (Beibehalten)
        dist_sq = np.sum((self.pos - player_pos) ** 2)
        if dist_sq < MAGNET_RANGE ** 2:
            direction = player_pos - self.pos
            direction[1] += 0.5
            length = np.linalg.norm(direction)
            if length > 0:
                direction /= length
                speed = 10.0 * (1.0 - (dist_sq / (MAGNET_RANGE ** 2))) + 2.0
                self.velocity += direction * speed * dt

        # 2. Physik und Kollision (NEU/GEÄNDERT)
        self.velocity[1] -= 25.0 * dt  # Schwerkraft
        self.velocity *= 0.95  # Luftwiderstand

        # Provisorischer Positions-Update für Kollision
        new_pos = self.pos + self.velocity * dt

        # Kollisions-Check: Wir checken nur den Boden unter dem Item
        # (Dies ist eine sehr vereinfachte Box-Kollision)

        # Position des Blocks direkt unter dem Item (Y-1)
        block_x = int(np.floor(new_pos[0]))
        block_y = int(np.floor(new_pos[1] - 0.1))  # 0.1 Puffer unter dem Item
        block_z = int(np.floor(new_pos[2]))

        cx = int(np.floor(block_x / CHUNK_SIZE))
        cz = int(np.floor(block_z / CHUNK_SIZE))

        coord = (cx, cz)

        if coord in world_data:
            chunk = world_data[coord]
            # Lokale Indizes (Padding beachten: +1)
            lx = block_x - cx * CHUNK_SIZE + 1
            lz = block_z - cz * CHUNK_SIZE + 1

            # Überprüfen, ob der Block unter dem Item solide ist
            if 0 <= lx < CHUNK_SIZE + 2 and 0 <= block_y < chunk.shape[1] and 0 <= lz < CHUNK_SIZE + 2:
                block_id = chunk[lx, block_y, lz]

                # Prüfe, ob der Block solide ist (Nicht Luft oder Blätter)
                if block_id != ID_AIR and block_id not in NON_SOLID_BLOCKS_NUMBA:
                    # Kollision mit dem Boden! Setze Y auf die Oberfläche des Blocks
                    self.pos[1] = block_y + 1.0  # Oberfläche ist Y+1
                    self.velocity[1] = 0.0  # Vertikal-Geschw. stoppen

                    # Horizontale Geschw. dämpfen (Reibung am Boden)
                    self.velocity[0] *= 0.5
                    self.velocity[2] *= 0.5

                    # Führe den Update nicht fort, wenn Kollision stattfand
                    self.rotation += 90.0 * dt
                    return

                    # Wenn keine Kollision, Position normal updaten
        self.pos = new_pos

        # Rotation für Visuals
        self.rotation += 90.0 * dt


class ItemManager:
    def __init__(self, item_renderer):
        self.item_renderer = item_renderer
        self.items = []
        print(f"📦 ItemManager V2 (Optimized) initialisiert.")

    def spawn_item(self, block_id, position):
        if block_id == ID_AIR: return

        # PERFORMANCE-SCHUTZ: Wenn zu viele Items da sind, lösche das älteste!
        if len(self.items) >= MAX_ITEMS:
            self.items.pop(0)

        self.items.append(DroppedItem(block_id, position))

    def update(self, dt, player_pos, world_data):  # world_data HINZUFÜGEN
        collected_items = []

        for i in range(len(self.items) - 1, -1, -1):
            item = self.items[i]
            # world_data übergeben
            item.update(dt, player_pos, world_data)

            # ... (Pickup-Logik beibehalten) ...
            dist_sq = np.sum((item.pos - player_pos) ** 2)
            if dist_sq < PICKUP_RANGE ** 2:
                item.is_dead = True
                collected_items.append(item.block_id)

            if item.is_dead:
                self.items.pop(i)

        return collected_items

    def render(self, view, proj, textures):
        self.item_renderer.render_items(self.items, view, proj, textures)