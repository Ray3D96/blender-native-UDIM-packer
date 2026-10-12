"""Instrumented QA run: log every oracle round and refusal, capped rounds.

Usage: blender --background --python .scratch/qa_probe.py [rounds=N]
"""
import sys
import time

ADDON_PATH = "/mnt/fusion/ai-projects/blender-uv-packer"
SCENE = ADDON_PATH + "/QA_Test_Files/P_BLENDER_01.5.blend"
CAP = 8
for _a in sys.argv:
    if _a.startswith("rounds="):
        CAP = int(_a[7:])

import bpy  # noqa: E402

_old = sys.modules.get("native_udim_packer")
if _old is not None:
    try:
        _old.unregister()
    except Exception as exc:
        print(f"[warn] old module unregister: {exc}", flush=True)
for _n in [n for n in list(sys.modules)
           if n.split(".")[0] == "native_udim_packer"]:
    del sys.modules[_n]
sys.path.insert(0, ADDON_PATH)
import native_udim_packer as A  # noqa: E402
from native_udim_packer import packer as P  # noqa: E402
from native_udim_packer import layout as L  # noqa: E402
A.register()

bpy.ops.wm.open_mainfile(filepath=SCENE)
targets = [o for o in bpy.context.scene.objects
           if o.type == 'MESH' and o.data.uv_layers
           and o.data.uv_layers.active]
print(f"QA probe objects={len(targets)} cap={CAP}", flush=True)

# ---- instrument the round executor -------------------------------------
_orig_round = P._execute_round
calls = {"n": 0}


def loud_round(state, assign, positions, S, rotate_90, margin):
    calls["n"] += 1
    n = calls["n"]
    t0 = time.time()
    try:
        ext = _orig_round(state, assign, positions, S, rotate_90, margin)
        used = [i for i, e in enumerate(ext) if e is not None]
        print(f"  round{n} S={S:.6f} OK tiles={used} "
              f"dt={time.time() - t0:.2f}s", flush=True)
        return ext
    except L.PackRefusedError as exc:
        used = sorted(set(assign.values()))
        print(f"  round{n} S={S:.6f} REFUSED tiles={used} "
              f"dt={time.time() - t0:.2f}s :: {exc}", flush=True)
        raise


P._execute_round = loud_round

# ---- cap the search ------------------------------------------------------
_orig_solve = L.solve


def capped_solve(items, gx, gy, m, oracle, **kw):
    kw["max_rounds"] = CAP
    return _orig_solve(items, gx, gy, m, oracle, **kw)


P._layout_solve = capped_solve

t0 = time.time()
res = P.pack_objects(targets, 3, 1, True, True, 0.0)
dt = time.time() - t0
if "error" in res:
    print(f"QA PROBE ERROR after {dt:.1f}s: {res['error']}", flush=True)
else:
    print(f"QA PROBE OK after {dt:.1f}s S*={res.get('global_scale')!r} "
          f"rounds_total={calls['n']}", flush=True)
