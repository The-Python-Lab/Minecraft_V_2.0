import glfw
from src.opengl_core import init_window
from src.game_world import run_game  # Import der neuen Hauptfunktion

# Fenstergröße
WIDTH, HEIGHT = 1280, 800


def main():
    """Initialisiert das Fenster und startet den Game-Loop."""

    # 1. Fenster initialisieren
    window, shader = init_window(WIDTH, HEIGHT, "Minecraft Threaded World - Refactored")

    # 2. Game-Loop starten (ausgelagert in src/game_world.py)
    run_game(window, shader, WIDTH, HEIGHT)

    # 3. Aufräumen (nach Beendigung des Game-Loops)
    glfw.terminate()


if __name__ == "__main__":
    main()