# --- src/managers/chunk_manager.py ---
import concurrent.futures
import numpy as np
from OpenGL.GL import *
from src.chunk_data import CHUNK_SIZE, MAX_HEIGHT, RENDER_DISTANCE_CHUNKS, ID_AIR
from src.chunk_mesh import block_data_worker_wrapper, mesh_worker_wrapper
from src.lighting_system import LightingSystem
from src.opengl_core import create_chunk_buffers_from_data, delete_chunk_buffers

# Thread Pool Definition hierhin verschoben
THREAD_POOL_SIZE = 8
UNLOAD_DISTANCE_BUFFER = 10 #4
EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=THREAD_POOL_SIZE)


class ChunkManager:
    def __init__(self):
        self.chunk_data = {}  # {coord: (vao, count, vbo, ebo)}
        self.world_data = {}  # {coord: numpy_array}
        self.lighting = LightingSystem(CHUNK_SIZE, MAX_HEIGHT)

        self.data_futures = {}
        self.mesh_futures = {}

        # Konfiguration
        self.max_chunks_per_frame = 1
        self.max_mesh_builds_per_frame = 3

    def get_block(self, cx, cz, bx, by, bz):
        """Sicherer Zugriff auf einen Block."""
        if (cx, cz) in self.world_data:
            # Check bounds
            if 0 <= bx < CHUNK_SIZE and 0 <= by < MAX_HEIGHT and 0 <= bz < CHUNK_SIZE:
                # Padding beachten: Welt-Daten haben +2 Padding, also Index +1
                return self.world_data[(cx, cz)][bx + 1, by, bz + 1]
        return ID_AIR

    def update_block(self, cx, cz, bx, by, bz, new_id):
        """Setzt Block, berechnet Licht neu und markiert Chunks für Re-Mesh."""
        coord = (cx, cz)
        if coord not in self.world_data: return

        local_x, local_z = bx + 1, bz + 1
        if not (0 < local_x < CHUNK_SIZE + 1 and 0 <= by < MAX_HEIGHT and 0 < local_z < CHUNK_SIZE + 1): return

        old_id = self.world_data[coord][local_x, by, local_z]
        self.world_data[coord][local_x, by, local_z] = new_id

        # Licht Update
        self.lighting.update_light_at_position(coord, self.world_data[coord], bx, by, bz, old_id, new_id)

        chunks_to_update = {coord}

        # Padding Sync (Nachbarn informieren)
        self._sync_neighbors(cx, cz, bx, bz, by, new_id, local_x, local_z, chunks_to_update)

        # Licht Sync und Re-Mesh Trigger
        for update_coord in chunks_to_update:
            self.lighting.sync_light_padding(update_coord, self.world_data)
            ucx, ucz = update_coord
            for neighbor in [(ucx - 1, ucz), (ucx + 1, ucz), (ucx, ucz - 1), (ucx, ucz + 1)]:
                if neighbor in self.lighting.light_data:
                    self.lighting.sync_light_padding(neighbor, self.world_data)

        for r_coord in chunks_to_update:
            self.force_remesh(r_coord)

    def _sync_neighbors(self, cx, cz, bx, bz, by, new_id, local_x, local_z, chunks_to_update):
        # ... (Logik für Padding Sync aus alter GameWorld) ...
        if bx == 0:
            n = (cx - 1, cz)
            if n in self.world_data:
                self.world_data[n][CHUNK_SIZE + 1, by, local_z] = new_id
                chunks_to_update.add(n)
        if bx == CHUNK_SIZE - 1:
            n = (cx + 1, cz)
            if n in self.world_data:
                self.world_data[n][0, by, local_z] = new_id
                chunks_to_update.add(n)
        if bz == 0:
            n = (cx, cz - 1)
            if n in self.world_data:
                self.world_data[n][local_x, by, CHUNK_SIZE + 1] = new_id
                chunks_to_update.add(n)
        if bz == CHUNK_SIZE - 1:
            n = (cx, cz + 1)
            if n in self.world_data:
                self.world_data[n][local_x, by, 0] = new_id
                chunks_to_update.add(n)

    def force_remesh(self, coord):
        if coord not in self.world_data or coord not in self.lighting.light_data: return
        if coord not in self.mesh_futures:
            cx, cz = coord
            light_map = self.lighting.light_data[coord]
            future = EXECUTOR.submit(mesh_worker_wrapper, cx, cz, self.world_data[coord], light_map)
            self.mesh_futures[coord] = future

    def update(self, player_pos):
        """Haupt-Update Loop für Chunk Loading UND Unloading."""
        px, pz = player_pos[0], player_pos[2]
        player_chunk_x = int(px // CHUNK_SIZE)  
        player_chunk_z = int(pz // CHUNK_SIZE)

        # 1. Neue Jobs erstellen (LADEN)
        self._schedule_chunks(player_chunk_x, player_chunk_z)

        # 2. Alte Chunks entfernen (ENTLADEN) <--- NEU
        self._unload_far_chunks(player_chunk_x, player_chunk_z)

        # 3. Ergebnisse verarbeiten
        self._process_futures(px, pz)

    def _unload_far_chunks(self, pcx, pcz):
        """Löscht Chunks, die zu weit weg sind, um RAM/VRAM zu sparen."""
        # Wir löschen alles, was etwas weiter ist als die Sichtweite (+2 Chunks Puffer)
        UNLOAD_DIST = RENDER_DISTANCE_CHUNKS + UNLOAD_DISTANCE_BUFFER

        # Liste der zu löschenden Koordinaten erstellen (Dictionary darf während Iteration nicht geändert werden)
        to_remove = []

        for coord in self.chunk_data.keys():
            cx, cz = coord
            dx = cx - pcx
            dz = cz - pcz
            dist_sq = dx * dx + dz * dz

            if dist_sq > UNLOAD_DIST * UNLOAD_DIST:
                to_remove.append(coord)

        # Tatsächliches Löschen
        for coord in to_remove:
            # 1. OpenGL Buffer löschen (WICHTIG gegen VRAM Leaks!)
            if coord in self.chunk_data:
                vao, count, vbo, ebo = self.chunk_data[coord]
                delete_chunk_buffers(vao, vbo, ebo)
                del self.chunk_data[coord]

            # 2. Block-Daten löschen (spart RAM)
            # Wir behalten sie optional im Lighting System oder World Data,
            # aber für maximale Performance löschen wir sie hier aus world_data.
            # Wenn man sie behält, geht das Neuladen schneller, kostet aber RAM.
            if coord in self.world_data:
                del self.world_data[coord]

            # 3. Licht-Daten löschen
            if coord in self.lighting.light_data:
                del self.lighting.light_data[coord]

            # 4. Laufende Futures abbrechen (optional, aber sauberer)
            if coord in self.data_futures:
                del self.data_futures[coord]  # Future läuft im Hintergrund weiter, Ergebnis wird aber ignoriert
            if coord in self.mesh_futures:
                del self.mesh_futures[coord]

    def _schedule_chunks(self, pcx, pcz):
        R = RENDER_DISTANCE_CHUNKS
        for cx in range(pcx - R, pcx + R + 1):
            for cz in range(pcz - R, pcz + R + 1):
                coord = (cx, cz)
                if coord not in self.world_data and coord not in self.data_futures:
                    self.data_futures[coord] = EXECUTOR.submit(block_data_worker_wrapper, cx, cz)
                elif coord in self.world_data and coord not in self.chunk_data and coord not in self.mesh_futures:
                    if coord not in self.lighting.light_data:
                        try:
                            self.lighting.init_chunk_lighting(coord, self.world_data[coord])
                        except Exception:
                            continue
                    light_map = self.lighting.light_data.get(coord, None)
                    if light_map is not None:
                        self.mesh_futures[coord] = EXECUTOR.submit(mesh_worker_wrapper, cx, cz, self.world_data[coord],
                                                                   light_map)

    def _process_futures(self, px, pz):
        # Helper für Sortierung nach Distanz
        def dist(coord):
            cx, cz = coord
            dx = (cx + 0.5) * CHUNK_SIZE - px
            dz = (cz + 0.5) * CHUNK_SIZE - pz
            return dx * dx + dz * dz

        # Data Futures
        finished_data = sorted([c for c, f in self.data_futures.items() if f.done()], key=dist)
        processed = 0
        for coord in finished_data:
            if processed >= self.max_chunks_per_frame: break
            try:
                res = self.data_futures[coord].result()
                if isinstance(res, Exception): raise res
                self.world_data[coord] = res
                self.lighting.init_chunk_lighting(coord, res)

                # Sync & Trigger Neighbors
                self.lighting.sync_light_padding(coord, self.world_data)
                cx, cz = coord
                for n in [(cx - 1, cz), (cx + 1, cz), (cx, cz - 1), (cx, cz + 1)]:
                    if n in self.lighting.light_data:
                        self.lighting.sync_light_padding(n, self.world_data)
                        self.force_remesh(n)
                self.lighting.sync_light_padding(coord, self.world_data)

                del self.data_futures[coord]
                processed += 1
            except Exception as e:
                print(f"Chunk Data Error {coord}: {e}")
                del self.data_futures[coord]

        # Mesh Futures
        finished_mesh = sorted([c for c, f in self.mesh_futures.items() if f.done()], key=dist)
        built = 0
        for coord in finished_mesh:
            if built >= self.max_mesh_builds_per_frame: break
            try:
                verts, inds = self.mesh_futures[coord].result()
                if coord in self.chunk_data:
                    old_vao, _, old_vbo, old_ebo = self.chunk_data[coord]
                    delete_chunk_buffers(old_vao, old_vbo, old_ebo)

                if inds.size > 0:
                    self.chunk_data[coord] = create_chunk_buffers_from_data(verts, inds)
                elif coord in self.chunk_data:
                    del self.chunk_data[coord]

                del self.mesh_futures[coord]
                built += 1
            except Exception as e:
                print(f"Mesh Error {coord}: {e}")
                del self.mesh_futures[coord]

    def render(self, is_chunk_visible_func, frustum_planes):
        """Rendert alle sichtbaren Chunks."""
        for coord, (vao, count, _, _) in self.chunk_data.items():
            if count > 0 and vao is not None:
                if is_chunk_visible_func(frustum_planes, coord[0], coord[1]):
                    glBindVertexArray(vao)
                    glDrawElements(GL_TRIANGLES, count, GL_UNSIGNED_INT, None)

    def shutdown(self):
        EXECUTOR.shutdown(wait=True)