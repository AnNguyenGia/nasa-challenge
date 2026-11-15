"""Convert the credited BlendSwap Man archive to an offline GLB asset.

Requires Blender's Python module (bpy). Scripts stored in the .blend file are
disabled while opening it. Only the Man mesh is exported.
"""

from __future__ import annotations

import hashlib
import tempfile
import zipfile
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "dist" / "assets" / "Man-blendswap-8811.zip"
OUTPUT = ROOT / "dist" / "assets" / "man.glb"


def main() -> None:
    if not zipfile.is_zipfile(SOURCE):
        raise RuntimeError(f"Invalid BlendSwap archive: {SOURCE}")
    with tempfile.TemporaryDirectory(prefix="astrohealth-man-") as temporary:
        blend_file = Path(temporary) / "Man.blend"
        with zipfile.ZipFile(SOURCE) as archive:
            blend_file.write_bytes(archive.read("Man.blend"))

        bpy.context.preferences.filepaths.use_scripts_auto_execute = False
        bpy.ops.wm.open_mainfile(
            filepath=str(blend_file), load_ui=False, use_scripts=False
        )
        man = bpy.data.objects.get("Man")
        if man is None or man.type != "MESH":
            raise RuntimeError("The source archive has no Man mesh")

        bpy.ops.object.select_all(action="DESELECT")
        man.hide_set(False)
        man.select_set(True)
        bpy.context.view_layer.objects.active = man
        bpy.ops.export_scene.gltf(
            filepath=str(OUTPUT),
            export_format="GLB",
            use_selection=True,
            export_apply=True,
            export_materials="NONE",
            export_cameras=False,
            export_lights=False,
        )

    digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    print(f"Exported {OUTPUT} ({OUTPUT.stat().st_size} bytes, SHA-256 {digest})")


if __name__ == "__main__":
    main()
