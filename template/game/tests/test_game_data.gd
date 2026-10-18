extends TestCase
## GameData loads every JSON file under res://data as a table.


func test_load_default_reads_balance() -> void:
	var data := GameData.load_default()
	assert_true(data.has_table("balance"))
	assert_eq(data.balance("example_tunable"), 1.0, "JSON numbers load as floats")


func test_balance_default_for_missing_key() -> void:
	var data := GameData.load_default()
	assert_eq(data.balance("no_such_key_xyz", 7), 7)


func test_ids_are_sorted() -> void:
	var data := GameData.new()
	data.tables["things"] = {"b": {}, "a": {}, "c": {}}
	assert_eq(data.ids("things"), ["a", "b", "c"] as Array[String])


func test_entry_missing_returns_empty() -> void:
	var data := GameData.new()
	data.tables["things"] = {"a": {"x": 1}}
	assert_eq(data.entry("things", "a"), {"x": 1})
	assert_eq(data.entry("things", "zzz"), {}, "missing ids push_error and return {} (ERROR line expected)")
