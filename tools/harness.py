#!/usr/bin/env python3
"""Offline harness: runs the addon in Lua 5.1 against a stub WoW API and rasterizes one frame to PNG.

Usage: python harness.py <x> <y> <angle_deg> <out.png> [sequence]
Sequence is comma separated: N (idle frames), KEY:N (hold a key for N frames), USE, FIRE.
"""
import os
import sys
from pathlib import Path

from lupa import lua51
from PIL import Image

ADDON_DIR = Path(__file__).resolve().parent.parent / "AddOns" / "wodoom"

STUB = r"""
local noop = function() end
local textures = {}
__tex = textures
local Methods = {}
local function newObject()
    return setmetatable({ shown = true, scripts = {} }, {
        __index = function(t, k)
            local v = Methods[k]
            if v ~= nil then return v end
            if type(k) == "string" and k:match("^[A-Z]") then return noop end
        end,
    })
end
function Methods:SetPoint(point, ...)
    local a, b, c, d = ...
    if type(a) == "table" then self.x, self.y = c or 0, d or 0 else self.x, self.y = a or 0, b or 0 end
end
function Methods:SetSize(w, h) self.w, self.h = w, h end
function Methods:SetWidth(w) self.w = w end
function Methods:SetHeight(h) self.h = h end
function Methods:SetTexture(path, hw) self.path, self.wrap, self.color = path, hw, nil end
function Methods:SetColorTexture(r, g, b, a) self.color, self.path = { r, g, b, a or 1 }, nil end
function Methods:SetTexCoord(...) self.tc = { ... } end
function Methods:SetVertexColor(r, g, b) self.vtx = { r, g, b } end
function Methods:SetAlpha(a) self.alpha = a end
function Methods:SetAllPoints() self.full = true end
function Methods:Show() self.shown = true end
function Methods:Hide() self.shown = false end
function Methods:SetShown(s) self.shown = s end
function Methods:IsShown() return self.shown end
function Methods:SetScript(name, fn) self.scripts[name] = fn end
function Methods:CreateTexture(name, layer, template, sub)
    local t = newObject()
    t.layer, t.sub, t.order = layer or "ARTWORK", sub or 0, #textures + 1
    textures[#textures + 1] = t
    return t
end
function Methods:CreateFontString() return newObject() end

function CreateFrame() return newObject() end
UIParent = newObject()
UISpecialFrames = {}
SlashCmdList = {}
tinsert = table.insert
random = math.random
function wipe(t) for k in pairs(t) do t[k] = nil end return t end
function PlaySoundFile() end
function PlayMusic(path) __music = path end
function StopMusic() __music = nil end
"""

LAYERS = {"BACKGROUND": 0, "BORDER": 1, "ARTWORK": 2, "OVERLAY": 3, "HIGHLIGHT": 4}
_images = {}


def load_image(path):
    parts = path.replace("/", "\\").split("\\")
    key = "/".join(parts[-2:])
    if key not in _images:
        img = Image.open(ADDON_DIR / parts[-2] / parts[-1]).convert("RGBA")
        _images[key] = (img.load(), img.size)
    return _images[key]


def rasterize(textures, width=640, height=480):
    canvas = Image.new("RGB", (width, height), (0, 0, 0))
    out = canvas.load()
    items = []
    for i in range(1, len(textures) + 1):
        t = textures[i]
        if not t["shown"]:
            continue
        items.append((LAYERS.get(t["layer"], 2), t["sub"], i, t))
    items.sort(key=lambda it: it[:3])
    for _l, _s, _i, t in items:
        w, h = t["w"], t["h"]
        if t["full"]:
            w, h, x0, y0 = width, height, 0, 0
        elif w is None or h is None:
            continue
        else:
            x0, y0 = round(t["x"] or 0), round(-(t["y"] or 0))
        w, h = int(round(w)), int(round(h))
        vr, vg, vb = (t["vtx"][1], t["vtx"][2], t["vtx"][3]) if t["vtx"] else (1, 1, 1)
        alpha = t["alpha"] if t["alpha"] is not None else 1
        if t["color"]:
            c = t["color"]
            col = (c[1] * vr, c[2] * vg, c[3] * vb)
            a = c[4] * alpha
            for y in range(max(0, y0), min(height, y0 + h)):
                for x in range(max(0, x0), min(width, x0 + w)):
                    r0, g0, b0 = out[x, y]
                    out[x, y] = (int(r0 * (1 - a) + col[0] * 255 * a), int(g0 * (1 - a) + col[1] * 255 * a),
                                 int(b0 * (1 - a) + col[2] * 255 * a))
        elif t["path"]:
            px, (iw, ih) = load_image(t["path"])
            tc = t["tc"]
            if tc and len(tc) == 8:
                # ULx, ULy, LLx, LLy, URx, URy, LRx, LRy: bilinear across the quad.
                ulx, uly, llx, lly, urx, ury, lrx, lry = (tc[k] for k in range(1, 9))
                quad = True
            else:
                u0, u1, v0, v1 = (tc[1], tc[2], tc[3], tc[4]) if tc else (0, 1, 0, 1)
                quad = False
            repeat = t["wrap"] == "REPEAT"
            for j in range(max(0, y0), min(height, y0 + h)):
                fy = ((j - y0) + 0.5) / h
                v = v0 + (v1 - v0) * fy if not quad else 0
                if repeat and not quad:
                    v %= 1.0
                sy = min(ih - 1, max(0, int(v * ih)))
                for i in range(max(0, x0), min(width, x0 + w)):
                    fx = ((i - x0) + 0.5) / w
                    if quad:
                        tx0, ty0 = ulx + (urx - ulx) * fx, uly + (ury - uly) * fx
                        tx1, ty1 = llx + (lrx - llx) * fx, lly + (lry - lly) * fx
                        u, v = tx0 + (tx1 - tx0) * fy, ty0 + (ty1 - ty0) * fy
                        if repeat:
                            u %= 1.0
                            v %= 1.0
                        sy = min(ih - 1, max(0, int(v * ih)))
                    else:
                        u = u0 + (u1 - u0) * fx
                        if repeat:
                            u %= 1.0
                    sx = min(iw - 1, max(0, int(u * iw)))
                    r, g, b, a = px[sx, sy]
                    if a == 0:
                        continue
                    aa = a / 255 * alpha
                    r0, g0, b0 = out[i, j]
                    out[i, j] = (int(r0 * (1 - aa) + r * vr * aa), int(g0 * (1 - aa) + g * vg * aa),
                                 int(b0 * (1 - aa) + b * vb * aa))
    return canvas


def main():
    x, y, angle, out = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
    seq = sys.argv[5] if len(sys.argv) > 5 else "0"
    lua = lua51.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(STUB)
    lua.execute("ns = {}")
    ns = lua.eval("ns")
    run = lua.eval("function(path, ns) local f = assert(loadfile(path)); f('wodoom', ns) end")
    for name in ("data_level.lua", "data_assets.lua", "wodoom.lua"):
        run(str(ADDON_DIR / name), ns)
    state = ns["state"]
    state["P"]["x"], state["P"]["y"] = x, y
    ns["setAngle"](angle * 3.14159265358979 / 180)
    columns = os.environ.get("WODOOM_COLS")
    if columns is not None:
        if columns not in ("160", "320"):
            raise ValueError("WODOOM_COLS must be 160 or 320")
        ns["setColumns"](int(columns))
    preset = os.environ.get("WODOOM_PRESET")
    if preset:
        lua.eval('SlashCmdList["WODOOM"]')(preset)
    keys = state["keys"]
    for part in seq.split(","):
        if part in ("USE", "FIRE"):
            ns["useLine" if part == "USE" else "fire"]()
        elif ":" in part:
            key, count = part.split(":")
            keys[key] = True
            for _ in range(int(count)):
                ns["update"](1 / 30)
            keys[key] = None
        else:
            for _ in range(int(part)):
                ns["update"](1 / 30)
    print("player at %.0f,%.0f" % (state["P"]["x"], state["P"]["y"]))
    ns["render"]()
    textures = lua.eval("__tex")
    n = len(textures)
    shown = sum(1 for i in range(1, n + 1) if textures[i]["shown"])
    print("columns %d; textures created %d, shown %d" % (ns["getColumns"](), n, shown))
    rasterize(textures).save(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
