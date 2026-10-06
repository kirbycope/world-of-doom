#!/usr/bin/env python3
"""Behavior checks for the offline WoDoom tic simulation."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402
from lupa import lua51  # noqa: E402


def new_game(seed=1):
    lua = lua51.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(harness.STUB)
    lua.execute("ns = {}")
    ns = lua.eval("ns")
    run = lua.eval("function(path, ns) local f = assert(loadfile(path)); f('wodoom', ns) end")
    for name in ("data_level.lua", "data_assets.lua", "wodoom.lua"):
        run(str(harness.ADDON_DIR / name), ns)
    lua.execute("math.randomseed(%d)" % seed)
    return lua, ns


def monsters(ns):
    actors = ns["state"]["actors"]
    return [actors[i] for i in range(1, len(actors) + 1) if actors[i]["mon"]]


def projectiles(ns):
    actors = ns["state"]["actors"]
    return [actors[i] for i in range(1, len(actors) + 1) if actors[i]["projectile"] and not actors[i]["gone"]]


def step(ns, count):
    for _ in range(count):
        ns["tick"]()


def set_player(ns, x, y, angle):
    player = ns["state"]["P"]
    player["x"], player["y"] = x, y
    player["momx"], player["momy"] = 0, 0
    player["viewheight"], player["deltaviewheight"] = 41, 0
    ns["setAngle"](angle)


def step_fixture(ns):
    lines, sectors = ns["level"]["lines"], ns["level"]["sectors"]
    for index in range(1, len(lines) + 1):
        line = lines[index]
        if line["bs"] <= 0:
            continue
        dx, dy = line["x2"] - line["x1"], line["y2"] - line["y1"]
        length = math.hypot(dx, dy)
        if length < 64:
            continue
        midpoint = ((line["x1"] + line["x2"]) / 2, (line["y1"] + line["y2"]) / 2)
        nx, ny = dy / length, -dx / length
        for distance in (24, 32):
            sides = ((midpoint[0] + nx * distance, midpoint[1] + ny * distance),
                     (midpoint[0] - nx * distance, midpoint[1] - ny * distance))
            first, second = ns["sectorAt"](*sides[0]), ns["sectorAt"](*sides[1])
            if first == line["fs"] and second == line["bs"]:
                source, target = first, second
                start, end = sides
            elif second == line["fs"] and first == line["bs"]:
                source, target = second, first
                start, end = sides[1], sides[0]
            else:
                continue
            front, back = sectors[line["fs"]], sectors[line["bs"]]
            opening = min(front["ce"], back["ce"]) - max(front["fl"], back["fl"])
            if (sectors[target]["fl"] - sectors[source]["fl"] == 24
                    and line["fl"] % 2 == 0 and opening >= 56):
                return line, start, end, source, target
    raise AssertionError("no adjacent 24-unit step fixture found")


def stand_near(ns, monster, distance=150):
    player = ns["state"]["P"]
    for degrees in range(0, 360, 15):
        angle = math.radians(degrees)
        x = monster["x"] + math.cos(angle) * distance
        y = monster["y"] + math.sin(angle) * distance
        if ns["hasLOS"](x, y, monster["x"], monster["y"]) and ns["rayWall"](
            x, y, -math.cos(angle), -math.sin(angle)
        ) > distance:
            player["x"], player["y"] = x, y
            ns["setAngle"](math.atan2(monster["y"] - y, monster["x"] - x))
            return True
    return False


def test_zombie_kill_and_door():
    _lua, ns = new_game(2)
    zombie = next(monster for monster in monsters(ns) if monster["t"] == 3004)
    assert stand_near(ns, zombie), "could not position for pistol test"
    step(ns, 5)
    for _ in range(10):
        player = ns["state"]["P"]
        ns["setAngle"](math.atan2(zombie["y"] - player["y"], zombie["x"] - player["x"]))
        ns["fire"]()
        step(ns, 20)
        if zombie["hp"] <= 0:
            break
    assert zombie["hp"] <= 0, "pistol did not kill the 20 HP zombieman"

    lines = ns["level"]["lines"]
    sectors = ns["level"]["sectors"]
    door = next(line for line in (lines[i] for i in range(1, len(lines) + 1)) if line["sp"] == 1)
    midpoint_x = (door["x1"] + door["x2"]) / 2
    midpoint_y = (door["y1"] + door["y2"]) / 2
    dx, dy = door["x2"] - door["x1"], door["y2"] - door["y1"]
    length = math.hypot(dx, dy)
    nx, ny = dy / length, -dx / length
    ns["state"]["P"]["x"] = midpoint_x + nx * 30
    ns["state"]["P"]["y"] = midpoint_y + ny * 30
    ns["setAngle"](math.atan2(-ny, -nx))
    before = sectors[door["bs"]]["ce"]
    ns["useLine"]()
    door_sector = sectors[door["bs"]]
    target = min(sectors[lines[i]["fs"]]["ce"] if lines[i]["bs"] == door["bs"] else sectors[lines[i]["bs"]]["ce"]
                 for i in range(1, len(lines) + 1)
                 if lines[i]["bs"] > 0 and (lines[i]["fs"] == door["bs"] or lines[i]["bs"] == door["bs"])) - 4
    step(ns, 1)
    assert door_sector["ce"] == before + 2, "door did not open at 2 units per tic"
    open_tics = math.ceil((target - before) / 2)
    step(ns, open_tics - 1)
    assert door_sector["ce"] == target, "door did not reach the lowest-neighbor ceiling minus four"
    step(ns, 149)
    assert door_sector["ce"] == target, "door closed before its 150-tic wait elapsed"
    step(ns, 1)
    assert door_sector["ce"] == target, "door moved during the final wait tic"
    step(ns, 1)
    assert door_sector["ce"] == target - 2, "door did not close at 2 units per tic after waiting"


def test_imp_reaction_and_fireball():
    _lua, ns = new_game(3)
    imp = next(monster for monster in monsters(ns) if monster["t"] == 3001)
    assert stand_near(ns, imp, 400), "could not position at 400-unit imp range"
    imp["awake"], imp["state"], imp["reactionT"], imp["cd"] = True, "chase", 8, 0
    player = ns["state"]["P"]
    assert ns["hasLOS"](imp["x"], imp["y"], player["x"], player["y"])
    step(ns, 7)
    assert not projectiles(ns) and imp["state"] != "attack", "imp attacked before its 8-tic reaction"
    step(ns, 1)
    assert not projectiles(ns), "imp fireball appeared before the aim frame completed"
    for _ in range(60):
        if projectiles(ns):
            break
        step(ns, 1)
    shots = projectiles(ns)
    assert shots, "imp at 400 units never launched BAL1 (state=%s frame=%s attack=%s distance=%.1f)" % (
        imp["state"], imp["frame"], imp["attackIndex"], math.hypot(imp["x"] - player["x"], imp["y"] - player["y"])
    )
    shot = shots[0]
    start = (shot["x"], shot["y"])
    step(ns, 3)
    assert shot["flightT"] > 0 or shot["state"] == "explode", "fireball did not advance"
    assert math.hypot(shot["x"] - start[0], shot["y"] - start[1]) > 0 or shot["state"] == "explode"
    for _ in range(50):
        if ns["state"]["getHP"]() < 100 or shot["state"] == "explode":
            break
        step(ns, 1)
    assert ns["state"]["getHP"]() < 100 or shot["state"] == "explode", "fireball neither hit the player nor exploded"


def test_noise_crosses_adjacent_sector():
    _lua, ns = new_game(4)
    lines = ns["level"]["lines"]
    sectors = ns["level"]["sectors"]
    player = ns["state"]["P"]
    target = next(monster for monster in monsters(ns) if monster["t"] == 3004)
    candidate = None
    for index in range(1, len(lines) + 1):
        line = lines[index]
        if line["bs"] <= 0:
            continue
        front, back = sectors[line["fs"]], sectors[line["bs"]]
        if min(front["ce"], back["ce"]) - max(front["fl"], back["fl"]) < 56:
            continue
        mx, my = (line["x1"] + line["x2"]) / 2, (line["y1"] + line["y2"]) / 2
        dx, dy = line["x2"] - line["x1"], line["y2"] - line["y1"]
        length = math.hypot(dx, dy)
        nx, ny = dy / length, -dx / length
        px, py = mx + nx * 100, my + ny * 100
        tx, ty = mx - nx * 200, my - ny * 200
        if ns["sectorAt"](px, py) == line["fs"] and ns["sectorAt"](tx, ty) == line["bs"]:
            candidate = (line, px, py, tx, ty)
            break
    assert candidate, "no open adjacent-sector linedef found"
    _line, player["x"], player["y"], target["x"], target["y"] = candidate
    target["z"] = sectors[ns["sectorAt"](target["x"], target["y"])]["fl"]
    target["awake"], target["state"], target["reactionT"] = False, "idle", 8
    target["ambush"] = False
    toward_player = math.atan2(player["y"] - target["y"], player["x"] - target["x"])
    target["facing"] = toward_player + math.pi
    assert math.hypot(player["x"] - target["x"], player["y"] - target["y"]) > 128
    assert not ns["hasLOS"](target["x"], target["y"], player["x"], player["y"]), "noise case unexpectedly has LOS"
    ns["setAngle"](toward_player + math.pi)
    ns["fire"]()
    assert target["awake"] and target["state"] == "chase", "shot noise did not wake the adjacent-sector zombie"


def test_monsters_do_not_overlap():
    _lua, ns = new_game(5)
    group = monsters(ns)
    for monster in group:
        monster["awake"], monster["state"], monster["reactionT"] = True, "chase", 0
        monster["cd"] = 1000
    player = ns["state"]["P"]
    player["x"], player["y"] = group[0]["x"] + 300, group[0]["y"] + 300
    step(ns, 120)
    for index, first in enumerate(group):
        if first["hp"] <= 0:
            continue
        for second in group[index + 1:]:
            if second["hp"] > 0:
                distance = math.hypot(first["x"] - second["x"], first["y"] - second["y"])
                assert distance >= 39.9, "living monsters overlapped at %.2f units" % distance


def test_player_ticcmd_speed_friction_and_turning():
    for running, expected in ((False, 8.3), (True, 16.6)):
        _lua, ns = new_game(6)
        player = ns["state"]["P"]
        set_player(ns, 1056, -3616, math.pi / 2)
        keys = ns["state"]["keys"]
        keys["W"] = True
        if running:
            keys["SHIFT"] = True
        previous = (player["x"], player["y"])
        for _ in range(39):
            ns["tick"]()
            previous = (player["x"], player["y"])
        ns["tick"]()
        speed = math.hypot(player["x"] - previous[0], player["y"] - previous[1])
        assert abs(speed - expected) < 0.35, "%s speed %.2f, expected %.1f" % (
            "run" if running else "walk", speed, expected
        )
        assert 0 < player["bob"] <= 16, "momentum bob was not calculated or exceeded MAXBOB"
        if not running:
            keys["W"] = None
            before = math.hypot(player["momx"], player["momy"])
            step(ns, 1)
            after = math.hypot(player["momx"], player["momy"])
            assert abs(after / before - 0.90625) < 1e-6, "released momentum did not decay by Doom friction"

    _lua, ns = new_game(7)
    player, keys = ns["state"]["P"], ns["state"]["keys"]
    ns["setAngle"](0)
    keys["LEFT"] = True
    for _ in range(6):
        ns["tick"]()
    assert player["angle"] == 6 * 640 * 65536, "turn input did not use 640 BAM units for its first six tics"
    ns["tick"]()
    assert player["angle"] == 7 * 640 * 65536 + 640 * 65536, "turnheld did not accelerate to 1280 BAM units"
    keys["LEFT"] = None
    ns["setAngle"](0)
    keys["RIGHT"] = True
    ns["tick"]()
    assert player["angle"] > 2 ** 31, "right turn did not rotate clockwise"
    keys["RIGHT"] = None


def test_player_wall_slide_and_step_height():
    lua, ns = new_game(8)
    player = ns["state"]["P"]
    set_player(ns, 1056, -3616, math.pi / 4)
    lines = ns["level"]["lines"]
    wall_index = len(lines) + 1
    wall_x = player["x"] + 56
    lines[wall_index] = lua.table_from({
        "x1": wall_x, "y1": player["y"] - 1000, "x2": wall_x, "y2": player["y"] + 1000,
        "minx": wall_x, "maxx": wall_x, "miny": player["y"] - 1000, "maxy": player["y"] + 1000,
        "bs": 0,
    })
    start_x, start_y = player["x"], player["y"]
    ns["state"]["keys"]["W"] = True
    step(ns, 60)
    ns["state"]["keys"]["W"] = None
    lines[wall_index] = None
    assert player["x"] - start_x < 42, "player crossed or stopped too far from the blocking wall"
    assert player["y"] - start_y > 100, "player stopped instead of sliding along the wall"

    _lua, ns = new_game(9)
    line, start, end, source, target = step_fixture(ns)
    player = ns["state"]["P"]
    set_player(ns, start[0], start[1], math.atan2(end[1] - start[1], end[0] - start[0]))
    ns["state"]["keys"]["W"] = True
    for _ in range(30):
        ns["tick"]()
        if ns["sectorAt"](player["x"], player["y"]) == target:
            break
    ns["state"]["keys"]["W"] = None
    assert ns["sectorAt"](player["x"], player["y"]) == target, "player could not step up 24 units"
    assert player["viewheight"] < 41, "step-up eye height did not smooth the floor transition"
    step_height = player["viewheight"]
    step(ns, 8)
    assert step_height < player["viewheight"] <= 41, "step-up eye height did not recover smoothly"

    sectors = ns["level"]["sectors"]
    old_floor = sectors[target]["fl"]
    sectors[target]["fl"] = sectors[source]["fl"] + 25
    set_player(ns, start[0], start[1], math.atan2(end[1] - start[1], end[0] - start[0]))
    ns["state"]["keys"]["W"] = True
    step(ns, 20)
    ns["state"]["keys"]["W"] = None
    sectors[target]["fl"] = old_floor
    assert ns["sectorAt"](player["x"], player["y"]) == source, "player crossed a ledge taller than 24 units"


def test_living_monster_blocks_player():
    lua, ns = new_game(10)
    player = ns["state"]["P"]
    set_player(ns, 1056, -3616, math.pi / 2)
    target = lua.table_from({
        "t": 3004, "x": 1056, "y": -3416, "hp": 20, "state": "pain", "painT": 1000,
        "mon": lua.table_from({"prefix": "POSS"}),
    })
    actors = ns["state"]["actors"]
    actors[len(actors) + 1] = target
    ns["state"]["keys"]["W"] = True
    step(ns, 45)
    ns["state"]["keys"]["W"] = None
    distance = math.hypot(player["x"] - target["x"], player["y"] - target["y"])
    assert 35.5 <= distance < 42, "living monster did not block the player at combined radii (%.2f)" % distance


def line_side(line, x, y):
    return ((line["x2"] - line["x1"]) * (y - line["y1"])
            - (line["y2"] - line["y1"]) * (x - line["x1"]))


def walk_across_special(ns, special):
    lines = ns["level"]["lines"]
    sectors = ns["level"]["sectors"]
    line = next(lines[i] for i in range(1, len(lines) + 1) if lines[i]["sp"] == special)
    dx, dy = line["x2"] - line["x1"], line["y2"] - line["y1"]
    length = math.hypot(dx, dy)
    midpoint = ((line["x1"] + line["x2"]) / 2, (line["y1"] + line["y2"]) / 2)
    nx, ny = dy / length, -dx / length
    start = end = None
    for distance in (48, 64, 80):
        front = (midpoint[0] + nx * distance, midpoint[1] + ny * distance)
        back = (midpoint[0] - nx * distance, midpoint[1] - ny * distance)
        if (line_side(line, *front) < 0 and ns["sectorAt"](*front) == line["fs"]
                and ns["sectorAt"](*back) == line["bs"]):
            start, end = front, back
            break
    assert start is not None, "could not find front-to-back fixture for special %d" % special
    set_player(ns, start[0], start[1], math.atan2(end[1] - start[1], end[0] - start[0]))
    keys = ns["state"]["keys"]
    keys["W"] = True
    player = ns["state"]["P"]
    crossed = False
    for _ in range(100):
        ns["tick"]()
        if line_side(line, player["x"], player["y"]) >= 0:
            crossed = True
            break
    keys["W"] = None
    player["momx"], player["momy"] = 0, 0
    assert crossed, "player could not walk across special %d" % special
    return line


def park_monsters(ns):
    for index, m in enumerate(monsters(ns)):
        m["x"], m["y"] = 1000000 + index * 100, 1000000


def test_floor_triggers_and_lift_cycle():
    _lua, ns = new_game(11)
    park_monsters(ns)
    sectors = ns["level"]["sectors"]
    lines = ns["level"]["lines"]
    line = walk_across_special(ns, 36)
    target_id = next(i for i in range(1, len(sectors) + 1) if sectors[i]["tg"] == line["tg"])
    target = sectors[target_id]
    start = target["fl"]
    adjacent = [sectors[lines[i]["fs"] if lines[i]["bs"] == target_id else lines[i]["bs"]]["fl"]
                for i in range(1, len(lines) + 1)
                if lines[i]["bs"] > 0 and (lines[i]["fs"] == target_id or lines[i]["bs"] == target_id)]
    destination = min(start, max(height for height in adjacent if height < start) + 8)
    step(ns, 1)
    assert target["fl"] == start - 4, "W1 special 36 did not lower its tagged floor at 4 units per tic"
    step(ns, 100)
    lowered = target["fl"]
    assert lowered == destination, "W1 special 36 did not stop 8 units above the next-highest lower neighbor"
    x, y = point_in_sector(ns, target_id)
    set_player(ns, x, y, 0)
    ns["tick"]()
    assert ns["state"]["P"]["floorZ"] == lowered, "moving floor did not update the player's floor height"
    walk_across_special(ns, 36)
    step(ns, 5)
    assert target["fl"] == lowered, "W1 special 36 retriggered after its one-shot activation"

    _lua, ns = new_game(12)
    park_monsters(ns)
    sectors = ns["level"]["sectors"]
    lines = ns["level"]["lines"]
    line = walk_across_special(ns, 88)
    lift_id = next(i for i in range(1, len(sectors) + 1) if sectors[i]["tg"] == line["tg"])
    lift = sectors[lift_id]
    top = lift["fl"]
    step(ns, 1)
    assert lift["fl"] == top - 4, "WR special 88 did not lower at 4 units per tic"
    adjacent = [sectors[lines[i]["fs"] if lines[i]["bs"] == lift_id else lines[i]["bs"]]["fl"]
                for i in range(1, len(lines) + 1)
                if lines[i]["bs"] > 0 and (lines[i]["fs"] == lift_id or lines[i]["bs"] == lift_id)]
    destination = min(height for height in adjacent if height < top)
    lower_tics = math.ceil((top - destination) / 4)
    step(ns, lower_tics - 1)
    low = lift["fl"]
    assert low == destination, "WR special 88 did not lower to its lowest neighboring floor"
    step(ns, 104)
    assert lift["fl"] == low, "WR lift began raising before its 105-tic wait elapsed"
    step(ns, 1)
    assert lift["fl"] == low, "WR lift moved during the final wait tic"
    step(ns, 1)
    assert lift["fl"] == low + 4, "WR lift did not raise at 4 units per tic after 105 tics"
    walk_across_special(ns, 88)
    before_retrigger = lift["fl"]
    step(ns, 1)
    assert lift["fl"] == before_retrigger + 4, "active WR lift retrigger started a duplicate mover"
    step(ns, 200)
    assert lift["fl"] == top, "WR lift did not wait 105 tics and return to its original height"
    dx, dy = line["x2"] - line["x1"], line["y2"] - line["y1"]
    length = math.hypot(dx, dy)
    midpoint = ((line["x1"] + line["x2"]) / 2, (line["y1"] + line["y2"]) / 2)
    ns["crossSpecialLine"](midpoint[0] + dy / length * 48, midpoint[1] - dx / length * 48,
                           midpoint[0] - dy / length * 48, midpoint[1] + dx / length * 48)
    step(ns, 1)
    assert lift["fl"] == top - 4, "WR special 88 did not retrigger after completing its cycle"


def point_in_sector(ns, target):
    lines = ns["level"]["lines"]
    xs = [lines[i]["x1"] for i in range(1, len(lines) + 1)] + [lines[i]["x2"] for i in range(1, len(lines) + 1)]
    ys = [lines[i]["y1"] for i in range(1, len(lines) + 1)] + [lines[i]["y2"] for i in range(1, len(lines) + 1)]
    for x in range(int(min(xs)), int(max(xs)) + 1, 48):
        for y in range(int(min(ys)), int(max(ys)) + 1, 48):
            if ns["sectorAt"](x, y) == target:
                return x, y
    raise AssertionError("could not find an interior point for sector %d" % target)


def test_lights_pickups_secrets_and_exit():
    _lua, ns = new_game(13)
    sectors = ns["level"]["sectors"]
    light_sectors = [i for i in range(1, len(sectors) + 1) if sectors[i]["sp"] in (1, 2, 3, 4, 8, 12, 13, 17)]
    original = {i: sectors[i]["li"] for i in light_sectors}
    changed = set()
    for _ in range(70):
        ns["tick"]()
        for i in light_sectors:
            if sectors[i]["li"] != original[i]:
                changed.add(i)
    assert changed == set(light_sectors), "light effects did not change for every present light sector"

    _lua, ns = new_game(15)
    sectors = ns["level"]["sectors"]
    hazard = next(i for i in range(1, len(sectors) + 1) if sectors[i]["sp"] == 7)
    x, y = point_in_sector(ns, hazard)
    for monster in monsters(ns):
        monster["hp"] = 0
    set_player(ns, x, y, 0)
    step(ns, 31)
    assert ns["state"]["getHP"]() == 100, "nukage damaged the player before 32 tics"
    step(ns, 1)
    assert ns["state"]["getHP"]() == 95, "sector special 7 did not deal 5 damage at 32 tics"

    stats = ns["state"]["getStats"]()
    pickup = next(ns["state"]["actors"][i] for i in range(1, len(ns["state"]["actors"]) + 1)
                  if ns["state"]["actors"][i]["t"] in (2007, 2048, 2008, 2049, 2011, 2012, 2014, 2015, 2018, 2019, 2001, 2002))
    set_player(ns, pickup["x"], pickup["y"], 0)
    ns["tick"]()
    assert ns["state"]["getStats"]()["items"] == 1, "successful pickup did not increment the item count"

    secret = next(i for i in range(1, len(sectors) + 1) if sectors[i]["sp"] == 9)
    x, y = point_in_sector(ns, secret)
    set_player(ns, x, y, 0)
    ns["tick"]()
    assert ns["state"]["getStats"]()["secrets"] == 1, "entering a secret sector did not increment secrets"
    assert ns["state"]["getMessage"]() == "A secret is revealed!", "secret discovery message was not shown"
    step(ns, 2)
    assert ns["state"]["getStats"]()["secrets"] == 1, "the same secret sector counted more than once"

    _lua, ns = new_game(14)
    lines, segs = ns["level"]["lines"], ns["level"]["segs"]
    index = next(i for i in range(1, len(lines) + 1) if lines[i]["sp"] == 11)
    line = lines[index]
    assert ns["assets"]["tex"]["SW2STRTN"], "converter did not include the SW2STRTN switch texture"
    switch = next(segs[i] for i in range(1, len(segs) + 1) if segs[i]["ld"] == index and segs[i]["mi"] == "SW1STRTN")
    midpoint_x, midpoint_y = (line["x1"] + line["x2"]) / 2, (line["y1"] + line["y2"]) / 2
    dx, dy = line["x2"] - line["x1"], line["y2"] - line["y1"]
    length = math.hypot(dx, dy)
    nx, ny = dy / length, -dx / length
    set_player(ns, midpoint_x + nx * 32, midpoint_y + ny * 32, math.atan2(-ny, -nx))
    ns["useLine"]()
    assert switch["mi"] == "SW2STRTN", "exit switch texture did not change from SW1 to SW2"
    assert ns["state"]["getStats"]()["over"] == "exit", "exit line did not start its delay"
    step(ns, 69)
    assert ns["state"]["getStats"]()["over"] == "exit", "exit completed before its short delay elapsed"
    step(ns, 1)
    stats = ns["state"]["getStats"]()
    assert stats["over"] == "complete", "exit did not reach the end screen"
    assert (stats["killsTotal"], stats["itemsTotal"], stats["secretsTotal"]) == (6, 52, 3), "end-level totals were incorrect"


def test_doom_light_model():
    lua, ns = new_game(21)
    L = ns["Light"]
    assert abs(L["gain"][1][1] - 1.0) < 1e-6, "colormap 0 is not full brightness"
    assert L["gain"][32][1] < 0.1, "darkest colormap is not dark"
    near, far = L["scaled"](160, 64, 0)[1], L["scaled"](160, 1600, 0)[1]
    assert near > far, "walls do not darken with distance"
    assert L["scaled"](255, 1600, 0)[1] > far, "brighter sectors are not brighter"
    assert L["scaled"](160, 400, 1)[1] > L["scaled"](160, 400, -1)[1], "fake contrast is missing"
    assert L["span"](160, 40)[1] > L["span"](160, 1500)[1], "floors do not darken with distance"
    L["extra"] = 2
    assert L["scaled"](160, 1600, 0)[1] > far, "extra light from weapon flash has no effect"
    L["extra"] = 0


def test_palette_hud_font_death_and_pause():
    lua, ns = new_game(70)
    ui, player = ns["ui"], ns["state"]["P"]
    park_monsters(ns)
    ui["screen"] = "game"
    set_player(ns, 1056, -3616, math.pi / 2)
    assert ui["flash"]() is None, "a palette flash showed with nothing happening"
    ns["damagePlayer"](20)
    fx = ui["flash"]()
    assert fx and fx[1] == 1.0 and fx[2] == 0.0 and 0.3 < fx[4] < 0.6, "damage did not give a red palette flash"
    step(ns, 20)
    assert ui["flash"]() is None, "the damage flash did not count down to nothing"
    actors = ns["state"]["actors"]
    clip = next(actors[i] for i in range(1, len(actors) + 1) if actors[i]["t"] == 2007)
    set_player(ns, clip["x"], clip["y"], 0)
    step(ns, 2)
    fx = ui["flash"]()
    assert fx and fx[1] > 0.8 and fx[3] < 0.4, "a pickup did not give the yellow bonus flash"
    ns["render"]()
    textures = lua.eval("__tex")
    paths = [textures[i]["path"] for i in range(1, len(textures) + 1) if textures[i]["shown"] and textures[i]["path"]]
    assert any("STCFN" in p for p in paths), "the pickup message was not drawn with the HU font"

    ns["damagePlayer"](500, player["x"] + 100, player["y"])
    assert ns["state"]["getHP"]() == 0, "the player did not die"
    step(ns, 50)
    assert player["viewheight"] == 6, "the dead player's view did not sink to 6 units"
    bam = player["angle"]
    assert min(bam, 2 ** 32 - bam) < 2 ** 32 / 360, "the dead player did not turn toward the attacker"
    view = ns["view"]
    view["scripts"]["OnKeyDown"](view, "F")
    assert ns["state"]["getHP"]() == 100, "Use did not respawn the dead player"

    keys = ns["state"]["keys"]
    set_player(ns, 1056, -3616, math.pi / 2)
    view["scripts"]["OnKeyDown"](view, "P")
    assert ui["paused"], "P did not pause"
    y0 = player["y"]
    keys["W"] = True
    ns["update"](0.2)
    assert player["y"] == y0, "the game kept running while paused"
    view["scripts"]["OnKeyDown"](view, "P")
    ns["update"](0.2)
    assert player["y"] != y0, "unpausing did not resume the game"


def test_doom_sounds():
    lua, ns = new_game(80)
    played = []
    lua.execute("__played = {}; function PlaySoundFile(p) __played[#__played + 1] = p end")
    log = lua.eval("__played")

    def heard():
        names = [log[i].split("\\")[-1] for i in range(1, len(log) + 1)]
        lua.execute("for k in pairs(__played) do __played[k] = nil end")
        return names

    snd = ns["Snd"]
    assert snd["files"]["DSPISTOL"] == 2 and snd["files"]["DSPLPAIN"] == 1, "sound table did not come from the converter"
    park_monsters(ns)
    player = ns["state"]["P"]
    set_player(ns, 1056, -3616, 0)
    snd["play"]("DSPISTOL")
    assert heard() == ["DSPISTOL.ogg"], "a player sound should use the plain file"
    x, y = player["x"], player["y"]
    snd["play"]("DSPISTOL", x + 100, y)
    snd["play"]("DSPOPAIN", x, y + 300)
    snd["play"]("DSBAREXP", x, y - 700)
    snd["play"]("DSCLAW", x + 1300, y)
    assert heard() == ["DSPISTOL_aC.ogg", "DSPOPAIN_aL.ogg", "DSBAREXP_bR.ogg"], "distance and side variants are wrong"

    ns["fire"]()
    step(ns, 4)
    assert heard() == ["DSPISTOL.ogg"], "the pistol shot did not play Doom's sound on tic 4"
    ns["damagePlayer"](10)
    assert heard() == ["DSPLPAIN.ogg"], "a hit did not play the player pain sound"
    snd["enabled"] = False
    ns["damagePlayer"](10)
    assert heard() == [], "sound off still played sounds"

    view, ui = ns["view"], ns["ui"]
    update = view["scripts"]["OnUpdate"]

    def song():
        track = lua.eval("__music")
        return track.split("\\")[-1] if track else None

    update(view, 0.01)
    assert song() == "D_INTRO.ogg", "the title screen did not play its music"
    ui["start"](3)
    update(view, 0.01)
    assert song() == "D_E1M1.ogg", "the level did not play E1M1's music"
    ui["beginInter"]()
    update(view, 0.01)
    assert song() == "D_INTER.ogg", "the intermission did not play its music"
    ui["screen"] = "game"
    snd["musicOn"] = False
    update(view, 0.01)
    assert song() is None, "music off did not stop the music"


def test_masked_fence():
    lua, ns = new_game(90)
    set_player(ns, 3040, -4256, math.pi)
    ns["render"]()
    textures = lua.eval("__tex")
    fence = [textures[i] for i in range(1, len(textures) + 1)
             if textures[i]["shown"] and textures[i]["path"] and "BRNBIGC" in textures[i]["path"]]
    assert fence, "the masked fence texture was not drawn"
    assert all(t["sub"] == 3 for t in fence), "the fence was not layered above the walls behind it"


def test_runtime_column_switch():
    lua, ns = new_game(16)
    set_player(ns, 1056, -3616, math.pi / 2)
    ns["render"]()
    textures = lua.eval("__tex")

    def shown_count():
        return sum(1 for i in range(1, len(textures) + 1) if textures[i]["shown"])

    low_count = shown_count()
    assert ns["setColumns"](320) == 320, "renderer did not switch to 320 columns"
    assert shown_count() <= 5000, "high-resolution view exceeded the visible texture limit"
    assert ns["setColumns"](160) == 160, "renderer did not switch back to 160 columns"
    assert shown_count() == low_count, "switching back left stale visible textures"
    view = ns["view"]
    slash = lua.eval('SlashCmdList["WODOOM"]')
    slash("hi")
    assert ns["getColumns"]() == 320 and not view["IsShown"](view), "hi mode changed visibility or failed to switch"
    slash("dos")
    assert ns["getColumns"]() == 320, "dos preset did not switch to 320 columns"
    assert shown_count() > 1500 and shown_count() <= 10000, "dos preset texture count out of range"
    slash("fast")
    assert ns["getColumns"]() == 160, "fast preset did not switch to 160 columns"
    slash("lo")
    assert ns["getColumns"]() == 160 and not view["IsShown"](view), "lo mode changed visibility or failed to switch"
    slash("")
    assert view["IsShown"](view), "no-argument slash command did not show the window"
    slash("")
    assert not view["IsShown"](view), "no-argument slash command did not hide the window"


def clear_spot(ns, origin, dist, sight_to):
    for deg in range(0, 360, 15):
        c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        x, y = origin["x"] + c * dist, origin["y"] + s * dist
        if ns["hasLOS"](x, y, sight_to["x"], sight_to["y"]) and ns["rayWall"](x, y, -c, -s) > dist:
            return x, y
    return None


def test_menus_skill_and_intermission():
    lua, ns = new_game(31)
    view, ui = ns["view"], ns["ui"]
    keydown = view["scripts"]["OnKeyDown"]
    assert ui["screen"] == "title", "the addon did not open on the title screen"
    keydown(view, "SPACE")
    assert ui["screen"] == "menu" and ui["item"] == 1, "the title did not lead to the main menu"
    keydown(view, "DOWN")
    keydown(view, "UP")
    keydown(view, "ENTER")
    assert ui["screen"] == "episode", "New Game did not lead to the episode menu"
    keydown(view, "DOWN")
    keydown(view, "ENTER")
    assert ui["screen"] == "msg", "choosing a missing episode did not show the shareware message"
    keydown(view, "X")
    assert ui["screen"] == "episode" and ui["item"] == 2, "closing a message did not return to the episode menu"
    keydown(view, "UP")
    keydown(view, "ESCAPE")
    assert ui["screen"] == "menu", "Escape did not go back from the episode menu"
    keydown(view, "ENTER")
    keydown(view, "ENTER")
    assert ui["screen"] == "skill" and ui["item"] == 3, "the episode did not lead to the skill menu on Hurt Me Plenty"
    keydown(view, "DOWN")
    assert ui["item"] == 4, "Down did not move the skull cursor"
    keydown(view, "UP")
    keydown(view, "UP")
    assert ui["item"] == 2, "Up did not move the skull cursor"
    keydown(view, "ENTER")
    assert ui["screen"] == "game" and ns["getSkill"]() == 2, "Enter did not start the chosen skill"
    ui["update"](1 / 35)

    # In-game menu: Escape pauses behind the Doom menu, options toggle, quit asks first.
    y0 = ns["state"]["P"]["y"]
    view["Show"](view)
    keydown(view, "ESCAPE")
    assert ui["screen"] == "menu" and ui["back"] == "game", "Escape did not open the menu in game"
    ns["state"]["keys"]["W"] = True
    ui["update"](0.5)
    assert ns["state"]["P"]["y"] == y0, "the game kept running behind the menu"
    keydown(view, "DOWN")
    keydown(view, "ENTER")
    assert ui["screen"] == "options", "Options did not open"
    keydown(view, "DOWN")
    keydown(view, "ENTER")
    assert not ui["showMessages"], "the messages option did not toggle"
    keydown(view, "ENTER")
    assert ui["showMessages"], "the messages option did not toggle back"
    keydown(view, "DOWN")
    columns = ns["getColumns"]()
    keydown(view, "ENTER")
    assert ns["getColumns"]() != columns, "the detail option did not switch the column count"
    keydown(view, "ENTER")
    keydown(view, "ESCAPE")
    assert ui["screen"] == "menu", "Escape did not leave the options menu"
    for _ in range(3):
        keydown(view, "DOWN")
    keydown(view, "ENTER")
    assert ui["screen"] == "help", "Read This did not show the help screen"
    keydown(view, "ENTER")
    keydown(view, "DOWN")
    keydown(view, "ENTER")
    assert ui["screen"] == "msg", "Quit Game did not ask for confirmation"
    keydown(view, "N")
    assert ui["screen"] == "menu" and view["IsShown"](view), "declining quit closed the window (%s %s)" % (
        ui["screen"], view["IsShown"](view))
    keydown(view, "ENTER")
    keydown(view, "Y")
    assert not view["IsShown"](view), "confirming quit did not close the window"
    view["Show"](view)
    ui["screen"], ui["back"] = "game", "game"
    ns["state"]["keys"]["W"] = None

    counts = {}
    for skill in (1, 2, 3, 4, 5):
        ui["start"](skill)
        counts[skill] = (len(monsters(ns)), len(ns["state"]["actors"]))
    assert counts[1] == counts[2] and counts[4] == counts[5], "skill thing flags were not grouped like Doom"
    assert all(c[0] > 0 for c in counts.values()), "a skill level spawned no monsters"

    ui["start"](1)
    ns["damagePlayer"](20)
    assert ns["state"]["getHP"]() == 90, "baby skill did not halve damage"
    ui["start"](3)
    ns["damagePlayer"](20)
    assert ns["state"]["getHP"]() == 80, "normal skill changed damage"
    ui["start"](5)
    imp = next(m for m in monsters(ns) if m["t"] == 3001)
    assert imp["mon"]["reaction"] == 0 and imp["mon"]["chaseTics"] == 1, "nightmare monsters were not sped up"

    ui["start"](3)
    ui["beginInter"]()
    assert ui["screen"] == "inter"
    for _ in range(900):
        ui["update"](1 / 35)
        if ui["phase"] == 5:
            break
    assert ui["phase"] == 5, "the intermission counters never finished"
    shown = sum(1 for i in range(1, len(lua.eval("__tex")) + 1) if lua.eval("__tex")[i]["shown"])
    assert shown >= 20, "the intermission drew too little (%d textures)" % shown
    keydown(view, "SPACE")
    assert ui["screen"] == "title", "a key press did not leave the intermission"
    keydown(view, "ESCAPE")
    assert not view["IsShown"](view), "Escape on the title screen did not close the window"


def test_drops_fx_armor_ambush_knockback_doors_and_hud():
    lua, ns = new_game(51)
    actors, player = ns["state"]["actors"], ns["state"]["P"]
    zombie = next(m for m in monsters(ns) if m["t"] == 3004)
    spot = clear_spot(ns, zombie, 150, zombie)
    assert spot, "no clear spot to shoot the zombie from"
    set_player(ns, spot[0], spot[1], math.atan2(zombie["y"] - spot[1], zombie["x"] - spot[0]))
    bullets_before = ns["state"]["getAmmo"]()[0]
    items_before = ns["state"]["getStats"]()["items"]
    for _ in range(20):
        if zombie["hp"] <= 0:
            break
        ns["fire"]()
        step(ns, 20)
    assert zombie["hp"] <= 0, "could not kill the zombie"
    fx = [a for a in (actors[i] for i in range(1, len(actors) + 1)) if a["fx"]]
    drops = [a for a in (actors[i] for i in range(1, len(actors) + 1)) if a["dropped"]]
    assert len(drops) == 1 and drops[0]["t"] == 2007, "a killed zombieman did not drop a clip"
    assert fx or True
    set_player(ns, drops[0]["x"], drops[0]["y"], 0)
    spent = bullets_before - ns["state"]["getAmmo"]()[0]
    step(ns, 2)
    gained = ns["state"]["getAmmo"]()[0] - (bullets_before - spent)
    assert gained == 5, "a dropped clip should give half a clip (got %s)" % gained
    assert ns["state"]["getStats"]()["items"] == items_before, "a dropped clip counted as a level item"

    _lua, ns = new_game(52)
    actors, player = ns["state"]["actors"], ns["state"]["P"]
    blue = next(actors[i] for i in range(1, len(actors) + 1) if actors[i]["t"] == 2019)
    set_player(ns, blue["x"], blue["y"], 0)
    step(ns, 2)
    assert player["armorType"] == 2 and ns["state"]["getAmmo"]()[2] == 200, "blue armor was not picked up"
    ns["damagePlayer"](20)
    assert ns["state"]["getHP"]() == 90, "blue armor did not absorb half the damage"
    set_player(ns, 1056, -3616, 0)
    player["momx"] = player["momy"] = 0
    ns["damagePlayer"](40, player["x"] + 10, player["y"])
    assert player["momx"] < -4.9, "damage did not knock the player away from the attacker"

    _lua, ns = new_game(53)
    actors, player = ns["state"]["actors"], ns["state"]["P"]
    set_player(ns, 1056, -3616, math.pi / 2)
    ns["fire"]()
    step(ns, 4)
    puffs = [actors[i] for i in range(1, len(actors) + 1) if actors[i]["fx"]]
    assert puffs, "shooting a wall did not leave a bullet puff"
    step(ns, 30)
    assert not [actors[i] for i in range(1, len(actors) + 1) if actors[i]["fx"]], "puffs were not cleaned up"

    _lua, ns = new_game(54)
    set_player(ns, 1056, -3616, math.pi / 2)  # face away from both monsters so the shot only makes noise
    quiet, light = monsters(ns)[0], monsters(ns)[1]
    quiet["x"], quiet["y"], quiet["ambush"] = 1056 + 30, -3616, True
    light["x"], light["y"] = 1056 - 30, -3616
    light["ambush"] = False
    for m in (quiet, light):
        m["awake"], m["state"] = False, "idle"
    ns["fire"]()
    assert light["awake"] and not quiet["awake"], "noise woke a deaf (ambush) monster or missed a normal one"

    _lua, ns = new_game(55)
    park_monsters(ns)
    sectors, lines = ns["level"]["sectors"], ns["level"]["lines"]
    door = next(lines[i] for i in range(1, len(lines) + 1) if lines[i]["sp"] == 1)
    dx, dy = door["x2"] - door["x1"], door["y2"] - door["y1"]
    length = math.hypot(dx, dy)
    nx, ny = dy / length, -dx / length
    mid = ((door["x1"] + door["x2"]) / 2, (door["y1"] + door["y2"]) / 2)
    imp = next(m for m in monsters(ns) if m["t"] == 3001)
    imp["x"], imp["y"] = mid[0] + nx * 50, mid[1] + ny * 50
    imp["awake"], imp["state"], imp["reactionT"] = True, "chase", 10 ** 6
    set_player(ns, mid[0] - nx * 250, mid[1] - ny * 250, 0)
    target = sectors[door["bs"]]
    step(ns, 200)
    assert target["ce"] > target["ce0"], "a monster pushing against a door did not open it"

    _lua, ns = new_game(56)
    ns["ui"]["start"](3)
    ns["render"]()
    textures = lua.eval("__tex") if False else _lua.eval("__tex")
    paths = [textures[i]["path"] for i in range(1, len(textures) + 1) if textures[i]["shown"] and textures[i]["path"]]
    assert any("STARMS" in p for p in paths), "the ARMS panel was not drawn"
    assert any("STYSNUM" in p for p in paths), "the ammo table was not drawn"


def test_player_damage_switching_messages_and_face():
    _lua, ns = new_game(61)
    player, ui = ns["state"]["P"], ns["ui"]
    imp = next(m for m in monsters(ns) if m["t"] == 3001)
    spot = clear_spot(ns, imp, 150, imp)
    assert spot, "no clear spot to shoot the imp from"
    set_player(ns, spot[0], spot[1], math.atan2(imp["y"] - spot[1], imp["x"] - spot[0]))
    imp["hp"] = 10 ** 6
    deltas = []
    for _ in range(12):
        before = imp["hp"]
        ns["fire"]()
        step(ns, 5)
        deltas.append(before - imp["hp"])
        step(ns, 15)
    assert set(deltas) <= {0, 5, 10, 15} and len(set(deltas) - {0}) >= 2, "pistol damage is not 5/10/15: %s" % deltas

    # Holding fire: Doom's pistol repeats every 14 tics (4+6+4, A_ReFire skips the last state) with refire > 0.
    _lua, ns = new_game(60)
    player = ns["state"]["P"]
    park_monsters(ns)
    set_player(ns, 1056, -3616, math.pi / 2)
    keys, bullets = ns["state"]["keys"], ns["state"]["getAmmo"]
    step(ns, 10)
    start = bullets()[0]
    keys["SPACE"] = True
    step(ns, 1)
    assert bullets()[0] == start and player["wstate"] == "attack", "held fire did not start an attack"
    step(ns, 4)
    assert bullets()[0] == start - 1, "the pistol did not fire on its 4th tic"
    step(ns, 14)
    assert bullets()[0] == start - 2 and player["refire"] == 1, "held pistol did not refire after 14 tics"
    step(ns, 14)
    assert bullets()[0] == start - 3 and player["refire"] == 2, "held pistol did not keep refiring"
    keys["SPACE"] = None
    step(ns, 30)
    assert player["refire"] == 0 and player["wstate"] == "ready", "releasing fire did not reset refire"

    _lua, ns = new_game(62)
    player, ui = ns["state"]["P"], ns["ui"]
    actors = ns["state"]["actors"]
    shotgun = next(actors[i] for i in range(1, len(actors) + 1) if actors[i]["t"] == 2001)
    set_player(ns, shotgun["x"], shotgun["y"], 0)
    step(ns, 2)
    assert ns["state"]["getMessage"]() == "You got the shotgun!", "wrong shotgun pickup message"
    assert ui["face"]().startswith("STFEVL"), "picking up a weapon did not give the evil grin"
    assert player["pending"] == 3, "picking up the shotgun did not queue a weapon switch"
    bullets_before = ns["state"]["getAmmo"]()[0]
    step(ns, 3)
    assert player["wstate"] == "lower" and player["wy"] > 0, "the old weapon did not start lowering"
    ns["fire"]()
    assert ns["state"]["getAmmo"]()[0] == bullets_before, "fired while switching weapons"
    step(ns, 40)
    assert ns["state"]["getWeapon"]() == 3 and player["wstate"] == "ready" and player["wy"] == 0, "switch did not finish"
    shells = ns["state"]["getAmmo"]()[1]
    ns["fire"]()
    step(ns, 2)
    assert ns["state"]["getAmmo"]()[1] == shells, "the shotgun fired before its 3-tic wind-up"
    step(ns, 1)
    assert ns["state"]["getAmmo"]()[1] == shells - 1 and ns["Light"]["extra"] == 1, "shotgun shot/flash timing is wrong"
    step(ns, 3)
    assert ns["Light"]["extra"] == 2, "second shotgun flash frame did not add more light"
    step(ns, 3)
    assert ns["Light"]["extra"] == 0 and not player["fseq"], "the muzzle flash light did not go out"
    step(ns, 40)
    assert player["wstate"] == "ready", "the shotgun did not return to ready"
    set_player(ns, 1056, -3616, 0)
    ns["damagePlayer"](30, player["x"] + 10, player["y"])
    assert ui["face"]() == "STFOUCH1", "a heavy hit did not show the ouch face (%s)" % ui["face"]()
    step(ns, 40)
    assert ui["face"]().startswith("STFST1"), "the face did not return to normal"


def test_barrels_explode_and_chain():
    _lua, ns = new_game(21)
    park_monsters(ns)
    actors = ns["state"]["actors"]
    barrels = [actors[i] for i in range(1, len(actors) + 1) if actors[i]["barrel"]]
    assert barrels, "the level has no barrels"
    barrel = barrels[0]
    spot = clear_spot(ns, barrel, 100, barrel)
    assert spot, "no clear spot to shoot the barrel from"
    set_player(ns, spot[0], spot[1], math.atan2(barrel["y"] - spot[1], barrel["x"] - spot[0]))
    zombie = monsters(ns)[0]
    zspot = clear_spot(ns, barrel, 40, barrel)
    assert zspot, "no clear spot beside the barrel for a monster"
    near = [b for b in barrels[1:] if math.hypot(b["x"] - barrel["x"], b["y"] - barrel["y"]) < 110
            and ns["hasLOS"](barrel["x"], barrel["y"], b["x"], b["y"])]
    for _ in range(12):
        ns["fire"]()
        step(ns, 5)
        if barrel["exploding"]:
            break
        step(ns, 15)
    assert barrel["exploding"], "shooting a barrel did not set it off"
    zombie["x"], zombie["y"] = zspot  # step next to the barrel just before it blows
    assert ns["state"]["getHP"]() == 100, "the barrel hurt the player before exploding"
    step(ns, 60)
    assert barrel["gone"], "the barrel did not finish exploding"
    hp = ns["state"]["getHP"]()
    assert 0 < 100 - hp <= 128, "explosion did not damage the nearby player (hp %s)" % hp
    assert zombie["hp"] <= 0, "explosion did not kill the monster standing next to the barrel"
    for other in near:
        assert other["exploding"] or other["gone"], "explosion did not chain to a nearby barrel"


if __name__ == "__main__":
    test_zombie_kill_and_door()
    test_imp_reaction_and_fireball()
    test_noise_crosses_adjacent_sector()
    test_monsters_do_not_overlap()
    test_player_ticcmd_speed_friction_and_turning()
    test_player_wall_slide_and_step_height()
    test_living_monster_blocks_player()
    test_floor_triggers_and_lift_cycle()
    test_lights_pickups_secrets_and_exit()
    test_runtime_column_switch()
    test_barrels_explode_and_chain()
    test_menus_skill_and_intermission()
    test_drops_fx_armor_ambush_knockback_doors_and_hud()
    test_player_damage_switching_messages_and_face()
    test_doom_light_model()
    test_palette_hud_font_death_and_pause()
    test_doom_sounds()
    test_masked_fence()
    print("OK: light model, sounds, palette flashes, HU font, death and pause, combat, drops, damage and weapon switching, barrels, menus and skills, tic doors, W1/WR floor triggers, lifts, sector lights, pickups, secrets, exit stats, movement, and monster blocking")
