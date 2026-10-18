extends TestCase
## Dice: seeded, reproducible, and scriptable with forced values.


func test_same_seed_same_rolls() -> void:
	var a := Dice.new(42)
	var b := Dice.new(42)
	for i in 20:
		assert_eq(a.range_i(1, 100), b.range_i(1, 100))


func test_forced_values_come_first() -> void:
	var d := Dice.forced([7, 99])
	assert_eq(d.range_i(1, 100), 7)
	assert_eq(d.range_i(1, 100), 99)
	var v := d.range_i(1, 6)
	assert_true(v >= 1 and v <= 6, "falls back to the seeded generator")


func test_roll_uses_1_to_100() -> void:
	assert_true(Dice.forced([50]).roll(50.0), "50 <= 50 succeeds")
	assert_false(Dice.forced([51]).roll(50.0), "51 > 50 fails")
	assert_true(Dice.forced([]).roll(100.0), "100% always succeeds")
	assert_false(Dice.forced([1]).roll(0.0), "0% never succeeds")


func test_weighted_index() -> void:
	assert_eq(Dice.forced([0]).weighted_index([1, 1]), 0)
	assert_eq(Dice.forced([9999]).weighted_index([1, 1]), 1)
	assert_eq(Dice.new().weighted_index([0, 0]), -1)


func test_save_round_trip_continues_sequence() -> void:
	var a := Dice.new(1234)
	a.range_i(1, 100)
	var b := Dice.from_dict(a.to_dict())
	for i in 10:
		assert_eq(a.range_i(1, 1000), b.range_i(1, 1000))
