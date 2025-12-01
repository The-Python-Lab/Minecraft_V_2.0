# --- src/hotbar.py ---
import numpy as np
from OpenGL.GL import *
from src.block_definitions import (
    ID_AIR, ID_GRASS, ID_DIRT, ID_STONE, ID_OAK_LOG,
    ID_LEAVES, ID_SAND, ID_CACTUS,
    GRASS_TEXTURES, OAK_LOG_TEXTURES, CACTUS_TEXTURES,
    TEX_INDEX_DIRT, TEX_INDEX_STONE, TEX_INDEX_SAND, TEX_INDEX_LEAVES,
    TEX_INDEX_HOTBAR
)
from src.text_generator import create_number_texture


class Hotbar:
    def __init__(self, gui_renderer, textures):
        print("🎮 Hotbar V6 (MASSIVE Numbers) wird initialisiert...")
        self.renderer = gui_renderer
        self.textures = textures

        self.inventory = [{'id': ID_AIR, 'count': 0} for _ in range(9)]

        self.selected_slot_index = 0
        self.slot_size = 30
        self.padding = 5
        self.margin_bottom = 10

        hotbar_tex_index = int(TEX_INDEX_HOTBAR)
        if 0 <= hotbar_tex_index < len(textures):
            self.hotbar_texture = textures[hotbar_tex_index]
        else:
            self.hotbar_texture = None

        self.number_texture = create_number_texture()

    def add_item(self, block_id, amount=1):
        """Fügt ein Item hinzu (Stacking von links nach rechts)."""
        if block_id == ID_AIR: return

        # 1. Suche nach existierendem Stack mit gleicher ID (mit Stacking-Grenze 64)
        for slot in self.inventory:
            if slot['id'] == block_id and slot['count'] < 64:
                space_left = 64 - slot['count']
                if amount <= space_left:
                    slot['count'] += amount
                    return True
                else:
                    slot['count'] = 64
                    amount -= space_left

        if amount <= 0: return True

        # 2. Suche nach leerem Slot
        for slot in self.inventory:
            if slot['id'] == ID_AIR:
                slot['id'] = block_id
                take = min(64, amount)
                slot['count'] = take
                amount -= take
                if amount <= 0: return True

        return False

    def use_selected_item(self):
        """Verringert die Anzahl des ausgewählten Items."""
        slot = self.inventory[self.selected_slot_index]
        if slot['count'] > 0:
            slot['count'] -= 1
            if slot['count'] <= 0:
                slot['id'] = ID_AIR
            return True
        return False

    def get_selected_block(self):
        """Gibt ID zurück, WENN Items vorhanden sind."""
        slot = self.inventory[self.selected_slot_index]
        if slot['count'] > 0:
            return slot['id']
        return ID_AIR

    def scroll(self, yoffset):
        direction = -int(yoffset)
        self.selected_slot_index = (self.selected_slot_index + direction) % 9

    def select_slot(self, index):
        if 0 <= index < 9:
            self.selected_slot_index = index

    def _get_texture_for_block(self, block_id):
        tex_index = 0
        if block_id == ID_GRASS:
            tex_index = int(GRASS_TEXTURES[2])
        elif block_id == ID_DIRT:
            tex_index = int(TEX_INDEX_DIRT)
        elif block_id == ID_STONE:
            tex_index = int(TEX_INDEX_STONE)
        elif block_id == ID_SAND:
            tex_index = int(TEX_INDEX_SAND)
        elif block_id == ID_OAK_LOG:
            tex_index = int(OAK_LOG_TEXTURES[2])
        elif block_id == ID_LEAVES:
            tex_index = int(TEX_INDEX_LEAVES)
        elif block_id == ID_CACTUS:
            tex_index = int(CACTUS_TEXTURES[2])

        if 0 <= tex_index < len(self.textures):
            return self.textures[tex_index]
        return None

    def render(self, screen_width, screen_height):
        total_width = (self.slot_size * 9) + (self.padding * 7.5)
        start_x = (screen_width - total_width) / 2
        start_y = screen_height - self.slot_size - self.margin_bottom

        # Hintergrund
        if self.hotbar_texture:
            self.renderer.render_rect(
                start_x - 10, start_y - 5,
                total_width + 20, self.slot_size + 10,
                (1.0, 1.0, 1.0, 1.0), self.hotbar_texture, screen_width, screen_height
            )

        for i in range(9):
            x = start_x + i * (self.slot_size + self.padding)
            y = start_y
            slot = self.inventory[i]

            # Selektion
            if i == self.selected_slot_index:
                self.renderer.render_rect(
                    x - 2, y - 2,
                    self.slot_size + 4, self.slot_size + 4,
                    (1.0, 1.0, 1.0, 0.9), None, screen_width, screen_height
                )

            # Item
            if slot['id'] != ID_AIR and slot['count'] > 0:
                tex = self._get_texture_for_block(slot['id'])
                if tex:
                    self.renderer.render_rect(
                        x + 8, y + 8,
                        self.slot_size - 16, self.slot_size - 16,
                        (1.0, 1.0, 1.0, 1.0), tex, screen_width, screen_height
                    )

                # --- ZAHLEN RENDERN ---
                if slot['count'] > 1:
                    # MAXIMALE GRÖSSE: 40 Pixel (Slot ist 30px)
                    num_size = 70

                    # Position: Unten Rechts, überlappend
                    x_right_align = x + self.slot_size + 40
                    # Vertikale Position: Mittenzentriert auf der Slot-Unterkante
                    pos_y = y + self.slot_size - num_size + 30

                    self._render_number(slot['count'], x_right_align, pos_y, num_size, screen_width, screen_height)

    def _render_number(self, number, x_right_align, y, size, sw, sh):
        """Zeichnet Zahl rechtsbündig zur Koordinate x_right_align."""
        s_num = str(number)

        digit_width = size
        digit_height = size

        # Enges Spacing für kompakten Look
        spacing_factor = 0.12

        # Gesamtbreite berechnen
        total_width = (len(s_num) - 1) * digit_width * spacing_factor + digit_width

        # Start X berechnen
        current_x = x_right_align - total_width

        for char in s_num:
            digit = int(char)

            # UV Koordinaten (0.1 Breite pro Ziffer)
            u_start = digit * 0.1
            u_width = 0.1

            # (u_start, v_start, u_width, v_height)
            uv_rect = (u_start, 0.0, u_width, 1.0)

            # Wichtig: Render_rect mit der Zahlen-Textur und uv_rect aufrufen!
            self.renderer.render_rect(
                current_x, y,
                digit_width, digit_height,
                (1.0, 1.0, 1.0, 1.0),
                self.number_texture,
                sw, sh,
                uv_rect=uv_rect
            )

            current_x += digit_width * spacing_factor