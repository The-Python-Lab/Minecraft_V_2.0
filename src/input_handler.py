# --- src/input_handler.py ---
import glfw


class InputHandler:
    def __init__(self, window, game_world):
        self.window = window
        self.game_world = game_world
        self._setup_callbacks()

    def _setup_callbacks(self):
        # Wir speichern die Instanz von InputHandler am Fenster, um im Static Callback drauf zuzugreifen
        glfw.set_window_user_pointer(self.window, self)

        def mouse_callback(window, xpos, ypos):
            handler = glfw.get_window_user_pointer(window)
            if handler: handler.on_mouse_move(xpos, ypos)

        def key_callback(window, key, scancode, action, mods):
            handler = glfw.get_window_user_pointer(window)
            if handler: handler.on_key(key, action)

        def mouse_btn_callback(window, button, action, mods):
            handler = glfw.get_window_user_pointer(window)
            if handler: handler.on_mouse_button(button, action)

        def scroll_callback(window, xoffset, yoffset):
            handler = glfw.get_window_user_pointer(window)
            if handler: handler.on_scroll(yoffset)

        def focus_callback(window, focused):
            handler = glfw.get_window_user_pointer(window)
            if handler: handler.on_focus(focused)

        glfw.set_cursor_pos_callback(self.window, mouse_callback)
        glfw.set_key_callback(self.window, key_callback)
        glfw.set_mouse_button_callback(self.window, mouse_btn_callback)
        glfw.set_scroll_callback(self.window, scroll_callback)
        glfw.set_window_focus_callback(self.window, focus_callback)

    def on_mouse_move(self, xpos, ypos):
        self.game_world.handle_mouse_move(xpos, ypos)

    def on_key(self, key, action):
        self.game_world.handle_key(key, action)

    def on_mouse_button(self, button, action):
        self.game_world.handle_mouse_button(button, action)

    def on_scroll(self, yoffset):
        self.game_world.handle_scroll(yoffset)

    def on_focus(self, focused):
        self.game_world.handle_focus(focused)