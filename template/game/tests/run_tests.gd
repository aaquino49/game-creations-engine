extends SceneTree
## Headless test runner.
##   godot --headless --path game --script res://tests/run_tests.gd [-- --filter=<substring>]
## Runs every res://tests/test_*.gd (recursively). Exit code 0 = all passed, 1 = failures.
## Prints one line per test and a final "TESTS: <passed> passed, <failed> failed" summary.
## A runtime SCRIPT ERROR inside a test (or its before_each/after_each) fails that test and reports file:line.
## Deliberate push_error() calls do not fail tests.


class ScriptErrorCatcher extends Logger:
	var errors: Array[String] = []

	func _log_error(function: String, file: String, line: int, code: String, rationale: String,
			_editor_notify: bool, error_type: int, _script_backtraces: Array[ScriptBacktrace]) -> void:
		if error_type == Logger.ERROR_TYPE_SCRIPT:
			errors.append("SCRIPT ERROR %s %s at %s:%d in %s()" % [code, rationale, file, line, function])


func _initialize() -> void:
	var filter := ""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--filter="):
			filter = arg.substr(9)
	var catcher := ScriptErrorCatcher.new()
	OS.add_logger(catcher)
	var files: Array[String] = []
	_collect("res://tests", files)
	files.sort()
	var passed := 0
	var failed := 0
	for path in files:
		var script: GDScript = load(path)
		if script == null or not script.can_instantiate():
			print("FAIL %s (script failed to load/compile)" % path)
			failed += 1
			continue
		for method in script.get_script_method_list():
			var method_name: String = method["name"]
			if not method_name.begins_with("test_"):
				continue
			if filter != "" and not (path + ":" + method_name).contains(filter):
				continue
			var test_obj: Object = script.new()
			if not test_obj is TestCase:
				print("FAIL %s (does not extend TestCase)" % path)
				failed += 1
				break
			var test := test_obj as TestCase
			test.tree = self
			catcher.errors.clear()
			test.before_each()
			test.call(method_name)
			test.after_each()
			for e in catcher.errors:
				test.fail(e)
			if test._failures.is_empty():
				passed += 1
				print("PASS %s:%s" % [path.get_file(), method_name])
			else:
				failed += 1
				print("FAIL %s:%s" % [path.get_file(), method_name])
				for f in test._failures:
					print("    - " + f)
	print("TESTS: %d passed, %d failed" % [passed, failed])
	OS.remove_logger(catcher)
	quit(1 if failed > 0 else 0)


func _collect(dir_path: String, out: Array[String]) -> void:
	var dir := DirAccess.open(dir_path)
	if dir == null:
		return
	for sub in dir.get_directories():
		_collect(dir_path.path_join(sub), out)
	for f in dir.get_files():
		if f.begins_with("test_") and f.ends_with(".gd") and f != "test_case.gd":
			out.append(dir_path.path_join(f))
