# --- src/item_renderer.py ---
"""
Rendert Dropped Items mit erweiterten Debug-Informationen.
"""

import numpy as np
import ctypes
from OpenGL.GL import *
import OpenGL.GL.shaders
from pyrr import Matrix44
import math

from src.block_definitions import (
    ID_GRASS, ID_DIRT, ID_STONE, ID_OAK_LOG, ID_LEAVES, ID_SAND, ID_CACTUS,
    GRASS_TEXTURES, OAK_LOG_TEXTURES, CACTUS_TEXTURES,
    TEX_INDEX_DIRT, TEX_INDEX_STONE, TEX_INDEX_SAND, TEX_INDEX_LEAVES
)
from src.geometry_constants import CUBE_UVS # <--- DIESE ZEILE HINZUFÜGEN

# --- SHADER (Unverändert) ---
ITEM_VERTEX_SRC = """
#version 330 core
layout(location = 0) in vec3 a_position;
layout(location = 1) in vec2 a_texcoord;
layout(location = 2) in float a_texid;

out vec2 v_texcoord;
flat out int v_texid;

uniform mat4 model;
uniform mat4 view;
uniform mat4 projection;

void main() {
    gl_Position = projection * view * model * vec4(a_position, 1.0);
    v_texcoord = a_texcoord;
    v_texid = int(round(a_texid));
}
"""

ITEM_FRAGMENT_SRC = """
#version 330 core
in vec2 v_texcoord;
flat in int v_texid;

out vec4 out_color;

uniform sampler2D textures[16];
uniform float brightness;

void main() {
    vec4 texColor;
    if (v_texid >= 0 && v_texid < 16) {
        texColor = texture(textures[v_texid], v_texcoord);
    } else {
        texColor = vec4(1.0, 0.0, 1.0, 1.0); // Magenta Error
    }
    if (texColor.a < 0.5) discard;
    out_color = vec4(texColor.rgb * brightness, texColor.a);
}
"""


class ItemRenderer:
    def __init__(self):
        print("🎁 ItemRenderer (Debug Mode) wird initialisiert...")

        # Shader kompilieren
        try:
            self.shader = OpenGL.GL.shaders.compileProgram(
                OpenGL.GL.shaders.compileShader(ITEM_VERTEX_SRC, GL_VERTEX_SHADER),
                OpenGL.GL.shaders.compileShader(ITEM_FRAGMENT_SRC, GL_FRAGMENT_SHADER),
                validate=False
            )
            print("✅ Item Shader kompiliert!")
        except Exception as e:
            print(f"❌ Shader Fehler: {e}")
            raise

        self.view_loc = glGetUniformLocation(self.shader, "view")
        self.proj_loc = glGetUniformLocation(self.shader, "projection")
        self.model_loc = glGetUniformLocation(self.shader, "model")
        self.brightness_loc = glGetUniformLocation(self.shader, "brightness")

        self._setup_buffers()
        self.mesh_cache = {}

        # Debug-Set, damit wir die Konsole nicht vollspammen
        self.debugged_ids = set()

        # --- DER FEHLENDE FIX: Textur-Sampler initialisieren ---
        glUseProgram(self.shader)
        for i in range(16):
            loc = glGetUniformLocation(self.shader, f"textures[{i}]")
            if loc != -1:
                glUniform1i(loc, i)  # Weist textures[i] die Texture Unit i zu

        print("✅ ItemRenderer: Textur-Sampler initialisiert!")

    def _setup_buffers(self):
        # Buffer für einen Würfel (24 Vertices * 6 Floats)
        buffer_size = 24 * 6 * 4
        indices = []
        for i in range(6):
            base = i * 4
            indices.extend([base, base + 1, base + 2, base + 2, base + 3, base])
        indices = np.array(indices, dtype=np.uint32)

        self.vao = glGenVertexArrays(1)
        glBindVertexArray(self.vao)

        self.vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, buffer_size, None, GL_DYNAMIC_DRAW)

        self.ebo = glGenBuffers(1)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL_STATIC_DRAW)

        stride = 6 * 4
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(0))
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(3 * 4))
        glEnableVertexAttribArray(2)
        glVertexAttribPointer(2, 1, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(5 * 4))
        glBindVertexArray(0)
        self.indices_count = len(indices)

    def _get_textures_for_block(self, block_id):
        # WICHTIG: Casting zu int für sicheren Vergleich
        bid = int(round(block_id))

        # Hier prüfen wir alle IDs
        if bid == int(ID_GRASS):
            return GRASS_TEXTURES.copy()
        elif bid == int(ID_DIRT):
            return np.array([TEX_INDEX_DIRT] * 6, dtype=np.float32)
        elif bid == int(ID_STONE):
            return np.array([TEX_INDEX_STONE] * 6, dtype=np.float32)
        elif bid == int(ID_OAK_LOG):
            return OAK_LOG_TEXTURES.copy()
        elif bid == int(ID_LEAVES):
            return np.array([TEX_INDEX_LEAVES] * 6, dtype=np.float32)
        elif bid == int(ID_SAND):
            return np.array([TEX_INDEX_SAND] * 6, dtype=np.float32)
        elif bid == int(ID_CACTUS):
            return CACTUS_TEXTURES.copy()
        else:
            # Unbekannte ID -> Debug Print erzwingen
            if bid not in self.debugged_ids:
                print(f"⚠️ WARNUNG: Keine Textur für Block-ID {bid} (Float: {block_id}) gefunden! Nutze Fallback.")
                self.debugged_ids.add(bid)
            return np.array([-1.0] * 6, dtype=np.float32)  # Magenta

    def _create_cube_vertices(self, block_id):
        textures = self._get_textures_for_block(block_id)

        # Debugging Output (nur einmal pro ID)
        bid = int(round(block_id))
        if bid not in self.debugged_ids:
            print(f"[DEBUG] Erstelle Mesh für Block-ID: {bid}")
            print(f"        -> Verwendete Textur-Indices: {textures}")
            self.debugged_ids.add(bid)

        faces = [
            ([0.0, 1.0, 0.0], [0.0, 1.0, 1.0], [1.0, 1.0, 1.0], [1.0, 1.0, 0.0]),  # Top (0)
            ([0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 0.0, 1.0], [0.0, 0.0, 1.0]),  # Bottom (1)
            ([0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 1.0, 1.0], [0.0, 0.0, 1.0]),  # Left (2)
            ([1.0, 0.0, 0.0], [1.0, 0.0, 1.0], [1.0, 1.0, 1.0], [1.0, 1.0, 0.0]),  # Right (3)
            ([0.0, 0.0, 1.0], [0.0, 1.0, 1.0], [1.0, 1.0, 1.0], [1.0, 0.0, 1.0]),  # Front (4)
            ([0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0], [1.0, 0.0, 0.0])  # Back (5)
        ]

        data = []
        for i, face in enumerate(faces):
            tex = textures[i]
            uvs_for_face = CUBE_UVS[i]  # Die korrigierten UVs aus geometry_constants.py verwenden

            for j in range(4):
                data.extend(face[j])  # Pos
                data.extend(uvs_for_face[j])  # UVs der spezifischen Fläche
                data.append(tex)  # TexID
        return np.array(data, dtype=np.float32)

    def _get_or_create_mesh_data(self, block_id):
        key = int(round(block_id))
        if key not in self.mesh_cache:
            self.mesh_cache[key] = self._create_cube_vertices(block_id)
        return self.mesh_cache[key]

    def render_item(self, item, view, projection, textures):
        glUseProgram(self.shader)
        glUniformMatrix4fv(self.view_loc, 1, GL_FALSE, view.astype('float32'))
        glUniformMatrix4fv(self.proj_loc, 1, GL_FALSE, projection.astype('float32'))
        glUniform1f(self.brightness_loc, 1.0)

        for i, tex in enumerate(textures[:16]):
            glActiveTexture(GL_TEXTURE0 + i)
            glBindTexture(GL_TEXTURE_2D, tex)

        # Mesh Daten laden
        vertex_data = self._get_or_create_mesh_data(item.block_id)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferSubData(GL_ARRAY_BUFFER, 0, vertex_data.nbytes, vertex_data)

        # Model Matrix
        translation = Matrix44.from_translation(item.pos)
        rotation = Matrix44.from_y_rotation(math.radians(item.rotation))
        scale = Matrix44.from_scale([item.scale, item.scale, item.scale])
        center = Matrix44.from_translation([-0.5, 0.0, -0.5])

        model = translation * rotation * scale * center
        glUniformMatrix4fv(self.model_loc, 1, GL_FALSE, model.astype('float32'))

        glBindVertexArray(self.vao)
        glDrawElements(GL_TRIANGLES, self.indices_count, GL_UNSIGNED_INT, None)
        glBindVertexArray(0)

    def render_items(self, items, view, projection, textures):
        if not items: return
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        for item in items:
            self.render_item(item, view, projection, textures)