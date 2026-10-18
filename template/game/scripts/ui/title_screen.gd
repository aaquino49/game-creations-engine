extends Control
## Title screen. Buttons for features that don't exist yet stay disabled until their milestone wires them up.

@onready var _new_btn: Button = %NewCampaign
@onready var _continue_btn: Button = %Continue
@onready var _skirmish_btn: Button = %Skirmish
@onready var _quit_btn: Button = %Quit
@onready var _version: Label = %Version


func open(_args: Dictionary) -> void:
	pass


func _ready() -> void:
	_version.text = "v" + str(ProjectSettings.get_setting("application/config/version", "0.0.0"))
	_new_btn.disabled = true
	_continue_btn.disabled = true
	_skirmish_btn.disabled = true
	_quit_btn.pressed.connect(func() -> void: Game.request_quit())
