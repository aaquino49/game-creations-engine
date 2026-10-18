extends Node
## Entry point. Holds ScreenRoot, under which Game swaps the current screen.


func _ready() -> void:
	Game.register_main(self)
	Game.goto_screen(Game.TITLE_SCREEN)
