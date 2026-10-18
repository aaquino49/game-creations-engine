class_name TestCase
extends RefCounted
## Base class for headless unit tests. See tests/README.md.
##
## Every method whose name starts with `test_` is run by tests/run_tests.gd.
## Optional hooks: before_each() / after_each().
## `tree` gives access to the SceneTree for tests that need nodes (add them under tree.root
## and free them in after_each).

var tree: SceneTree
var _failures: Array[String] = []


func before_each() -> void:
	pass


func after_each() -> void:
	pass


func temp_path(name: String, extension: String = "") -> String:
	var suffix: String = "." + extension.trim_prefix(".") if not extension.is_empty() else ""
	return "user://test_%s_%d%s" % [name, OS.get_process_id(), suffix]


func remove_test_temp_file(path: String) -> void:
	var absolute_path: String = ProjectSettings.globalize_path(path)
	if FileAccess.file_exists(path):
		assert_eq(DirAccess.remove_absolute(absolute_path), OK, "Remove temporary file: " + path)


func fail(message: String) -> void:
	_failures.append(message)


func assert_true(value: bool, message: String = "") -> void:
	if not value:
		fail("expected true. " + message)


func assert_false(value: bool, message: String = "") -> void:
	if value:
		fail("expected false. " + message)


func assert_eq(actual: Variant, expected: Variant, message: String = "") -> void:
	if typeof(actual) != typeof(expected) or actual != expected:
		fail("expected %s, got %s. %s" % [var_to_str(expected), var_to_str(actual), message])


func assert_ne(actual: Variant, not_expected: Variant, message: String = "") -> void:
	if typeof(actual) == typeof(not_expected) and actual == not_expected:
		fail("expected value != %s. %s" % [var_to_str(not_expected), message])


func assert_almost_eq(actual: float, expected: float, tolerance: float = 0.001, message: String = "") -> void:
	if absf(actual - expected) > tolerance:
		fail("expected %f +/- %f, got %f. %s" % [expected, tolerance, actual, message])


func assert_gt(actual: Variant, bound: Variant, message: String = "") -> void:
	if not actual > bound:
		fail("expected %s > %s. %s" % [str(actual), str(bound), message])


func assert_lt(actual: Variant, bound: Variant, message: String = "") -> void:
	if not actual < bound:
		fail("expected %s < %s. %s" % [str(actual), str(bound), message])


func assert_not_null(value: Variant, message: String = "") -> void:
	if value == null:
		fail("expected non-null. " + message)


func assert_has(container: Variant, item: Variant, message: String = "") -> void:
	if not container.has(item):
		fail("expected container to have %s. %s" % [str(item), message])
