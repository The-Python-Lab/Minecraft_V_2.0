# --- src/opengl_core.py ---
import glfw
from OpenGL.GL import *
import OpenGL.GL.shaders
from PIL import Image
import ctypes
import numpy as np
from pyrr import Matrix44
from .block_definitions import get_texture_paths

# --- STANDARD CHUNK SHADERS ---
VERTEX_SRC = """
#version 330 core
layout(location = 0) in vec3 a_position;
layout(location = 1) in vec2 a_texcoord;
layout(location = 2) in float a_texid;
layout(location = 3) in float a_light;

out vec2 v_texcoord;
flat out int v_texid;
out float v_light;

uniform mat4 model;
uniform mat4 view;
uniform mat4 projection;

void main() {
    gl_Position = projection * view * model * vec4(a_position, 1.0);
    v_texcoord = a_texcoord;
    v_texid = int(round(a_texid));
    v_light = a_light / 15.0;
}
"""

FRAGMENT_SRC = """
#version 330 core
in vec2 v_texcoord;
flat in int v_texid;
in float v_light;

out vec4 out_color;

uniform sampler2D textures[16]; 
uniform float ambientLight;

void main() {
    if (v_texid < 0) {
        out_color = vec4(1.0, 0.0, 1.0, 1.0);
        return;
    }
    vec4 texColor;

    if (v_texid >= 0 && v_texid < 16) {
        texColor = texture(textures[v_texid], v_texcoord);
    } else {
        texColor = vec4(1.0, 0.0, 1.0, 1.0);
    }

    // Schwellenwert auf 0.1 senken, damit halb-transparentes Wasser (z.B. 0.4) sichtbar bleibt!
    if (texColor.a < 0.5) {
        discard;
    }

    float minLight = ambientLight;
    float finalLight = mix(minLight, 1.0, v_light);
    out_color = vec4(texColor.rgb * finalLight, texColor.a);
}
"""

# --- LINE RENDERER SHADERS (Selection Box & Crosshair) ---
LINE_VERTEX_SRC = """
#version 330 core
layout(location = 0) in vec3 a_position;
uniform mat4 view;
uniform mat4 projection;
uniform mat4 model;
void main() {
    gl_Position = projection * view * model * vec4(a_position, 1.0);
}
"""

LINE_FRAGMENT_SRC = """
#version 330 core
out vec4 color;
uniform vec4 line_color;
void main() {
    color = line_color;
}
"""

# --- CRACK RENDERER SHADERS (Mining Overlay) ---
CRACK_VERTEX_SRC = """
#version 330 core
layout(location = 0) in vec3 a_position;
layout(location = 1) in vec2 a_texcoord;

out vec2 v_texcoord;

uniform mat4 model;
uniform mat4 view;
uniform mat4 projection;

void main() {
    gl_Position = projection * view * model * vec4(a_position, 1.0);
    v_texcoord = a_texcoord;
}
"""

CRACK_FRAGMENT_SRC = """
#version 330 core
in vec2 v_texcoord;
out vec4 color;

uniform sampler2D crackTexture;

void main() {
    vec4 texColor = texture(crackTexture, v_texcoord);
    // Transparente Bereiche der Crack-Textur verwerfen
    if (texColor.a < 0.1) discard; 
    color = texColor;
}
"""


class LineRenderer:
    def __init__(self):
        self.shader = OpenGL.GL.shaders.compileProgram(
            OpenGL.GL.shaders.compileShader(LINE_VERTEX_SRC, GL_VERTEX_SHADER),
            OpenGL.GL.shaders.compileShader(LINE_FRAGMENT_SRC, GL_FRAGMENT_SHADER),
            validate=False  # <-- Diese Zeile hinzufügen!
        )

        self.vao = glGenVertexArrays(1)
        self.vbo = glGenBuffers(1)

        self.view_loc = glGetUniformLocation(self.shader, "view")
        self.proj_loc = glGetUniformLocation(self.shader, "projection")
        self.model_loc = glGetUniformLocation(self.shader, "model")
        self.color_loc = glGetUniformLocation(self.shader, "line_color")

    def draw_lines(self, vertices, view, projection, model=None, color=(0, 0, 0, 1), thickness=1.0):
        if model is None:
            model = Matrix44.identity()

        glUseProgram(self.shader)
        glUniformMatrix4fv(self.view_loc, 1, GL_FALSE, view.astype('float32'))
        glUniformMatrix4fv(self.proj_loc, 1, GL_FALSE, projection.astype('float32'))
        glUniformMatrix4fv(self.model_loc, 1, GL_FALSE, model.astype('float32'))
        glUniform4f(self.color_loc, *color)

        glBindVertexArray(self.vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_DYNAMIC_DRAW)

        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, None)

        try:
            glLineWidth(thickness)
        except Exception:
            glLineWidth(1.0)

        glDrawArrays(GL_LINES, 0, len(vertices) // 3)
        glLineWidth(1.0)


class CrackRenderer:
    """Zeichnet das Riss-Overlay über Blöcke, die abgebaut werden."""

    def __init__(self):
        self.shader = OpenGL.GL.shaders.compileProgram(
            OpenGL.GL.shaders.compileShader(CRACK_VERTEX_SRC, GL_VERTEX_SHADER),
            OpenGL.GL.shaders.compileShader(CRACK_FRAGMENT_SRC, GL_FRAGMENT_SHADER),
            validate=False  # <-- Diese Zeile hinzufügen!
        )
        self.view_loc = glGetUniformLocation(self.shader, "view")
        self.proj_loc = glGetUniformLocation(self.shader, "projection")
        self.model_loc = glGetUniformLocation(self.shader, "model")

        # --- Texturen laden ---
        self.crack_textures = []
        for i in range(10):
            # Pfad: assets/cracks/destroy_stage_0.png ... 9.png
            path = f"assets/cracks/destroy_stage_{i}.png"
            tex = load_texture(path)
            if tex is None:
                print(f"WARNUNG: Crack-Textur nicht gefunden: {path}")
                # Fallback: Versuche 0 zu nutzen oder einfach 0 (kein Bild)
                tex = 0
            self.crack_textures.append(tex)

        # --- Cube Mesh erstellen (Einheitswürfel 0..1) ---
        # Format: x, y, z, u, v
        # Wir definieren hier manuell einen Würfel, um keine Abhängigkeiten zu haben
        cube_vertices = [
            # Front (+Z)
            0, 0, 1, 0, 0, 1, 0, 1, 1, 0, 1, 1, 1, 1, 1, 0, 1, 1, 0, 1,
            # Back (-Z)
            1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 1, 1, 1, 1, 0, 0, 1,
            # Left (-X)
            0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 1, 1, 1, 1, 0, 1, 0, 0, 1,
            # Right (+X)
            1, 0, 1, 0, 0, 1, 0, 0, 1, 0, 1, 1, 0, 1, 1, 1, 1, 1, 0, 1,
            # Top (+Y)
            0, 1, 1, 0, 0, 1, 1, 1, 1, 0, 1, 1, 0, 1, 1, 0, 1, 0, 0, 1,
            # Bottom (-Y)
            0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 1, 0, 1, 1, 1, 0, 0, 1, 0, 1,
        ]
        # Das sind Quads, wir müssen sie als GL_TRIANGLES zeichnen.
        # Um es einfach zu machen, konvertieren wir die Liste in Indices on-the-fly oder nutzen GL_QUADS (deprecated)
        # Besser: Wir bauen explizite Dreiecke.

        # Vereinfacht: Wir nutzen Indices für die oben definierten 24 Vertices (4 pro Seite * 6 Seiten)
        vertices_array = np.array(cube_vertices, dtype=np.float32)

        indices = []
        for i in range(6):  # 6 Seiten
            base = i * 4
            # 0, 1, 2,  2, 3, 0
            indices.extend([base, base + 1, base + 2, base + 2, base + 3, base])

        indices_array = np.array(indices, dtype=np.uint32)

        self.vao = glGenVertexArrays(1)
        glBindVertexArray(self.vao)

        self.vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, vertices_array.nbytes, vertices_array, GL_STATIC_DRAW)

        self.ebo = glGenBuffers(1)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices_array.nbytes, indices_array, GL_STATIC_DRAW)

        # Attrib 0: Pos (3 floats), Stride: 5*4 bytes
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 5 * 4, ctypes.c_void_p(0))

        # Attrib 1: UV (2 floats), Offset: 3*4 bytes
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 5 * 4, ctypes.c_void_p(3 * 4))

        glBindVertexArray(0)
        self.indices_count = len(indices)

    def render(self, position, progress, view, projection):
        """
        position: (x, y, z) Tuple/Array
        progress: 0.0 bis 1.0
        """
        if progress <= 0.0: return

        # Bestimme Textur-Stage (0 bis 9)
        stage = int(progress * 10)
        if stage > 9: stage = 9
        if stage < 0: stage = 0

        tex_id = self.crack_textures[stage]
        if tex_id == 0: return  # Keine Textur geladen

        glUseProgram(self.shader)

        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, tex_id)

        glUniformMatrix4fv(self.view_loc, 1, GL_FALSE, view.astype('float32'))
        glUniformMatrix4fv(self.proj_loc, 1, GL_FALSE, projection.astype('float32'))

        # Model Matrix: Position + leichte Skalierung, um Z-Fighting zu verhindern
        # Wir skalieren um 1.01 und verschieben um -0.005, damit der Würfel zentriert etwas größer ist
        scale_factor = 1.01
        offset_factor = (1.0 - scale_factor) / 2.0

        trans_mat = Matrix44.from_translation(
            [position[0] + offset_factor, position[1] + offset_factor, position[2] + offset_factor])
        scale_mat = Matrix44.from_scale([scale_factor, scale_factor, scale_factor])

        model = trans_mat * scale_mat
        glUniformMatrix4fv(self.model_loc, 1, GL_FALSE, model.astype('float32'))

        glBindVertexArray(self.vao)
        glDrawElements(GL_TRIANGLES, self.indices_count, GL_UNSIGNED_INT, None)
        glBindVertexArray(0)


def init_window(width, height, title):
    if not glfw.init(): raise Exception("GLFW init failed")
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, GL_TRUE)

    window = glfw.create_window(width, height, title, None, None)
    if not window:
        glfw.terminate()
        raise Exception("Failed to create window")

    glfw.make_context_current(window)
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    # Placeholder VAO, falls benötigt
    vao_placeholder = glGenVertexArrays(1)
    glBindVertexArray(vao_placeholder)

    shader = OpenGL.GL.shaders.compileProgram(
        OpenGL.GL.shaders.compileShader(VERTEX_SRC, GL_VERTEX_SHADER),
        OpenGL.GL.shaders.compileShader(FRAGMENT_SRC, GL_FRAGMENT_SHADER)
    )
    glUseProgram(shader)

    if glGetUniformLocation(shader, "ambientLight") != -1:
        glUniform1f(glGetUniformLocation(shader, "ambientLight"), 0.05)

    return window, shader


def load_texture(path):
    try:
        img = Image.open(path).transpose(Image.FLIP_TOP_BOTTOM)
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"Error loading texture {path}: {e}")
        return None

    img_data = img.convert("RGBA").tobytes()
    tex = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST_MIPMAP_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, img.width, img.height, 0, GL_RGBA, GL_UNSIGNED_BYTE, img_data)
    glGenerateMipmap(GL_TEXTURE_2D)
    return tex


def setup_textures(shader):
    texture_paths = get_texture_paths()
    textures = []

    # --- DEBUG OUTPUT ---
    print(f"DEBUG OPENGL: Starte Ladevorgang für {len(texture_paths)} Texturpfade.")
    # --- END DEBUG OUTPUT ---

    for i, path in enumerate(texture_paths):
        loaded_count = 0
        tex_id = load_texture(path)
        if tex_id is None: raise Exception(f"Textur fehlt: {path}")
        textures.append(tex_id)
        loc = glGetUniformLocation(shader, f"textures[{i}]")
        if loc != -1: glUniform1i(loc, i)
        loaded_count += 1
        print(f"DEBUG OPENGL: {loaded_count} Texturen erfolgreich in OpenGL geladen (sollte 12 sein).")
    return textures


def create_chunk_buffers_from_data(verts, inds):
    if inds.size == 0: return None, 0, None, None
    vao = glGenVertexArrays(1)
    glBindVertexArray(vao)
    vbo = glGenBuffers(1)
    ebo = glGenBuffers(1)
    glBindBuffer(GL_ARRAY_BUFFER, vbo)
    glBufferData(GL_ARRAY_BUFFER, verts.nbytes, verts, GL_STATIC_DRAW)
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ebo)
    glBufferData(GL_ELEMENT_ARRAY_BUFFER, inds.nbytes, inds, GL_STATIC_DRAW)

    # 7 Floats pro Vertex: x, y, z, u, v, tex_id, light
    stride = 7 * verts.itemsize
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(0))
    glEnableVertexAttribArray(0)
    glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(3 * 4))
    glEnableVertexAttribArray(1)
    glVertexAttribPointer(2, 1, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(5 * 4))
    glEnableVertexAttribArray(2)
    glVertexAttribPointer(3, 1, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(6 * 4))
    glEnableVertexAttribArray(3)
    glBindVertexArray(0)
    return vao, inds.size, vbo, ebo


def delete_chunk_buffers(vao, vbo, ebo):
    if vao is not None:
        glDeleteVertexArrays(1, [vao])
        glDeleteBuffers(1, [vbo])
        glDeleteBuffers(1, [ebo])


# --- GUI SHADER (2D Overlay) ---
# WICHTIG: Hier fügen wir 'u_uv_rect' hinzu, um Textur-Ausschnitte zu erlauben
GUI_VERTEX_SRC = """
#version 330 core
layout(location = 0) in vec2 a_position;
layout(location = 1) in vec2 a_texcoord;

out vec2 v_texcoord;

uniform mat4 model;
uniform mat4 projection;
uniform vec4 u_uv_rect; // x, y, width, height (Neu)

void main() {
    gl_Position = projection * model * vec4(a_position, 0.0, 1.0);

    // UV-Koordinaten transformieren: (Original * Breite) + StartX
    v_texcoord = a_texcoord * u_uv_rect.zw + u_uv_rect.xy;
}
"""

GUI_FRAGMENT_SRC = """
#version 330 core
in vec2 v_texcoord;
out vec4 out_color;

uniform sampler2D u_texture;
uniform vec4 u_color;
uniform bool u_use_texture;

void main() {
    if (u_use_texture) {
        vec4 texColor = texture(u_texture, v_texcoord);
        if (texColor.a < 0.1) discard;
        out_color = texColor * u_color;
    } else {
        out_color = u_color;
    }
}
"""


class GUIRenderer:
    def __init__(self):
        print("🎨 GUIRenderer wird initialisiert...")

        try:
            vertex_shader = OpenGL.GL.shaders.compileShader(GUI_VERTEX_SRC, GL_VERTEX_SHADER)
            fragment_shader = OpenGL.GL.shaders.compileShader(GUI_FRAGMENT_SRC, GL_FRAGMENT_SHADER)
            self.shader = OpenGL.GL.shaders.compileProgram(vertex_shader, fragment_shader, validate=False)
            print("✅ GUI Shader erfolgreich kompiliert!")
        except Exception as e:
            print(f"❌ FEHLER beim Kompilieren des GUI Shaders: {e}")
            raise

        vertices = np.array([
            0.0, 0.0, 0.0, 0.0,
            1.0, 0.0, 1.0, 0.0,
            1.0, 1.0, 1.0, 1.0,
            0.0, 1.0, 0.0, 1.0
        ], dtype=np.float32)

        indices = np.array([0, 1, 2, 2, 3, 0], dtype=np.uint32)

        self.vao = glGenVertexArrays(1)
        glBindVertexArray(self.vao)

        self.vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)

        self.ebo = glGenBuffers(1)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL_STATIC_DRAW)

        stride = 4 * 4
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(0))
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(2 * 4))

        glBindVertexArray(0)

        # Uniform Locations
        self.proj_loc = glGetUniformLocation(self.shader, "projection")
        self.model_loc = glGetUniformLocation(self.shader, "model")
        self.color_loc = glGetUniformLocation(self.shader, "u_color")
        self.use_tex_loc = glGetUniformLocation(self.shader, "u_use_texture")
        self.uv_rect_loc = glGetUniformLocation(self.shader, "u_uv_rect")  # <-- NEU

    def render_rect(self, x, y, w, h, color, texture_id=None, screen_width=800, screen_height=600,
                    uv_rect=(0.0, 0.0, 1.0, 1.0)):
        """
        Zeichnet ein Rechteck.
        uv_rect: (u_start, v_start, u_width, v_height) -> Standard ist ganze Textur
        """

        glUseProgram(self.shader)
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        projection = Matrix44.orthogonal_projection(0, screen_width, screen_height, 0, -1, 1)

        translation = Matrix44.from_translation([x, y, 0.0])
        scale = Matrix44.from_scale([w, h, 1.0])
        model = translation * scale

        glUniformMatrix4fv(self.proj_loc, 1, GL_FALSE, projection.astype('float32'))
        glUniformMatrix4fv(self.model_loc, 1, GL_FALSE, model.astype('float32'))
        glUniform4f(self.color_loc, *color)

        # UV Rect übergeben
        glUniform4f(self.uv_rect_loc, *uv_rect)

        if texture_id is not None:
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, texture_id)
            glUniform1i(self.use_tex_loc, 1)
        else:
            glUniform1i(self.use_tex_loc, 0)

        glBindVertexArray(self.vao)
        glDrawElements(GL_TRIANGLES, 6, GL_UNSIGNED_INT, None)
        glBindVertexArray(0)

        glEnable(GL_DEPTH_TEST)