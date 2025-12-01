# --- src/greedy_mesh.py ---
import numpy as np
from numba import jit

from .chunk_data import CHUNK_SIZE, MAX_HEIGHT, ID_AIR
# WICHTIG: CACTUS_VERTICES NICHT MEHR NÖTIG
from .geometry_constants import CUBE_VERTICES, CUBE_UVS, CUBE_NORMALS, FACE_SHADING
from .block_definitions import (
    ID_LEAVES, ID_OAK_LOG, ID_GRASS, ID_DIRT, ID_STONE, ID_SAND, ID_CACTUS, ID_WATER,
    NON_SOLID_BLOCKS_NUMBA, OAK_LOG_TEXTURES, GRASS_TEXTURES, CACTUS_TEXTURES,
    TEX_INDEX_LEAVES, TEX_INDEX_DIRT, TEX_INDEX_STONE, TEX_INDEX_SAND, WATER_TEXTURES
)
from .lighting_system import calculate_minecraft_vertex_light

@jit(nopython=True, cache=True)
def is_nonsolid(block_id, nonsolid_array):
    for nonsolid_id in nonsolid_array:
        if block_id == nonsolid_id:
            return True
    return False

@jit(nopython=True, cache=True)
def generate_face_culling_mesh_v7(cx, cz, block_data, light_map):
    MAX_FACES = CHUNK_SIZE * CHUNK_SIZE * MAX_HEIGHT * 6
    MAX_VERTS = MAX_FACES * 4 * 7
    vertices = np.empty(MAX_VERTS, dtype=np.float32)
    indices = np.empty(MAX_FACES * 6, dtype=np.uint32)

    vert_count = 0
    index_count = 0
    index_offset = 0

    base_x = cx * CHUNK_SIZE
    base_z = cz * CHUNK_SIZE

    dx, dy, dz = block_data.shape

    for x in range(1, dx - 1):
        for z in range(1, dz - 1):
            for y in range(dy):
                block_id = block_data[x, y, z]

                if block_id == ID_AIR:
                    continue

                is_current_leaves = (block_id == ID_LEAVES)
                is_current_water = (block_id == ID_WATER)  # <--- Check
                # Kaktus ist jetzt ein ganz normaler Block, keine Sonderbehandlung mehr hier!

                wx = base_x + x - 1
                wz = base_z + z - 1

                for i_face in range(6):
                    nx, ny, nz = CUBE_NORMALS[i_face]
                    neighbor_x = x + int(nx)
                    neighbor_y = y + int(ny)
                    neighbor_z = z + int(nz)

                    is_face_visible = False

                    if neighbor_y < 0 or neighbor_y >= MAX_HEIGHT:
                        is_face_visible = True
                    elif 0 <= neighbor_x < dx and 0 <= neighbor_z < dz:
                        neighbor_id = block_data[neighbor_x, neighbor_y, neighbor_z]

                        # SPEZIALFALL WASSER
                        if is_current_water:
                            if neighbor_id != ID_WATER:
                                is_face_visible = True

                        elif is_current_leaves:
                            if neighbor_id == ID_AIR or neighbor_id == ID_LEAVES:
                                is_face_visible = True
                        else:
                            # DIESER FALL BEHANDELT SAND, ERDE, STEIN
                            is_neighbor_nonsolid = is_nonsolid(neighbor_id, NON_SOLID_BLOCKS_NUMBA)
                            if is_neighbor_nonsolid:
                                is_face_visible = True

                    if is_face_visible:
                        start_vert_idx = vert_count
                        texture_index = -1.0

                        # --- TEXTUR ZUWEISUNG ---
                        if block_id == ID_GRASS:
                            texture_index = GRASS_TEXTURES[i_face]
                        elif block_id == ID_OAK_LOG:
                            texture_index = OAK_LOG_TEXTURES[i_face]
                        elif block_id == ID_LEAVES:
                            texture_index = TEX_INDEX_LEAVES
                        elif block_id == ID_DIRT:
                            texture_index = TEX_INDEX_DIRT
                        elif block_id == ID_STONE:
                            texture_index = TEX_INDEX_STONE
                        elif block_id == ID_SAND:
                            texture_index = TEX_INDEX_SAND
                        elif block_id == ID_CACTUS:
                            texture_index = CACTUS_TEXTURES[i_face]
                        elif block_id == ID_WATER:  # <--- NEU
                            texture_index = WATER_TEXTURES[i_face]

                        # Vertex Generation
                        for i_vert in range(4):
                            # WICHTIG: Immer CUBE_VERTICES verwenden!
                            vx = CUBE_VERTICES[i_face, i_vert, 0]
                            vy = CUBE_VERTICES[i_face, i_vert, 1]
                            vz = CUBE_VERTICES[i_face, i_vert, 2]

                            uv_u = CUBE_UVS[i_face, i_vert, 0]
                            uv_v = CUBE_UVS[i_face, i_vert, 1]

                            sunlight = calculate_minecraft_vertex_light(
                                light_map, block_data, x, y, z, i_face, i_vert, 0
                            )
                            blocklight = calculate_minecraft_vertex_light(
                                light_map, block_data, x, y, z, i_face, i_vert, 1
                            )

                            combined_light = max(sunlight, blocklight) * FACE_SHADING[i_face]

                            vertices[start_vert_idx] = wx + vx
                            vertices[start_vert_idx + 1] = y + vy
                            vertices[start_vert_idx + 2] = wz + vz
                            vertices[start_vert_idx + 3] = uv_u
                            vertices[start_vert_idx + 4] = uv_v
                            vertices[start_vert_idx + 5] = texture_index
                            vertices[start_vert_idx + 6] = combined_light

                            start_vert_idx += 7

                        vert_count += 28
                        indices[index_count] = index_offset
                        indices[index_count + 1] = index_offset + 1
                        indices[index_count + 2] = index_offset + 2
                        indices[index_count + 3] = index_offset + 2
                        indices[index_count + 4] = index_offset + 3
                        indices[index_count + 5] = index_offset

                        index_count += 6
                        index_offset += 4

    return (vertices[:vert_count].reshape(-1, 7), indices[:index_count])