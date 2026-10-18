class_name Dice
extends RefCounted
## Seeded randomness for the simulation. Never use the global randi()/randf() in scripts/sim/.
##
## Every roll goes through range_i(), so tests can script exact outcomes:
##   var dice := Dice.forced([100, 3])  # next range_i() returns 100, then 3, then falls back to the seed
## Forced values are returned as-is (not clamped), so pick values valid for the call you are scripting.
##   roll(chance) uses range_i(1, 100): force 1 to succeed, 100 to fail (unless chance >= 100).

var _rng := RandomNumberGenerator.new()
var _forced: Array[int] = []


func _init(seed_value: int = 0) -> void:
	_rng.seed = seed_value


static func forced(values: Array, seed_value: int = 0) -> Dice:
	var d := Dice.new(seed_value)
	for v in values:
		d._forced.append(int(v))
	return d


## Queue more forced values (consumed before the seeded generator).
func push_forced(values: Array) -> void:
	for v in values:
		_forced.append(int(v))


## Inclusive integer in [lo, hi].
func range_i(lo: int, hi: int) -> int:
	if not _forced.is_empty():
		return _forced.pop_front()
	return _rng.randi_range(lo, hi)


func get_state() -> int:
	return _rng.state


func set_state(value: int) -> void:
	_rng.state = value


## True with `chance_pct`% probability (0-100). <= 0 never, >= 100 always (no roll consumed).
func roll(chance_pct: float) -> bool:
	if chance_pct >= 100.0:
		return true
	if chance_pct <= 0.0:
		return false
	return float(range_i(1, 100)) <= chance_pct


## Float in [0, 1).
func unit() -> float:
	return float(range_i(0, 9999)) / 10000.0


## A random element (null if empty).
func pick(items: Array) -> Variant:
	if items.is_empty():
		return null
	return items[range_i(0, items.size() - 1)]


## Index chosen by integer/float weights (-1 if all weights are 0).
func weighted_index(weights: Array) -> int:
	var total := 0.0
	for w in weights:
		total += float(w)
	if total <= 0.0:
		return -1
	var r := unit() * total
	for i in weights.size():
		r -= float(weights[i])
		if r < 0.0:
			return i
	return weights.size() - 1


## Fisher-Yates shuffle in place.
func shuffle(items: Array) -> void:
	for i in range(items.size() - 1, 0, -1):
		var j := range_i(0, i)
		var tmp: Variant = items[i]
		items[i] = items[j]
		items[j] = tmp


func to_dict() -> Dictionary:
	return {"seed": str(_rng.seed), "state": str(_rng.state)}


static func from_dict(d: Dictionary) -> Dice:
	var dice := Dice.new()
	dice._rng.seed = int(str(d.get("seed", "0")))
	dice._rng.state = int(str(d.get("state", "0")))
	return dice
