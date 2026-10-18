extends Node
## Screen router and owner of the shared game data (and, from M4, the current CampaignState).
##
## Screens are scenes whose root script implements `func open(args: Dictionary) -> void`.
## `main.tscn` has a `ScreenRoot` node; goto_screen() replaces its child.

const TITLE_SCREEN := "res://scenes/ui/title_screen.tscn"

var data: GameData
var current_screen: Node
var _main: Node
var _quitting: bool = false


func _ready() -> void:
	data = GameData.load_default()


## Called by main.gd so screens can be swapped from its _ready (current_scene may not be set yet).
func register_main(main: Node) -> void:
	_main = main


## Replace the current screen with the scene at `path` and call its open(args).
func goto_screen(path: String, args: Dictionary = {}) -> Node:
	var root := _screen_root()
	if root == null:
		push_error("Game.goto_screen: main scene has no ScreenRoot")
		return null
	var packed := load(path) as PackedScene
	if packed == null:
		push_error("Game.goto_screen: cannot load " + path)
		return null
	if current_screen != null and is_instance_valid(current_screen):
		root.remove_child(current_screen)
		current_screen.queue_free()
	current_screen = packed.instantiate()
	root.add_child(current_screen)
	if current_screen.has_method("open"):
		current_screen.call("open", args)
	Events.screen_changed.emit(path)
	return current_screen


func request_quit(exit_code: int = 0) -> void:
	if _quitting:
		return
	_quitting = true
	get_tree().quit(exit_code)


func _screen_root() -> Node:
	var main := _main if _main != null and is_instance_valid(_main) else get_tree().current_scene
	return main.get_node_or_null("ScreenRoot") if main != null else null
