# Apache License, Version 2.0

# Pass in:
#
#    blender --python blendfile_templates.py -- destination/file.blend create_command return_code
#
# 'return_code' can be any number, use to check the script completes.


def _clear_blend():
    import bpy

    # copied from batch_import.py
    unique_obs = set()
    for scene in bpy.data.scenes:
        for obj in scene.objects[:]:
            scene.objects.unlink(obj)
            unique_obs.add(obj)

    # remove obdata, for now only worry about the startup scene
    for bpy_data_iter in (bpy.data.objects, bpy.data.meshes, bpy.data.lamps, bpy.data.cameras):
        for id_data in bpy_data_iter:
            bpy_data_iter.remove(id_data)


def create_blank(deps):
    assert(isinstance(deps, list))


def create_image_single(deps):
    import bpy

    path = "//my_image.png"
    image = bpy.data.images.new(name="MyImage", width=512, height=512)
    image.filepath_raw = path
    deps.append(bpy.path.abspath(path))
    image.file_format = 'PNG'
    image.use_fake_user = True
    image.save()


if __name__ == "__main__":
    import sys
    blendfile, blendfile_deps_json, create_id, returncode = sys.argv[-4:]
    returncode = int(returncode)
    create_fn = globals()[create_id]

    # ----
    import bpy
    # no need for blend1's
    bpy.context.user_preferences.filepaths.save_version = 0
    # WEAK! (but needed)
    # save the file first, so we can do real, relative dirs
    bpy.ops.wm.save_mainfile('EXEC_DEFAULT', filepath=blendfile)
    del bpy
    # ----

    _clear_blend()
    deps = []
    create_fn(deps)
    if deps:
        with open(blendfile_deps_json, 'w') as f:
            import json
            json.dump(
                    deps, f, ensure_ascii=False,
                    check_circular=False,
                    # optional (pretty)
                    sort_keys=True, indent=4, separators=(',', ': '),
                    )
            del json

    import bpy
    bpy.ops.wm.save_mainfile('EXEC_DEFAULT', filepath=blendfile)

    import sys
    sys.exit(returncode)
