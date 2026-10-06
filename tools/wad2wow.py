#!/usr/bin/env python3
"""Convert a DOOM WAD (default E1M1) into WoW addon assets.

Writes TGA wall textures and sprites plus Lua level/asset tables into the addon folder.
Usage: python wad2wow.py <doom1.wad> [--map E1M1] [--out <addon dir>]
"""
import argparse
import glob
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

from PIL import Image

# Thing type -> (sprite prefix, frame letter). Only types present in the map are converted.
THING_SPRITES = {
    3004: ("POSS", "A"), 9: ("SPOS", "A"), 3001: ("TROO", "A"), 3002: ("SARG", "A"), 58: ("SARG", "A"),
    3003: ("BOSS", "A"), 3005: ("HEAD", "A"), 3006: ("SKUL", "A"),
    2001: ("SHOT", "A"), 2002: ("MGUN", "A"), 2003: ("LAUN", "A"), 2004: ("PLAS", "A"),
    2005: ("CSAW", "A"), 2006: ("BFUG", "A"),
    2007: ("CLIP", "A"), 2008: ("SHEL", "A"), 2010: ("ROCK", "A"), 2011: ("STIM", "A"),
    2012: ("MEDI", "A"), 2013: ("SOUL", "A"), 2014: ("BON1", "A"), 2015: ("BON2", "A"),
    2018: ("ARM1", "A"), 2019: ("ARM2", "A"), 2022: ("PINV", "A"), 2023: ("PSTR", "A"),
    2024: ("PINS", "A"), 2025: ("SUIT", "A"), 2026: ("PMAP", "A"), 2045: ("PVIS", "A"),
    2046: ("BROK", "A"), 2047: ("CELL", "A"), 2048: ("AMMO", "A"), 2049: ("SBOX", "A"),
    17: ("CELP", "A"), 8: ("BPAK", "A"),
    5: ("BKEY", "A"), 6: ("YKEY", "A"), 13: ("RKEY", "A"),
    38: ("RSKU", "A"), 39: ("YSKU", "A"), 40: ("BSKU", "A"),
    2035: ("BAR1", "A"), 70: ("FCAN", "A"), 48: ("ELEC", "A"),
    30: ("COL1", "A"), 31: ("COL2", "A"), 32: ("COL3", "A"), 33: ("COL4", "A"),
    36: ("COL5", "A"), 37: ("COL6", "A"), 2028: ("COLU", "A"),
    25: ("POL1", "A"), 26: ("POL6", "A"), 27: ("POL4", "A"), 28: ("POL2", "A"), 29: ("POL3", "A"),
    35: ("CBRA", "A"), 34: ("CAND", "A"), 44: ("TBLU", "A"), 45: ("TGRN", "A"), 46: ("TRED", "A"),
    55: ("SMBT", "A"), 56: ("SMGT", "A"), 57: ("SMRT", "A"), 47: ("SMIT", "A"),
    54: ("TRE2", "A"), 43: ("TRE1", "A"), 85: ("TLMP", "A"), 86: ("TLP2", "A"),
    10: ("PLAY", "W"), 12: ("PLAY", "W"), 15: ("PLAY", "N"), 18: ("POSS", "L"), 19: ("SPOS", "L"),
    20: ("TROO", "M"), 21: ("SARG", "N"), 24: ("POL5", "A"),
    49: ("GOR1", "A"), 50: ("GOR2", "A"), 51: ("GOR3", "A"), 52: ("GOR4", "A"), 53: ("GOR5", "A"),
}

ANIMATED_FLATS = ["NUKAGE1", "NUKAGE2", "NUKAGE3"]
FRAME_PREFIXES = ("POSS", "SPOS", "TROO", "BAL1", "PUFF", "BLUD")

# Extra patches/sprites always converted: weapon views, status bar and face art.
EXTRA_LUMPS = (
    ["STBAR", "STTPRCNT", "STFDEAD0", "STFKILL0", "STFGOD0"]
    + ["STTNUM%d" % i for i in range(10)]
    + ["STFST%d%d" % (p, f) for p in range(5) for f in range(3)]
    + ["STFOUCH%d" % p for p in range(5)] + ["STFEVL%d" % p for p in range(5)]
    + ["STFKILL%d" % p for p in range(5)]
    + ["STFTR%d0" % p for p in range(5)] + ["STFTL%d0" % p for p in range(5)]
    + ["POSSL0", "SPOSL0", "TROOM0"]
    + ["BAR1B0", "BEXPA0", "BEXPB0", "BEXPC0", "BEXPD0", "BEXPE0"]
    + ["TITLEPIC", "M_NEWG", "M_SKILL", "M_JKILL", "M_ROUGH", "M_HURT", "M_ULTRA", "M_NMARE",
       "M_SKULL1", "M_SKULL2", "M_PAUSE", "M_DOOM", "M_NGAME", "M_OPTION", "M_LOADG", "M_SAVEG", "M_RDTHIS",
       "M_QUITG", "M_EPISOD", "M_EPI1", "M_EPI2", "M_EPI3", "M_EPI4", "M_OPTTTL", "M_ENDGAM", "M_MESSG",
       "M_DETAIL", "M_SCRNSZ", "M_MSENS", "M_SVOL", "M_MSGON", "M_MSGOFF", "M_GDHIGH", "M_GDLOW", "M_THERML", "M_THERMM",
       "M_THERMR", "M_THERMO", "HELP1"]
    + ["STCFN%03d" % i for i in range(33, 96)]
    + ["WIMAP0", "WIF", "WILV00", "WIOSTK", "WIOSTI", "WISCRT2", "WITIME", "WIPAR", "WIPCNT", "WICOLON"]
    + ["WINUM%d" % i for i in range(10)]
    + ["STARMS"] + ["STGNUM%d" % i for i in range(2, 8)] + ["STYSNUM%d" % i for i in range(10)]
    + ["PISGA0", "PISGB0", "PISGC0", "PISGD0", "PISGE0", "PISFA0",
       "SHTGA0", "SHTGB0", "SHTGC0", "SHTGD0", "SHTFA0", "SHTFB0",
       "CHGGA0", "CHGGB0", "CHGFA0", "CHGFB0",
       "MISGA0", "MISGB0", "MISFA0", "MISFB0", "MISFC0", "MISFD0",
       "PLSGA0", "PLSGB0", "PLSFA0", "PLSFB0",
       "BFGGA0", "BFGGB0", "BFGGC0", "BFGFA0", "BFGFB0",
       "SAWGA0", "SAWGB0", "SAWGC0", "SAWGD0", "PUNGA0", "PUNGB0", "PUNGC0", "PUNGD0"]
)


DOOM_SOUNDS = (
    "DSPISTOL DSSHOTGN DSPUNCH DSPLPAIN DSPLDETH DSITEMUP DSWPNUP DSDOROPN DSDORCLS DSSWTCHN DSSWTCHX "
    "DSPSTART DSPSTOP DSSTNMOV DSBAREXP DSPOSIT1 DSPOSIT2 DSPOSIT3 DSPODTH1 DSPODTH2 DSPODTH3 DSPOSACT "
    "DSPOPAIN DSSGTSIT DSSGTDTH DSBGSIT1 DSBGSIT2 DSBGDTH1 DSBGDTH2 DSBGACT DSCLAW DSFIRSHT DSFIRXPL"
).split()
# Sounds that come from a place in the world get volume (a/b/c) x side (L/C/R) variants.
POSITIONAL_SOUNDS = set(DOOM_SOUNDS) - {"DSPLPAIN", "DSPLDETH", "DSITEMUP", "DSWPNUP", "DSPUNCH", "DSSWTCHN",
                                        "DSSWTCHX"}
SOUND_VOLUMES = {"a": 1.0, "b": 0.55, "c": 0.25}
SOUND_SIDES = {"L": (1.0, 0.3), "C": (0.85, 0.85), "R": (0.3, 1.0)}


def find_ffmpeg(explicit):
    if explicit:
        return explicit
    found = shutil.which("ffmpeg")
    if found:
        return found
    pattern = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\**\ffmpeg.exe")
    hits = glob.glob(pattern, recursive=True)
    return hits[0] if hits else None


# Doom DS* lumps are 8-bit PCM; returns {name: 1 (plain) or 2 (with positional variants)}.
def convert_sounds(wad, out, ffmpeg):
    (out / "snd").mkdir(parents=True, exist_ok=True)
    info = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name in DOOM_SOUNDS:
            if not wad.has(name):
                print("missing sound", name, file=sys.stderr)
                continue
            data = wad.lump(name)
            rate, count = struct.unpack("<HI", data[2:8])
            pcm = data[8 + 16:8 + count - 16]  # Doom pads each end with 16 samples
            src = Path(tmp) / (name + ".wav")
            with wave.open(str(src), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(1)
                w.setframerate(rate)
                w.writeframes(pcm)
            jobs = [(name + ".ogg", None)]
            if name in POSITIONAL_SOUNDS:
                jobs += [("%s_%s%s.ogg" % (name, v, s), (SOUND_VOLUMES[v], SOUND_SIDES[s]))
                         for v in SOUND_VOLUMES for s in SOUND_SIDES]
            for target, gain in jobs:
                cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", str(src), "-ar", "22050"]
                if gain:
                    vol, (left, right) = gain
                    cmd += ["-af", "pan=stereo|c0=%.3f*c0|c1=%.3f*c0" % (vol * left, vol * right)]
                cmd += ["-c:a", "libvorbis", "-q:a", "4", str(out / "snd" / target)]
                subprocess.run(cmd, check=True)
            info[name] = 2 if name in POSITIONAL_SOUNDS else 1
    return info


MUSIC_LUMPS = ("D_E1M1", "D_INTRO", "D_INTER")
MUS_CONTROLLERS = {1: 0, 2: 1, 3: 7, 4: 10, 5: 11, 6: 91, 7: 93, 8: 64, 9: 67}  # MUS controller to MIDI CC


def varlen(n):
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(out))


# Doom's MUS format runs at 140 ticks per second; the MIDI file uses division 140 at one second per quarter.
def mus_to_midi(mus):
    score_start = struct.unpack("<H", mus[6:8])[0]
    pos = score_start
    track = bytearray(b"\x00\xff\x51\x03\x0f\x42\x40")
    last_volume = [100] * 16
    delta = 0

    def midi_channel(c):
        return 9 if c == 15 else (c if c < 9 else c + 1)

    def emit(data):
        nonlocal delta
        track.extend(varlen(delta))
        track.extend(data)
        delta = 0

    while pos < len(mus):
        b = mus[pos]
        pos += 1
        last, event, ch = b & 0x80, (b >> 4) & 7, midi_channel(b & 15)
        if event == 0:
            emit(bytes([0x80 | ch, mus[pos] & 127, 0]))
            pos += 1
        elif event == 1:
            note = mus[pos]
            pos += 1
            if note & 0x80:
                last_volume[b & 15] = mus[pos] & 127
                pos += 1
            emit(bytes([0x90 | ch, note & 127, last_volume[b & 15]]))
        elif event == 2:
            v = mus[pos]
            pos += 1
            emit(bytes([0xE0 | ch, (v << 6) & 0x7F, v >> 1]))
        elif event == 3:
            controller = mus[pos]
            pos += 1
            if controller in (10, 11):
                emit(bytes([0xB0 | ch, 120 if controller == 10 else 123, 0]))
            elif controller == 14:
                emit(bytes([0xB0 | ch, 121, 0]))
        elif event == 4:
            controller, value = mus[pos], mus[pos + 1] & 127
            pos += 2
            if controller == 0:
                emit(bytes([0xC0 | ch, value]))
            elif controller in MUS_CONTROLLERS:
                emit(bytes([0xB0 | ch, MUS_CONTROLLERS[controller], value]))
        elif event == 6:
            break
        if last:
            wait = 0
            while True:
                byte = mus[pos]
                pos += 1
                wait = wait * 128 + (byte & 0x7F)
                if not byte & 0x80:
                    break
            delta += wait
    emit(b"\xff\x2f\x00")
    return b"MThd" + struct.pack(">IHHH", 6, 0, 1, 140) + b"MTrk" + struct.pack(">I", len(track)) + bytes(track)


def convert_music(wad, out, ffmpeg, fluidsynth, soundfont):
    (out / "music").mkdir(parents=True, exist_ok=True)
    info = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name in MUSIC_LUMPS:
            if not wad.has(name):
                print("missing music", name, file=sys.stderr)
                continue
            mid, wav = Path(tmp) / (name + ".mid"), Path(tmp) / (name + ".wav")
            mid.write_bytes(mus_to_midi(wad.lump(name)))
            subprocess.run([fluidsynth, "-ni", "-g", "0.7", "-T", "wav", "-F", str(wav), "-r", "44100",
                            str(soundfont), str(mid)], check=True, stdout=subprocess.DEVNULL)
            subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(wav), "-ac", "2", "-c:a", "libvorbis",
                            "-q:a", "3", str(out / "music" / (name + ".ogg"))], check=True)
            info[name] = True
    return info


def colormap_gains(wad, palette):
    """Average RGB gain of each of Doom's 32 light colormaps, from COLORMAP and PLAYPAL."""
    cmap = wad.lump("COLORMAP")
    base = [sum(c[i] for c in palette) or 1 for i in range(3)]
    gains = []
    for n in range(32):
        mapped = [0, 0, 0]
        for idx in range(256):
            c = palette[cmap[n * 256 + idx]]
            for i in range(3):
                mapped[i] += c[i]
        gains.append([round(mapped[i] / base[i], 4) for i in range(3)])
    return gains


def palette_effects(wad):
    """Blend target and strength of PLAYPAL palettes 1-13 (damage, pickup, radiation suit)."""
    raw = wad.lump("PLAYPAL")
    pals = [[tuple(raw[768 * k + 3 * i:768 * k + 3 * i + 3]) for i in range(256)] for k in range(14)]
    fx = []
    for k in range(1, 14):
        target = (255, 0, 0) if k <= 8 else (215, 186, 69) if k <= 12 else (0, 256, 0)
        num = den = 0
        for i in range(256):
            for c in range(3):
                d = target[c] - pals[0][i][c]
                num += (pals[k][i][c] - pals[0][i][c]) * d
                den += d * d
        fx.append([round(target[0] / 255, 3), round(target[1] / 255, 3), round(target[2] / 255, 3),
                   round(num / den, 4)])
    return fx


def pow2(n):
    p = 1
    while p < n:
        p *= 2
    return p


class Wad:
    def __init__(self, path):
        self.data = Path(path).read_bytes()
        ident, count, offset = struct.unpack_from("<4sii", self.data, 0)
        if ident not in (b"IWAD", b"PWAD"):
            raise SystemExit("not a WAD file")
        self.lumps = []
        for i in range(count):
            pos, size, name = struct.unpack_from("<ii8s", self.data, offset + 16 * i)
            self.lumps.append((name.split(b"\0")[0].decode("ascii").upper(), pos, size))
        self.index = {}
        for i, (name, _, _) in enumerate(self.lumps):
            self.index[name] = i

    def has(self, name):
        return name in self.index

    def lump(self, name):
        _, pos, size = self.lumps[self.index[name]]
        return self.data[pos:pos + size]

    def map_lumps(self, mapname):
        start = self.index[mapname]
        out = {}
        for name, pos, size in self.lumps[start + 1:start + 11]:
            out[name] = self.data[pos:pos + size]
        return out


def decode_patch(data, palette):
    w, h, left, top = struct.unpack_from("<HHhh", data, 0)
    columns = struct.unpack_from("<%dI" % w, data, 8)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = img.load()
    for x, off in enumerate(columns):
        p = off
        while data[p] != 255:
            topdelta, length = data[p], data[p + 1]
            for i in range(length):
                y = topdelta + i
                if y < h:
                    px[x, y] = palette[data[p + 3 + i]] + (255,)
            p += length + 4
    return img, left, top


class Textures:
    def __init__(self, wad, palette):
        self.wad, self.palette = wad, palette
        pnames = wad.lump("PNAMES")
        n = struct.unpack_from("<i", pnames, 0)[0]
        self.pnames = [pnames[4 + 8 * i:12 + 8 * i].split(b"\0")[0].decode().upper() for i in range(n)]
        self.defs = {}
        for lump in ("TEXTURE1", "TEXTURE2"):
            if not wad.has(lump):
                continue
            d = wad.lump(lump)
            count = struct.unpack_from("<i", d, 0)[0]
            for off in struct.unpack_from("<%di" % count, d, 4):
                name = d[off:off + 8].split(b"\0")[0].decode().upper()
                _masked, w, h, _cd, pc = struct.unpack_from("<iHHiH", d, off + 8)
                patches = [struct.unpack_from("<hhhhh", d, off + 22 + 10 * i) for i in range(pc)]
                self.defs[name] = (w, h, patches)
        self.patch_cache = {}

    def patch(self, index):
        name = self.pnames[index]
        if name not in self.patch_cache:
            self.patch_cache[name] = decode_patch(self.wad.lump(name), self.palette)[0]
        return self.patch_cache[name]

    def compose(self, name):
        w, h, patches = self.defs[name]
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        for ox, oy, pidx, _step, _cmap in patches:
            p = self.patch(pidx)
            img.paste(p, (ox, oy), p)
        return img


def lua_key(k):
    if isinstance(k, str) and k.isidentifier():
        return k
    return "[%s]" % lua_value(k)


def lua_value(v):
    if isinstance(v, dict):
        return "{" + ",".join("%s=%s" % (lua_key(k), lua_value(x)) for k, x in v.items()) + "}"
    if isinstance(v, (list, tuple)):
        return "{" + ",".join(lua_value(x) for x in v) + "}"
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return repr(round(v, 4))
    return str(v)


def find_sprite_lump(wad, prefix, frame):
    for rot in ("0", "1"):
        if wad.has(prefix + frame + rot):
            return prefix + frame + rot
    for name, _, _ in wad.lumps:
        if name.startswith(prefix + frame) and len(name) in (6, 8):
            return name
    return None


def sprite_frames(wad):
    frames = {}
    for name, _, _ in wad.lumps:
        prefix = name[:4]
        if prefix not in FRAME_PREFIXES or len(name) not in (6, 8):
            continue
        frame, rotation = name[4], name[5]
        if not frame.isalpha() or not rotation.isdigit():
            continue
        frames.setdefault(prefix, {}).setdefault(frame, {})[int(rotation)] = {
            "lump": name, "flip": False,
        }
        if len(name) == 8:
            mirror_frame, mirror_rotation = name[6], name[7]
            if mirror_frame.isalpha() and mirror_rotation.isdigit():
                frames.setdefault(prefix, {}).setdefault(mirror_frame, {})[int(mirror_rotation)] = {
                    "lump": name, "flip": True,
                }
    return frames


def clean(name):
    name = name.split(b"\0")[0].decode("ascii").upper()
    return "" if name in ("-", "") else name


def convert_map(wad, mapname):
    m = wad.map_lumps(mapname)
    verts = [struct.unpack_from("<hh", m["VERTEXES"], 4 * i) for i in range(len(m["VERTEXES"]) // 4)]

    sectors = []
    for i in range(len(m["SECTORS"]) // 26):
        fl, ce, ft, ct, light, special, tag = struct.unpack_from("<hh8s8shhh", m["SECTORS"], 26 * i)
        sectors.append({"fl": fl, "ce": ce, "ft": clean(ft), "ct": clean(ct), "li": light, "sp": special, "tg": tag})

    sides = []
    for i in range(len(m["SIDEDEFS"]) // 30):
        xo, yo, up, lo, mi, sec = struct.unpack_from("<hh8s8s8sh", m["SIDEDEFS"], 30 * i)
        sides.append((xo, yo, clean(up), clean(lo), clean(mi), sec))

    linedefs = []
    for i in range(len(m["LINEDEFS"]) // 14):
        v1, v2, flags, special, tag, right, left = struct.unpack_from("<hhhhhhh", m["LINEDEFS"], 14 * i)
        linedefs.append((v1, v2, flags, special, tag, right, left))

    lines = []
    for v1, v2, flags, special, tag, right, left in linedefs:
        lines.append({
            "x1": verts[v1][0], "y1": verts[v1][1], "x2": verts[v2][0], "y2": verts[v2][1],
            "fl": flags, "sp": special, "tg": tag,
            "fs": sides[right][5] + 1 if right >= 0 else 0,
            "bs": sides[left][5] + 1 if left >= 0 else 0,
        })

    segs = []
    for i in range(len(m["SEGS"]) // 12):
        v1, v2, _angle, ld, side, offset = struct.unpack_from("<hhhhhh", m["SEGS"], 12 * i)
        l = linedefs[ld]
        front, back = (l[5], l[6]) if side == 0 else (l[6], l[5])
        xo, yo, up, lo, mi, fsec = sides[front]
        x1, y1 = verts[v1]
        x2, y2 = verts[v2]
        seg = {
            "x1": x1, "y1": y1, "dx": x2 - x1, "dy": y2 - y1,
            "len": ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5, "off": offset,
            "f": fsec + 1, "b": sides[back][5] + 1 if back >= 0 else 0,
            "ld": ld + 1, "xo": xo, "yo": yo,
        }
        if l[2] & 8:
            seg["pt"] = 1  # upper unpegged
        if l[2] & 16:
            seg["pb"] = 1  # lower unpegged
        if l[3] == 48:
            seg["sc"] = 1  # scrolling wall
        for key, val in (("up", up), ("lo", lo), ("mi", mi)):
            if val:
                seg[key] = val
        segs.append(seg)

    ssectors = []
    for i in range(len(m["SSECTORS"]) // 4):
        count, first = struct.unpack_from("<hh", m["SSECTORS"], 4 * i)
        ssectors.append({"first": first + 1, "n": count})

    def child(c):
        c &= 0xFFFF
        return -((c & 0x7FFF) + 1) if c & 0x8000 else c + 1

    nodes = []
    for i in range(len(m["NODES"]) // 28):
        x, y, dx, dy = struct.unpack_from("<hhhh", m["NODES"], 28 * i)
        right, left = struct.unpack_from("<HH", m["NODES"], 28 * i + 24)
        nodes.append({"x": x, "y": y, "dx": dx, "dy": dy, "r": child(right), "l": child(left)})

    things = []
    for i in range(len(m["THINGS"]) // 10):
        x, y, angle, ttype, flags = struct.unpack_from("<hhhhh", m["THINGS"], 10 * i)
        if flags & 16:  # multiplayer only
            continue
        if ttype == 1 or flags & 7:  # player start, or present on at least one skill
            things.append({"x": x, "y": y, "a": angle, "t": ttype, "f": flags & 15})

    return {"sectors": sectors, "segs": segs, "ssectors": ssectors, "nodes": nodes,
            "root": len(nodes), "lines": lines, "things": things}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wad")
    ap.add_argument("--map", default="E1M1")
    ap.add_argument("--ffmpeg", help="ffmpeg executable used for sounds (found automatically if omitted)")
    work = Path(__file__).resolve().parent / "work" / "music"
    ap.add_argument("--fluidsynth", default=next(iter(glob.glob(str(work / "fluidsynth" / "**" / "fluidsynth.exe"),
                                                                recursive=True)), shutil.which("fluidsynth")),
                    help="fluidsynth executable used to render the music")
    ap.add_argument("--soundfont", default=str(work / "GeneralUser-GS.sf2"), help="General MIDI soundfont for the music")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "AddOns" / "wodoom"))
    args = ap.parse_args()

    out = Path(args.out)
    (out / "tex").mkdir(parents=True, exist_ok=True)
    (out / "spr").mkdir(parents=True, exist_ok=True)

    wad = Wad(args.wad)
    pal_raw = wad.lump("PLAYPAL")[:768]
    palette = [tuple(pal_raw[3 * i:3 * i + 3]) for i in range(256)]
    level = convert_map(wad, args.map)

    # Wall textures used by the map, plus the sky.
    tex_names = {"SKY1"}
    for seg in level["segs"]:
        for key in ("up", "lo", "mi"):
            if key in seg:
                tex_names.add(seg[key])
    textures = Textures(wad, palette)
    for name in tuple(tex_names):
        if name.startswith("SW1"):
            alternate = "SW2" + name[3:]
            if alternate in textures.defs:
                tex_names.add(alternate)
    tex_info = {}
    for name in sorted(tex_names):
        if name not in textures.defs:
            print("missing texture", name, file=sys.stderr)
            continue
        img = textures.compose(name)
        w, h = img.size
        # Power-of-two resample so the client can REPEAT-wrap the texture.
        img.resize((pow2(w), pow2(h)), Image.NEAREST).save(out / "tex" / (name + ".tga"))
        tex_info[name] = {"w": w, "h": h}

    # Flats: 64x64 TGAs (REPEAT-wrapped in game) plus an average color per flat.
    (out / "flat").mkdir(parents=True, exist_ok=True)
    flat_names = {n for s in level["sectors"] for n in (s["ft"], s["ct"]) if n}
    flat_names.update(n for n in ANIMATED_FLATS if wad.has(n))
    flat_info = {}
    for name in sorted(flat_names):
        if not wad.has(name):
            continue
        data = wad.lump(name)[:4096]
        n = max(1, len(data))
        flat_info[name] = [round(sum(palette[b][i] for b in data) / n / 255, 3) for i in range(3)]
        if name != "F_SKY1" and len(data) == 4096:
            img = Image.new("RGB", (64, 64))
            img.putdata([palette[b] for b in data])
            img.save(out / "flat" / (name + ".tga"))

    # Sprites for map things, plus weapon/HUD art.
    wanted = {}
    thing_sprite = {}
    for t in level["things"]:
        spec = THING_SPRITES.get(t["t"])
        if spec is None:
            if t["t"] != 1:
                print("no sprite mapping for thing type", t["t"], file=sys.stderr)
            continue
        lump = find_sprite_lump(wad, *spec)
        if lump:
            wanted[lump] = True
            thing_sprite[t["t"]] = lump
    for lump in EXTRA_LUMPS:
        if wad.has(lump):
            wanted[lump] = True
        else:
            print("missing lump", lump, file=sys.stderr)

    frames = sprite_frames(wad)
    for name, _, _ in wad.lumps:
        if name[:4] in FRAME_PREFIXES and len(name) in (6, 8):
            wanted[name] = True

    spr_info = {}
    for lump in sorted(wanted):
        img, left, top = decode_patch(wad.lump(lump), palette)
        w, h = img.size
        pw, ph = pow2(w), pow2(h)
        canvas = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        canvas.paste(img, (0, 0))
        canvas.save(out / "spr" / (lump + ".tga"))
        spr_info[lump] = {"w": w, "h": h, "pw": pw, "ph": ph, "lo": left, "to": top}

    ffmpeg = find_ffmpeg(args.ffmpeg)
    snd_info, music_info = {}, {}
    if not ffmpeg:
        print("ffmpeg not found: sounds and music were not converted", file=sys.stderr)
    else:
        snd_info = convert_sounds(wad, out, ffmpeg)
        if args.fluidsynth and Path(args.soundfont).exists():
            music_info = convert_music(wad, out, ffmpeg, args.fluidsynth, args.soundfont)
        else:
            print("fluidsynth or soundfont missing: music was not converted", file=sys.stderr)
    assets = {"tex": tex_info, "flats": flat_info, "spr": spr_info, "thing": thing_sprite,
              "frames": frames, "cmap": colormap_gains(wad, palette), "palfx": palette_effects(wad),
              "snd": snd_info, "music": music_info}
    (out / "data_assets.lua").write_text("local _, ns = ...\nns.assets = " + lua_value(assets) + "\n", encoding="ascii")

    print("segs %d ssectors %d nodes %d lines %d sectors %d things %d" % (
        len(level["segs"]), len(level["ssectors"]), len(level["nodes"]), len(level["lines"]),
        len(level["sectors"]), len(level["things"])))
    print("textures %d flats %d sprites %d" % (len(tex_info), len(flat_info), len(spr_info)))


if __name__ == "__main__":
    main()
