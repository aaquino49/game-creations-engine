extends Node
## Developer harness used by the automated pipeline. Inert during normal play.
##
## User args (after `--` on the godot command line):
##   --scenario=<name>    run res://dev/scenarios/<name>.gd `static func setup(main: Node) -> void`
##                        after the main scene is ready
##   --screenshot=<path>  save a PNG of the viewport to <path> (absolute path), then quit
##   --frames=<n>         frames to wait before the screenshot / quit (default 90)
##   --quit-frames=<n>    quit after n frames without a screenshot (smoke runs)

var _args: Dictionary = {}
var _frame: int = 0
var _target_frames: int = -1
var _screenshot_path: String = ""


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	# Also scan engine args, so a forgotten `--` separator doesn't leave a headless run going forever.
	for arg in OS.get_cmdline_args() + OS.get_cmdline_user_args():
		if arg.begins_with("--") and arg.contains("="):
			var kv := arg.substr(2).split("=", true, 1)
			_args[kv[0]] = kv[1]
	if _args.has("screenshot"):
		_screenshot_path = _args["screenshot"]
		_target_frames = int(_args.get("frames", "90"))
	elif _args.has("quit-frames"):
		_target_frames = int(_args["quit-frames"])
	if _target_frames < 0 and DisplayServer.get_name() == "headless":
		# A headless game run with no quit flag would never exit and hang whoever started it.
		_target_frames = 600
		print("DevTools: headless run without --quit-frames/--screenshot; quitting after 600 frames")
	if _target_frames >= 0:
		_start_failsafe(FAILSAFE_SECONDS)
	if _args.has("scenario"):
		_run_scenario.call_deferred(_args["scenario"])


## True for pipeline runs (smoke, screenshot). Game code can use it to skip saving or intro delays.
func is_automated() -> bool:
	return _target_frames >= 0 or _args.has("scenario")


## True when the display server can render a viewport image (false on --headless).
static func screenshot_supported() -> bool:
	return DisplayServer.get_name() != "headless"


## Hard limit for automated runs. Runs on its own thread, so it fires even if game code is stuck in
## an infinite loop and frames stop advancing.
const FAILSAFE_SECONDS := 120.0
var _failsafe: Thread
var _failsafe_stop := false


func _start_failsafe(seconds: float) -> void:
	_failsafe = Thread.new()
	_failsafe.start(_failsafe_run.bind(seconds))


func _failsafe_run(seconds: float) -> void:
	var deadline := Time.get_ticks_msec() + int(seconds * 1000.0)
	while not _failsafe_stop and Time.get_ticks_msec() < deadline:
		OS.delay_msec(250)
	if not _failsafe_stop:
		print("ERROR: DevTools failsafe: automated run still going after %d s (game loop stuck in an infinite loop?) - killing process" % int(seconds))
		OS.delay_msec(200)
		OS.kill(OS.get_process_id())


func _exit_tree() -> void:
	if _failsafe != null:
		_failsafe_stop = true
		_failsafe.wait_to_finish()


func _run_scenario(scenario_name: String) -> void:
	var path := "res://dev/scenarios/%s.gd" % scenario_name
	if not ResourceLoader.exists(path):
		push_error("DevTools: scenario not found: " + path)
		return
	var main := get_tree().current_scene
	if main == null:
		await get_tree().process_frame
		main = get_tree().current_scene
	var script: GDScript = load(path)
	script.setup(main)
	print("DevTools: scenario '%s' applied" % scenario_name)


func _process(_delta: float) -> void:
	if _target_frames < 0:
		return
	_frame += 1
	if _frame < _target_frames:
		return
	_target_frames = -1
	if _screenshot_path != "":
		if not screenshot_supported():
			print("DevTools: --screenshot needs a windowed run (headless has no renderer); no PNG written to %s" % _screenshot_path)
		else:
			await RenderingServer.frame_post_draw
			var img := get_viewport().get_texture().get_image()
			if img == null or img.is_empty():
				print("DevTools: screenshot failed (empty viewport image)")
			else:
				var err := img.save_png(_screenshot_path)
				print("DevTools: screenshot saved to %s (err=%d)" % [_screenshot_path, err])
	Game.request_quit()
