# --- src/game_world.py ---
import glfw
from OpenGL.GL import *
import numpy as np
from pyrr import Matrix44

from src.chunk_data import CHUNK_SIZE, MAX_HEIGHT, ID_AIR
from src.opengl_core import (
    setup_textures,
    LineRenderer, GUIRenderer
)

# Optionaler Renderer
try:
    from src.opengl_core import CrackRenderer

    HAS_CRACK_RENDERER = True
except ImportError:
    HAS_CRACK_RENDERER = False

from src.block_definitions import BLOCK_HARDNESS, DEFAULT_HARDNESS, ID_GRASS, ID_WATER

# --- Manager Imports ---
from src.managers.chunk_manager import ChunkManager
from src.managers.item_manager import ItemManager
from src.input_handler import InputHandler
from src.player import Player
from src.item_renderer import ItemRenderer

# Hotbar Import
from src.gui.hotbar import Hotbar

PICKUP_RANGE = 1.5


class GameWorld:
    def __init__(self, window, shader, width, height):
        self.window = window
        self.shader = shader
        self.width = width
        self.height = height

        # --- Sub-Systeme ---
        self.chunk_manager = ChunkManager()
        # NEU: ItemRenderer VOR ItemManager erstellen!
        self.item_renderer = ItemRenderer()
        self.item_manager = ItemManager(self.item_renderer)  # GEÄNDERT: Renderer übergeben

        # --- Renderer ---
        self.line_renderer = LineRenderer()
        self.crack_renderer = CrackRenderer() if HAS_CRACK_RENDERER else None

        # Texturen laden (für Welt & GUI)
        self.textures = setup_textures(shader)

        # 🚀 FIX: Haupt-Chunk-Shader Textur-Sampler initialisieren
        # Wir müssen den 'textures[i]' Uniforms im CHUNK SHADER sagen,
        # dass sie auf die Texture Unit 'i' zugreifen sollen.
        glUseProgram(self.shader)
        for i in range(16):
            # Holt die Location für uniform sampler2D textures[i]
            loc = glGetUniformLocation(self.shader, f"textures[{i}]")
            if loc != -1:
                # Setzt den Uniform-Wert auf den Index i (die Texture Unit)
                glUniform1i(loc, i)

        # WICHTIG: Shader danach deaktivieren, um den Zustand zurückzusetzen
        #glUseProgram(0)

        print("✅ GameWorld: Haupt-Chunk-Shader Textur-Sampler initialisiert.")

        # GUI
        self.gui_renderer = GUIRenderer()
        if Hotbar:
            self.hotbar = Hotbar(self.gui_renderer, self.textures)
            self.selected_block_id = self.hotbar.get_selected_block()
        else:
            self.hotbar = None
            self.selected_block_id = ID_GRASS

        # --- Player ---
        self.player = Player(
            position=np.array([CHUNK_SIZE / 2.0, MAX_HEIGHT * 2.0, CHUNK_SIZE * 2.5], dtype=np.float32),
            yaw=-90.0, pitch=0.0
        )

        # --- Mining State ---
        self.is_mining = False
        self.mining_block_pos = None
        self.mining_progress = 0.0

        # --- Input Setup ---
        self.mouse_last_x = 0.0
        self.mouse_last_y = 0.0
        self.mouse_first_input = True
        self.input_handler = InputHandler(window, self)  # Übergibt 'self' an den Handler

        # --- Uniforms ---
        self.view_loc = glGetUniformLocation(shader, "view")
        self.proj_loc = glGetUniformLocation(shader, "projection")
        self.model_loc = glGetUniformLocation(shader, "model")

        self.projection = Matrix44.perspective_projection(self.player.fovy, width / height, self.player.near,
                                                          self.player.far)
        glUniformMatrix4fv(self.proj_loc, 1, GL_FALSE, self.projection.astype('float32'))
        glUniformMatrix4fv(self.model_loc, 1, GL_FALSE, Matrix44.identity().astype('float32'))

        glfw.set_input_mode(self.window, glfw.CURSOR, glfw.CURSOR_DISABLED)

    # --- Input Handling Delegation ---
    def handle_mouse_move(self, xpos, ypos):
        if glfw.get_input_mode(self.window, glfw.CURSOR) == glfw.CURSOR_DISABLED:
            if self.mouse_first_input:
                self.mouse_last_x = xpos
                self.mouse_last_y = ypos
                self.mouse_first_input = False
                return
            xoffset = xpos - self.mouse_last_x
            yoffset = self.mouse_last_y - ypos
            self.mouse_last_x = xpos
            self.mouse_last_y = ypos
            self.player.mouse_dx = xoffset
            self.player.mouse_dy = yoffset

    def handle_scroll(self, yoffset):
        if glfw.get_input_mode(self.window, glfw.CURSOR) == glfw.CURSOR_DISABLED and self.hotbar:
            self.hotbar.scroll(yoffset)
            self.selected_block_id = self.hotbar.get_selected_block()

    def handle_key(self, key, action):
        if key == glfw.KEY_ESCAPE and action == glfw.PRESS:
            mode = glfw.get_input_mode(self.window, glfw.CURSOR)
            if mode == glfw.CURSOR_DISABLED:
                glfw.set_input_mode(self.window, glfw.CURSOR, glfw.CURSOR_NORMAL)
                self.is_mining = False
                self.mining_progress = 0.0
            else:
                glfw.set_input_mode(self.window, glfw.CURSOR, glfw.CURSOR_DISABLED)
                self.mouse_first_input = True

        # Hotbar Tasten
        if action == glfw.PRESS and self.hotbar:
            if glfw.KEY_1 <= key <= glfw.KEY_9:
                self.hotbar.select_slot(key - glfw.KEY_1)
                self.selected_block_id = self.hotbar.get_selected_block()

    def handle_mouse_button(self, button, action):
        """Steuert Mining-State (Linksklick) und Platzieren (Rechtsklick)."""
        # 1. Cursor Check
        if glfw.get_input_mode(self.window, glfw.CURSOR) != glfw.CURSOR_DISABLED:
            return

        # ==========================================
        # LINKSKLICK: MINING STATE MACHINE
        # ==========================================
        if button == glfw.MOUSE_BUTTON_LEFT:
            if action == glfw.PRESS:
                # Starte den Mining-Prozess. Der eigentliche Abbau passiert in _update_mining.
                self.is_mining = True
            elif action == glfw.RELEASE:
                # Mining beenden
                self.is_mining = False
                self.mining_block_pos = None  # Das Ziel zurücksetzen
                self.mining_progress = 0.0  # Fortschritt zurücksetzen

        # ==========================================
        # RECHTSKLICK: PLATZIEREN & VERBRAUCHEN (Survival Logic)
        # ==========================================
        elif button == glfw.MOUSE_BUTTON_RIGHT and action == glfw.PRESS:

            chunk_size = CHUNK_SIZE
            block_to_place = self.hotbar.get_selected_block()

            # Nur bauen, wenn wir wirklich ein Item haben
            if block_to_place != ID_AIR:
                # Raycast, um die Platzierungsposition zu finden
                # Wir verwenden CHUNK_SIZE anstatt self.chunk_manager.CHUNK_SIZE
                hit, place_info = self.player.raycast_block_selection(
                    self.chunk_manager.world_data,
                    chunk_size,
                    max_dist=8.0
                )

                if place_info:
                    (cx, cz), bx, by, bz = place_info

                    world_x = cx * chunk_size + bx
                    world_z = cz * chunk_size + bz

                    # Kollisions-Check
                    if not self.player.check_block_intersection(world_x, by, world_z):
                        # Block in der Welt setzen
                        self.chunk_manager.update_block(cx, cz, bx, by, bz, block_to_place)

                        # WICHTIG: Item aus Inventar abziehen!
                        self.hotbar.use_selected_item()

                        print(f"🏗️ Block {block_to_place} gesetzt. Item verbraucht.")
            else:
                print("⚠️ Dieser Slot ist leer!")

    def handle_focus(self, focused):
        if focused: self.mouse_first_input = True

    # --- Update Loop ---
    def update(self, dt):
        # 1. Chunks updaten
        self.chunk_manager.update(self.player.pos)

        # 2. Player Input & Physics
        if glfw.get_input_mode(self.window, glfw.CURSOR) == glfw.CURSOR_DISABLED:
            self.player.handle_mouse_input()
            self.player.apply_movement_input(self.window, dt)
        else:
            self.player.mouse_dx = 0.0
            self.player.mouse_dy = 0.0
            self.player.target_velocity[:] = 0.0

        self.player.apply_physics(dt, self.chunk_manager.world_data, CHUNK_SIZE)

        # 3. Mining Logic
        self._update_mining(dt)

        # 4. Items Logic
        collected = self.item_manager.update(
            dt,
            self.player.pos,
            self.chunk_manager.world_data
        )

        # WENN Items eingesammelt wurden ⇾ Ab in die Hotbar damit!
        if collected:
            for block_id in collected:
                # Das fügt das Item hinzu (stapelt es oder sucht neuen Slot)
                success = self.hotbar.add_item(block_id)

                if success:
                    print(f"Item {block_id} ins Inventar aufgenommen.")
                else:
                    print("Inventar voll!")

    def _update_mining(self, dt):
        if self.is_mining:
            hit, _ = self.player.raycast_block_selection(self.chunk_manager.world_data, CHUNK_SIZE, max_dist=5.0)
            if hit:
                (cx, cz), bx, by, bz = hit
                target = (cx, cz, bx, by, bz)

                # HIER: Prüfen, ob der anvisierte Block Wasser ist.
                current_block_id = self.chunk_manager.get_block(cx, cz, bx, by, bz)

                # Wenn der Block Wasser ist, stoppen wir das Mining sofort und beenden die Funktion.
                if current_block_id == ID_WATER:
                    self.is_mining = False
                    self.mining_progress = 0.0
                    self.mining_block_pos = None
                    return  # WICHTIG: Die Funktion hier beenden

                if self.mining_block_pos != target:
                    self.mining_block_pos = target
                    self.mining_progress = 0.0

                # Block ID holen
                block_id = self.chunk_manager.get_block(cx, cz, bx, by, bz)
                hardness = BLOCK_HARDNESS.get(block_id, DEFAULT_HARDNESS)

                if hardness > 0:
                    self.mining_progress += dt / hardness
                else:
                    self.mining_progress = 1.1

                if self.mining_progress >= 1.0:
                    # Block zerstören
                    self.chunk_manager.update_block(cx, cz, bx, by, bz, ID_AIR)
                    # Item spawnen
                    wx = cx * CHUNK_SIZE + bx
                    wz = cz * CHUNK_SIZE + bz
                    self.item_manager.spawn_item(block_id, (wx + 0.5, by, wz + 0.5)) # änderung

                    self.mining_progress = 0.0
                    self.mining_block_pos = None
            else:
                self.mining_progress = 0.0
                self.mining_block_pos = None
        else:
            self.mining_progress = 0.0

    # --- Render Loop ---
    def render(self):
        view = self.player.get_view_matrix()

        glUseProgram(self.shader)
        glUniformMatrix4fv(self.view_loc, 1, GL_FALSE, view.astype('float32'))
        glUniformMatrix4fv(self.model_loc, 1, GL_FALSE, Matrix44.identity().astype('float32'))

        # Frustum Culling Planes
        view_proj = self.projection * view
        planes = self._extract_frustum_planes(view_proj)

        glClearColor(0.53, 0.8, 0.95, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        # Texturen binden
        for i, tex in enumerate(self.textures):
            glActiveTexture(GL_TEXTURE0 + i)
            glBindTexture(GL_TEXTURE_2D, tex)

        # 1. Chunks rendern (delegiert an ChunkManager)
        self.chunk_manager.render(self._is_chunk_visible, planes)

        # --- FIX FÜR Z-FIGHTING (Polygon Offset) ---
        glEnable(GL_POLYGON_OFFSET_FILL)
        # Feste Konstanten, um die Tiefe leicht zu verschieben
        glPolygonOffset(2.0, 2.0)  # Experimentieren Sie mit diesen Werten (z.B. 1.0, 1.0)

        self.chunk_manager.render(self._is_chunk_visible, planes)

        glDisable(GL_POLYGON_OFFSET_FILL)
        # -------------------------------------------

        # 2. Mining Risse
        self._draw_cracks(view)

        # 3. Selection Box
        self._draw_selection_box(view)

        # 4. Items (GEÄNDERT: Nutzt jetzt ItemRenderer!)
        self.item_manager.render(view, self.projection, self.textures)

        # 5. Crosshair
        glClear(GL_DEPTH_BUFFER_BIT)
        self._draw_crosshair()

        # 6. GUI (Hotbar)
        if self.hotbar:
            self.hotbar.render(self.width, self.height)

    # --- Helper für Rendering ---
    def _draw_cracks(self, view):
        if self.is_mining and self.mining_block_pos and self.mining_progress > 0.0:
            if self.crack_renderer:
                cx, cz, bx, by, bz = self.mining_block_pos
                wx = cx * CHUNK_SIZE + bx
                wz = cz * CHUNK_SIZE + bz
                self.crack_renderer.render((wx, by, wz), self.mining_progress, view, self.projection)

    def _draw_selection_box(self, view):
        hit, _ = self.player.raycast_block_selection(self.chunk_manager.world_data, CHUNK_SIZE, max_dist=8.0)
        if hit:
            (cx, cz), bx, by, bz = hit
            wx = cx * CHUNK_SIZE + bx
            wz = cz * CHUNK_SIZE + bz
            off = 0.005
            min_x, max_x = wx - off, wx + 1 + off
            min_y, max_y = by - off, by + 1 + off
            min_z, max_z = wz - off, wz + 1 + off

            # Simple Box Vertices
            v = np.array([
                min_x, min_y, min_z, max_x, min_y, min_z, max_x, min_y, min_z, max_x, min_y, max_z,
                max_x, min_y, max_z, min_x, min_y, max_z, min_x, min_y, max_z, min_x, min_y, min_z,
                min_x, max_y, min_z, max_x, max_y, min_z, max_x, max_y, min_z, max_x, max_y, max_z,
                max_x, max_y, max_z, min_x, max_y, max_z, min_x, max_y, max_z, min_x, max_y, min_z,
                min_x, min_y, min_z, min_x, max_y, min_z, max_x, min_y, min_z, max_x, max_y, min_z,
                max_x, min_y, max_z, max_x, max_y, max_z, min_x, min_y, max_z, min_x, max_y, max_z,
            ], dtype=np.float32)
            self.line_renderer.draw_lines(v, view, self.projection, color=(0, 0, 0, 1), thickness=2.5)

    def _draw_crosshair(self):
        size = 0.02
        ratio = self.width / self.height
        v = np.array([0.0, -size, 0.0, 0.0, size, 0.0, -size / ratio, 0.0, 0.0, size / ratio, 0.0, 0.0],
                     dtype=np.float32)
        self.line_renderer.draw_lines(v, Matrix44.identity(), Matrix44.identity(), Matrix44.identity(),
                                      color=(1, 1, 1, 0.8), thickness=2.0)

    def _extract_frustum_planes(self, view_proj):
        # ... (Gleiche Logik wie vorher) ...
        planes = np.zeros((6, 4), dtype=np.float32)
        m = np.array(view_proj)
        planes[0] = m[:, 3] + m[:, 0]
        planes[1] = m[:, 3] - m[:, 0]
        planes[2] = m[:, 3] + m[:, 1]
        planes[3] = m[:, 3] - m[:, 1]
        planes[4] = m[:, 3] + m[:, 2]
        planes[5] = m[:, 3] - m[:, 2]
        for i in range(6): planes[i] /= np.linalg.norm(planes[i, :3])
        return planes

    def _is_chunk_visible(self, planes, cx, cz):
        FRUSTUM_MARGIN = 0.01

        min_x, max_x = cx * CHUNK_SIZE, (cx + 1) * CHUNK_SIZE
        min_z, max_z = cz * CHUNK_SIZE, (cz + 1) * CHUNK_SIZE
        points = [[min_x, 0, min_z], [max_x, 0, min_z], [min_x, MAX_HEIGHT, min_z], [max_x, MAX_HEIGHT, min_z],
                  [min_x, 0, max_z], [max_x, 0, max_z], [min_x, MAX_HEIGHT, max_z], [max_x, MAX_HEIGHT, max_z]]

        for plane in planes:
            # Wenn ALLE 8 Punkte des Chunks HINTER der Ebene und HINTER der Marge liegen,
            # gilt der Chunk als unsichtbar.
            if all(plane[0] * p[0] + plane[1] * p[1] + plane[2] * p[2] + plane[3] < -FRUSTUM_MARGIN for p in points):
                return False
        return True

    def shutdown(self):
        self.chunk_manager.shutdown()


def run_game(window, shader, width, height):
    game_world = GameWorld(window, shader, width, height)
    prev_time = glfw.get_time()
    frame_count = 0
    last_fps_update = glfw.get_time()

    try:
        while not glfw.window_should_close(window):
            now = glfw.get_time()
            dt = now - prev_time
            prev_time = now

            frame_count += 1
            if now - last_fps_update >= 1.0:
                fps = frame_count / (now - last_fps_update)
                # Chunks zählen via Manager
                chunk_count = len(game_world.chunk_manager.chunk_data)
                glfw.set_window_title(window, f"Minecraft Clone | FPS: {fps:.2f} | Chunks: {chunk_count}")
                frame_count = 0
                last_fps_update = now

            glfw.poll_events()
            game_world.update(dt)
            game_world.render()
            glfw.swap_buffers(window)
    finally:
        game_world.shutdown()