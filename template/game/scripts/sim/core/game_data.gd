class_name GameData
extends RefCounted
## All JSON content and balance data, loaded once.
##
## Every `res://data/<name>.json` becomes a table named `<name>`.
## Content files (classes, skills, enemies, quirks, ...) are Dictionaries keyed by id:
##   { "gut_stab": { "name": "Gut Stab", ... }, ... }
## List files (trinkets, regions, ...) are top-level JSON arrays, read with `list()`:
##   [ { "id": "lucky_rock", ... }, ... ]
## `balance.json` is a flat Dictionary of global tunables, read with `balance()`.
##
## Use `GameData.load_default()` in game code and tests. `GameData.new()` is EMPTY.

const DATA_DIR := "res://data"

var tables: Dictionary = {}


static func load_default() -> GameData:
	return load_dir(DATA_DIR)


static func load_dir(dir_path: String) -> GameData:
	var gd := GameData.new()
	var dir := DirAccess.open(dir_path)
	if dir == null:
		push_error("GameData: cannot open " + dir_path)
		return gd
	for file in dir.get_files():
		if file.ends_with(".json"):
			gd.load_file(dir_path.path_join(file))
	return gd


## Load one JSON file into the table named after its basename. Returns false on error.
func load_file(path: String) -> bool:
	var text := FileAccess.get_file_as_string(path)
	var parsed: Variant = JSON.parse_string(text)
	if not parsed is Dictionary and not parsed is Array:
		push_error("GameData: %s is not a JSON object or array" % path)
		return false
	tables[path.get_file().get_basename()] = parsed
	return true


func has_table(table_name: String) -> bool:
	return tables.has(table_name)


## A whole table (empty Dictionary if missing or a list file).
func table(table_name: String) -> Dictionary:
	var stored: Variant = tables.get(table_name, {})
	return stored if stored is Dictionary else {}


## A whole list file (empty Array if missing or an object file).
func list(table_name: String) -> Array:
	var stored: Variant = tables.get(table_name, [])
	return stored if stored is Array else []


## One entry by id. Pushes an error and returns {} if it doesn't exist.
func entry(table_name: String, id: String) -> Dictionary:
	var t := table(table_name)
	if not t.has(id):
		push_error("GameData: no '%s' in table '%s'" % [id, table_name])
		return {}
	return t[id]


## Ids of a table, sorted, so iteration order is stable across runs.
func ids(table_name: String) -> Array[String]:
	var out: Array[String] = []
	for k in table(table_name).keys():
		out.append(str(k))
	out.sort()
	return out


## A global tunable from balance.json.
func balance(key: String, default: Variant = null) -> Variant:
	var b := table("balance")
	if not b.has(key):
		if default == null:
			push_error("GameData: balance.json has no '%s'" % key)
		return default
	return b[key]
