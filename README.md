# WoDoom

DOOM E1M1 (Hangar) as a World of Warcraft addon. The level, textures, sprites and lighting come from the real shareware `doom1.wad`; the renderer and game logic are written from scratch in Lua.

## How it works

WoW addons can't run native code or draw pixels, so WoDoom lets the game's texture system do the drawing:

- **Walls and sprites:** for each screen column the addon walks Doom's BSP tree, then draws the visible wall pieces and monster sprites as thin textured strips (`SetTexCoord` picks the texture column).
- **Floors and ceilings:** each row of floor or ceiling becomes one quad whose eight texture coordinates follow the view rays, which gives perspective-correct textured flats.
- **Pooling:** textures are pooled per image, so there are roughly 350 to 700 visible textures per frame at the default 160 columns, and about 1,000 to 3,500 in `dos`. More than about 16,000 visible textures makes the whole UI disappear, so the addon stays far below that.
- **Game logic:** it runs on Doom's 35 Hz tic clock, separate from rendering.

## Install

Copy or link the `AddOns\wodoom` folder (the one containing `wodoom.toc`) into `World of Warcraft\_retail_\Interface\AddOns\`, so the path ends in `AddOns\wodoom`, then `/reload` and type `/wodoom`. Don't copy `tools\`: it is not part of the addon.

The `## Interface` number in `wodoom.toc` is a guess for the current client. If the addon shows as out of date, update it or enable "Load out of date AddOns".

## Commands

| Command | Effect |
|---|---|
| `/wodoom` | Show or hide the game window. |
| `/wodoom dos` | Closest to DOS Doom: 320 columns, and floor/ceiling light changes with distance across each row (about 3-4k textures per frame). |
| `/wodoom hi` | 320 columns, floors lit per row only. |
| `/wodoom fast` or `lo` | 160 columns (default, fastest). |
| `/wodoom sound on` / `off` | Doom sound effects. |
| `/wodoom music on` / `off` | Doom music. |

Lighting follows Doom: each sector's light level and the distance pick one of the 32 `COLORMAP` brightness levels (converted from the WAD), horizontal and vertical walls get the +/-1 contrast step, and gunfire adds extra light. If a preset ever needs more visible textures than it allows (5,000, or 10,000 for `dos`), it falls back to 160 columns and prints a chat message.

## Controls

The addon opens on Doom's title screen. Any key opens the main menu (New Game, Options, Read This!, Quit Game; load and save show a notice). New Game leads to the episode menu (only Knee-Deep in the Dead exists in the shareware WAD) and then the skill menu. Use Up/Down (or W/S) to move the skull cursor, and Enter, Space or a click to choose. Esc goes back. In game, Esc opens the menu and pauses; Options has Messages and Graphic Detail (low is 160 columns, high is 320). After the exit switch you get the intermission screen: kills, items, secrets, time and par count up, and a key press returns to the title.

| Key | Action |
|---|---|
| W / S or Up / Down | Move forward / back |
| A / D | Strafe |
| Q / E or Left / Right | Turn |
| Shift | Run |
| Space or left click | Fire (hold to keep firing) |
| F | Use (doors, switches); respawns you when dead |
| 1 to 4 | Fist, pistol, shotgun, chaingun (once owned) |
| P | Pause |
| R | Restart after dying or finishing the level |
| Esc | Menu |

You start with the fist and pistol. The shotgun and chaingun are picked up in the level.

## What's implemented

- **Level:** all of E1M1's geometry, textures, animated nukage, scrolling walls, see-through masked textures (the iron gates in the barrel room) and distance and sector lighting, with the real sky.
- **Mechanics:** doors, walk-over triggers (floor lower and lifts), switches, the exit, sector light effects, nukage damage, secrets, pickups and an end-of-level kills, items and secrets summary.
- **Monsters:** zombieman, shotgun guy and imp, each with a state machine (reaction time, chase, attack, pain, death), 8 view rotations and animation frames. Imps throw fireballs, and gunfire wakes monsters in connected rooms.
- **Player:** Doom-style momentum and friction, wall sliding, 24-unit step-up, view bob and Doom's weapon bob (full-range sway while running).
- **Weapons:** each weapon runs Doom's state tables tic by tic: the pistol fires on tic 4 and repeats every 14 tics while held, the shotgun every 37, the fist every 22, the chaingun every 4 per shot. Muzzle flashes are fullbright and add extra light for a few tics, as in Doom.
- **Screen effects:** red palette flashes scaled by damage taken, yellow pickup flashes (the blend colors and strengths are derived from the WAD's `PLAYPAL`), Doom's HU-font messages (top left, 4 seconds), and Doom's death view: the camera sinks, the weapon drops and you turn toward your killer until you press F.
- **HUD:** the real status bar with health, ammo, armor, the face, the ARMS weapon grid and the ammo table.
- **Combat details:** zombiemen and shotgun guys drop a clip or shotgun when killed, monsters open the doors they bump into, deaf (ambush) monsters ignore gunfire, shots leave bullet puffs and blood, damage knocks you back, blue armor absorbs half the damage (green a third), and imp fireballs can set off barrels.
- **Doom's rules:** bullets do 5, 10 or 15 damage and the fist 2 to 20. The first pistol or chaingun shot is accurate and refired shots, like shotgun pellets, stray up to about 5.6 degrees. Monsters aim with Doom's wider error and decide to shoot with its missile-range rule. Switching weapons lowers and raises the gun, you auto-switch when out of ammo, pickup messages use Doom's wording, and the status face reacts to hits, weapon pickups and long firing.
- **Screens:** Doom's title picture, the main menu with skull cursor, episode, skill and options menus, message boxes (quit, nightmare, shareware), the Read This! screen and the "Hangar / Finished" intermission with counting stats and par time.
- **Sound and music:** Doom's own sound effects (converted to OGG) for weapons, monsters (sight, pain, death, attacks, idle growls), doors, lifts, switches, pickups, barrels, the menus and the intermission. World sounds use Doom's distance rule (full volume under 200 units, silent past 1200) and a left/centre/right pick, baked as volume x side variants because WoW can't pan or set volume per sound. The title, E1M1 and intermission tracks are Doom's MUS files rendered with a General MIDI soundfont, so they sound like Doom's MIDI, not the original synth. Both are played through WoW's SFX and Music channels, so the in-game volume sliders apply.
- **Skill levels:** the map's per-skill monster and item placement for all five levels, double ammo and half damage on "I'm too young to die", and faster, more aggressive monsters with faster fireballs on Nightmare.

## Limitations

- E1M1 only. Other maps need the converter run on them plus any new specials.
- Not reproduced: Doom's exact random-number table (the RNG is Lua's), the full monster pathing of `P_NewChaseDir`, automap, saved games, and the screen-size, mouse and volume sliders (drawn but inactive). The view is 320 columns at best with the 90 degree projection scaled to 640x480; color is shaded per texture strip or floor chunk rather than per pixel from the 8-bit palette.
- Sprite occlusion only tests solid walls, so a sprite seen through a partly open window may draw slightly wrong.

## Regenerating the generated files

`data_level.lua`, `data_assets.lua` and the `tex/`, `flat/`, `spr/`, `snd/` and `music/` folders are generated from the WAD by `tools/wad2wow.py` (Python 3 with Pillow):

```powershell
python wodoom\tools\wad2wow.py path\to\doom1.wad --out wodoom\AddOns\wodoom
```

Pass `--out` explicitly to be safe; it defaults to `AddOns\wodoom` next to `tools\`. The script writes whatever it generates into that folder.

Sounds need `ffmpeg` (on PATH, in the WinGet install location, or `--ffmpeg <path>`). Music also needs `fluidsynth` and a General MIDI soundfont: unpack the FluidSynth Windows release into `tools\work\music\fluidsynth` and put `GeneralUser-GS.sf2` in `tools\work\music`, or pass `--fluidsynth` and `--soundfont`. Without them the converter skips that part and the addon stays silent. The generated `snd/` and `music/` folders are about 7 MB.

## Offline testing

Needs `pip install lupa pillow`. Run these from the repository root:

```powershell
python wodoom\tools\test_logic.py
python wodoom\tools\harness.py 1056 -3616 90 out.png W:60,E:20
```

- `test_logic.py` runs the gameplay checks (combat, weapon timing, lighting, menus, sounds, doors, triggers, lifts, movement) against a stubbed WoW API.
- `harness.py <x> <y> <angle> <png> [sequence]` renders one frame to a PNG. The sequence is a list like `W:60` (hold a key for N tics), `USE`, `FIRE` or a plain tic count. Set `WODOOM_COLS=320` to render in hi-res, or `WODOOM_PRESET=dos` (or `hi`, `fast`) to use a preset.

## Files

| Path | Purpose |
|---|---|
| `AddOns/wodoom/` | The addon: the only folder to copy into WoW (about 15 MB, 7 MB zipped). |
| `AddOns/wodoom/wodoom.toc`, `wodoom.lua` | The addon code. |
| `AddOns/wodoom/data_level.lua`, `data_assets.lua` | Generated level and asset tables. |
| `AddOns/wodoom/tex/`, `flat/`, `spr/` | Generated wall textures, floor and ceiling flats, and sprites (`.tga`). |
| `AddOns/wodoom/snd/`, `music/` | Generated sound effects (with volume and side variants) and music (`.ogg`). |
| `tools/` | Converter, offline harness and tests. Its `work/` folder (the WAD, soundfont and FluidSynth, about 48 MB) is git-ignored. |

## Credits and licensing

Doom is a trademark of id Software. The art, sounds, music and level data come from the shareware `doom1.wad`. Check its terms before redistributing the converted assets. The music is rendered with the GeneralUser GS soundfont by S. Christian Collins (see its license) and FluidSynth, which are only needed to regenerate it. The Lua code, converter and tools are original work.
