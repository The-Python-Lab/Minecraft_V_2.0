import numpy as np
import math
import glfw
from pyrr import Matrix44

# Player-Konstanten
PLAYER_HEIGHT = 1.8
PLAYER_EYE_HEIGHT = 1.62
PLAYER_WIDTH = 0.6
PLAYER_HALF_WIDTH = PLAYER_WIDTH / 2.0

# --- PHYSIK & GESCHWINDIGKEIT ---
GRAVITY = 32.0
JUMP_VELOCITY = 9.5  # Etwas höher für sportlicheres Gefühl
FRICTION_GROUND = 0.82  # Gute Bodenhaftung

# Geschwindigkeit (DEUTLICH SCHNELLER)
WALK_SPEED = 14.0  # Vorher 6.0 -> Jetzt viel schneller
SPRINT_SPEED = 22.0  # Sprint-Tempo

MOUSE_SENSITIVITY = 0.15


class Player:
    def __init__(self, position, yaw, pitch, speed=WALK_SPEED, rot_speed=120.0):
        self.pos = position
        self.yaw = yaw
        self.pitch = pitch
        self.speed = speed
        self.rot_speed = rot_speed
        self.height = PLAYER_HEIGHT
        self.eye_height = PLAYER_EYE_HEIGHT

        self.fovy = 60.0
        self.near = 0.1
        self.far = 512.0

        self.forward = np.zeros(3, dtype=np.float32)
        self.right = np.zeros(3, dtype=np.float32)

        self.velocity = np.zeros(3, dtype=np.float32)
        self.target_velocity = np.zeros(3, dtype=np.float32)
        self.on_ground = False
        self.FLYING = False

        self.mouse_dx = 0.0
        self.mouse_dy = 0.0
        self.update_view_vectors()

    def update_view_vectors(self):
        """Berechnet die Vektoren Forward und Right basierend auf Yaw und Pitch."""
        self.forward[0] = math.sin(math.radians(self.yaw)) * math.cos(math.radians(self.pitch))
        self.forward[1] = math.sin(math.radians(self.pitch))
        self.forward[2] = -math.cos(math.radians(self.yaw)) * math.cos(math.radians(self.pitch))
        self.forward = self.forward / np.linalg.norm(self.forward)

        forward_xz = self.forward.copy()
        forward_xz[1] = 0.0
        if np.linalg.norm(forward_xz) > 0:
            forward_xz = forward_xz / np.linalg.norm(forward_xz)

        self.right = np.cross([0.0, 1.0, 0.0], forward_xz)
        if np.linalg.norm(self.right) > 0:
            self.right = self.right / np.linalg.norm(self.right)

    def handle_mouse_input(self):
        if self.mouse_dx != 0.0 or self.mouse_dy != 0.0:
            self.yaw += self.mouse_dx * MOUSE_SENSITIVITY
            self.pitch += self.mouse_dy * MOUSE_SENSITIVITY
            self.pitch = max(-89.0, min(89.0, self.pitch))
            self.mouse_dx = 0.0
            self.mouse_dy = 0.0
            self.update_view_vectors()

    def apply_movement_input(self, window, dt):
        # Sprinten Logik
        current_move_speed = self.speed
        if glfw.get_key(window, glfw.KEY_LEFT_SHIFT) == glfw.PRESS:
            current_move_speed = SPRINT_SPEED

        target_v = np.array([0.0, 0.0, 0.0], dtype=np.float32)

        if glfw.get_key(window, glfw.KEY_W) == glfw.PRESS: target_v += self.forward
        if glfw.get_key(window, glfw.KEY_S) == glfw.PRESS: target_v -= self.forward
        if glfw.get_key(window, glfw.KEY_D) == glfw.PRESS: target_v += self.right
        if glfw.get_key(window, glfw.KEY_A) == glfw.PRESS: target_v -= self.right

        if not self.FLYING:
            if glfw.get_key(window, glfw.KEY_SPACE) == glfw.PRESS and self.on_ground:
                self.velocity[1] = JUMP_VELOCITY
                self.on_ground = False
            target_v[1] = 0.0

        horizontal_target_v = target_v[[0, 2]]
        if np.linalg.norm(horizontal_target_v) > 0:
            scale = current_move_speed / np.linalg.norm(horizontal_target_v)
            target_v[0] = horizontal_target_v[0] * scale
            target_v[2] = horizontal_target_v[1] * scale

        self.target_velocity[:] = target_v

    def get_aabb(self):
        """Gibt die AABB des Spielers zurück."""
        min_x = self.pos[0] - PLAYER_HALF_WIDTH
        max_x = self.pos[0] + PLAYER_HALF_WIDTH
        min_y = self.pos[1]
        max_y = self.pos[1] + PLAYER_HEIGHT
        min_z = self.pos[2] - PLAYER_HALF_WIDTH
        max_z = self.pos[2] + PLAYER_HALF_WIDTH
        return np.array([min_x, min_y, min_z, max_x, max_y, max_z], dtype=np.float32)

    def check_block_intersection(self, bx, by, bz):
        """Prüft, ob der Spieler mit dem Block an (bx, by, bz) kollidiert."""
        p_aabb = self.get_aabb()
        b_min_x, b_max_x = bx, bx + 1.0
        b_min_y, b_max_y = by, by + 1.0
        b_min_z, b_max_z = bz, bz + 1.0

        overlap_x = (p_aabb[0] < b_max_x and p_aabb[3] > b_min_x)
        overlap_y = (p_aabb[1] < b_max_y and p_aabb[4] > b_min_y)
        overlap_z = (p_aabb[2] < b_max_z and p_aabb[5] > b_min_z)
        return overlap_x and overlap_y and overlap_z

    def is_block_solid(self, block_x, block_y, block_z, world_data, chunk_size):
        if block_y < 0 or block_y >= 256: return True
        cx = int(np.floor(block_x / chunk_size))
        cz = int(np.floor(block_z / chunk_size))
        bx = int(block_x - cx * chunk_size)
        bz = int(block_z - cz * chunk_size)
        by = int(block_y)

        coord = (cx, cz)
        if coord in world_data:
            block_data = world_data[coord]
            local_x_data = bx + 1
            local_z_data = bz + 1
            if 0 <= local_x_data < chunk_size + 2 and 0 <= by < block_data.shape[
                1] and 0 <= local_z_data < chunk_size + 2:
                b_id = block_data[local_x_data, by, local_z_data]
                # Es ist solide, wenn es NICHT Luft (-1.0) UND NICHT Wasser (7.0) ist.
                return b_id != -1.0 and b_id != 7.0
        return False

    def check_collisions(self, motion, world_data, chunk_size):
        AABB = self.get_aabb()
        min_x_block = math.floor(AABB[0])
        max_x_block = math.ceil(AABB[3])
        min_y_block = math.floor(AABB[1])
        max_y_block = math.ceil(AABB[4])
        min_z_block = math.floor(AABB[2])
        max_z_block = math.ceil(AABB[5])

        on_ground_new = False

        for axis in [1, 0, 2]:
            if motion[axis] == 0: continue
            AABB[axis] += motion[axis]
            AABB[axis + 3] += motion[axis]

            if axis == 0:
                block_range_y = range(min_y_block, max_y_block)
                block_range_z = range(min_z_block, max_z_block)
                test_coord_idx = 0 if motion[0] < 0 else 3
                for y in block_range_y:
                    for z in block_range_z:
                        test_x = math.floor(AABB[test_coord_idx])
                        if self.is_block_solid(test_x, y, z, world_data, chunk_size):
                            correction = (test_x + 1.0 - AABB[0]) if motion[0] < 0 else (test_x - AABB[3])
                            AABB[0] += correction
                            AABB[3] += correction
                            motion[0] = 0.0
                            break
                    if motion[0] == 0.0: break

            elif axis == 1:
                block_range_x = range(min_x_block, max_x_block)
                block_range_z = range(min_z_block, max_z_block)
                test_coord_idx = 1 if motion[1] < 0 else 4
                for x in block_range_x:
                    for z in block_range_z:
                        test_y = math.floor(AABB[test_coord_idx])
                        if self.is_block_solid(x, test_y, z, world_data, chunk_size):
                            if motion[1] < 0:
                                correction = test_y + 1.0 - AABB[1]
                                on_ground_new = True
                            else:
                                correction = test_y - AABB[4]
                            AABB[1] += correction
                            AABB[4] += correction
                            motion[1] = 0.0
                            break
                    if motion[1] == 0.0: break

            elif axis == 2:
                block_range_x = range(min_x_block, max_x_block)
                block_range_y = range(min_y_block, max_y_block)
                test_coord_idx = 2 if motion[2] < 0 else 5
                for x in block_range_x:
                    for y in block_range_y:
                        test_z = math.floor(AABB[test_coord_idx])
                        if self.is_block_solid(x, y, test_z, world_data, chunk_size):
                            correction = (test_z + 1.0 - AABB[2]) if motion[2] < 0 else (test_z - AABB[5])
                            AABB[2] += correction
                            AABB[5] += correction
                            motion[2] = 0.0
                            break
                    if motion[2] == 0.0: break

        self.pos[0] = (AABB[0] + AABB[3]) / 2.0
        self.pos[1] = AABB[1]
        self.pos[2] = (AABB[2] + AABB[5]) / 2.0
        self.on_ground = on_ground_new
        return motion

    def apply_physics(self, dt, world_data, chunk_size):
        if self.on_ground:
            accel_factor = 0.35
            friction = FRICTION_GROUND
        else:
            accel_factor = 0.04
            friction = 0.98

        target_vxz = self.target_velocity[[0, 2]]
        current_vxz = self.velocity[[0, 2]]

        self.velocity[0] += (target_vxz[0] - current_vxz[0]) * accel_factor
        self.velocity[2] += (target_vxz[1] - current_vxz[1]) * accel_factor

        self.velocity[0] *= friction
        self.velocity[2] *= friction

        if not self.FLYING:
            self.velocity[1] -= GRAVITY * dt

        motion = self.velocity * dt
        corrected_motion = self.check_collisions(motion, world_data, chunk_size)

        if dt > 0:
            if corrected_motion[0] == 0.0 and abs(self.velocity[0]) > 0.0: self.velocity[0] = 0.0
            if corrected_motion[2] == 0.0 and abs(self.velocity[2]) > 0.0: self.velocity[2] = 0.0
            if corrected_motion[1] == 0.0: self.velocity[1] = 0.0

        if self.on_ground and self.velocity[1] < 0:
            self.velocity[1] = 0.0

    # --- DIE FEHLENDEN METHODEN WIEDER EINGEFÜGT ---

    def get_view_matrix(self):
        """Gibt die View-Matrix zurück (Kamera-Position in AUGENHÖHE)."""
        camera_pos = self.pos.copy()
        camera_pos[1] += self.eye_height
        return Matrix44.look_at(camera_pos, camera_pos + self.forward, [0.0, 1.0, 0.0])

    def raycast_block_selection(self, world_data, chunk_size, max_dist=10.0):
        """Führt einen Raycast durch, um den angezielten Block zu finden."""
        origin = self.pos.copy()
        origin[1] += self.eye_height
        direction = self.forward

        current_pos = origin.copy()
        step = 0.05
        steps_max = int(max_dist / step)

        last_block_pos = None

        for _ in range(steps_max):
            current_pos += direction * step
            wx, wy, wz = current_pos
            bx = int(np.floor(wx))
            by = int(np.floor(wy))
            bz = int(np.floor(wz))

            if self.is_block_solid(bx, by, bz, world_data, chunk_size):
                cx = int(np.floor(bx / chunk_size))
                cz = int(np.floor(bz / chunk_size))
                local_bx = bx - cx * chunk_size
                local_bz = bz - cz * chunk_size

                hit_block_info = ((cx, cz), local_bx, by, local_bz)

                if last_block_pos is not None:
                    place_bx, place_by, place_bz = last_block_pos
                    place_cx = int(np.floor(place_bx / chunk_size))
                    place_cz = int(np.floor(place_bz / chunk_size))
                    place_local_bx = place_bx - place_cx * chunk_size
                    place_local_bz = place_bz - place_cz * chunk_size
                    place_block_info = ((place_cx, place_cz), place_local_bx, place_by, place_local_bz)
                    return hit_block_info, place_block_info
                else:
                    return hit_block_info, None

            last_block_pos = (bx, by, bz)

        return None, None