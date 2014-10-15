#!/usr/bin/env python3

# ***** BEGIN GPL LICENSE BLOCK *****
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
# ***** END GPL LICENCE BLOCK *****

VERBOSE = True


class FilePath:
    """
    Tiny filepath class to hide blendfile.
    """
    __slots__ = (
        "block",
        "path",
        # path may be relative to basepath
        "basedir",
        )

    def __init__(self, block, path, basedir):
        self.block = block
        self.path = path
        self.basedir = basedir

    # --------
    # filepath
    #
    @property
    def filepath(self):
        return self.block[self.path]

    @filepath.setter
    def filepath(self, filepath):
        self.block[self.path] = filepath

    # ------------------------------------------------------------------------
    # Main function to visit paths

    @staticmethod
    def visit_from_blend(
            filepath,

            # never modify the blend
            readonly=True,
            # callback that creates a temp file and returns its path.
            temp_remap_cb=None,

            # recursive options
            recursive=False,
            # list of ID block names we want to load, or None to load all
            block_codes=None,
            # root when we're loading libs indirectly
            rootdir=None,
            level=0,
            ):

        import os

        if VERBOSE:
            indent_str = "  " * level
            print(indent_str + "Opening:", filepath)
            print(indent_str + "... blocks:", block_codes)


        basedir = os.path.dirname(os.path.abspath(filepath))
        if rootdir is None:
            rootdir = basedir

        if recursive and (level > 0) and (block_codes is not None):
            expand_codes = set()
            def block_expand(block):
                # TODO, expand ID's
                return block
        else:
            expand_codes = None
            def block_expand(block):
                return block

        if block_codes is None:
            iter_blocks_id = lambda code: blend.find_blocks_from_code(code)
        else:
            iter_blocks_id = lambda code: (block_expand(block)
                                           for block in blend.find_blocks_from_code(code)
                                           if block[b'id.name'] in block_codes)

        if expand_codes is None:
            iter_blocks_lib = lambda: blend.find_blocks_from_code(b'ID')
        else:
            iter_blocks_lib = lambda: (block
                                       for block in blend.find_blocks_from_code(b'ID')
                                       if block[b'name'] in expand_codes)


        if temp_remap_cb is not None:
            filepath_tmp = temp_remap_cb(filepath)
        else:
            filepath_tmp = filepath

        import blendfile
        blend = blendfile.open_blend(filepath_tmp, "rb" if readonly else "r+b")

        for block in iter_blocks_id(b'IM'):
            print(block[b'name'], basedir)
            yield FilePath(block, b'name', basedir), rootdir

        if recursive:
            # look into libraries
            lib_all = {}

            for block in iter_blocks_lib():
                lib_id = block[b'lib']
                lib = blend.find_block_from_offset(lib_id)
                lib_path = lib[b'name']

                # import IPython; IPython.embed()

                # get all data needed to read the blend files here (it will be freed!)
                # lib is an address at the moment, we only use as a way to group
                lib_all.setdefault(lib_path, []).append(block[b'name'])

        # do this after, incase we mangle names above
        for block in iter_blocks_id(b'LI'):
            yield FilePath(block, b'name', basedir), rootdir

        blend.close()

        # ----------------
        # Handle Recursive
        if recursive:
            # now we've closed the file, loop on other files
            for lib_path, lib_block_codes in lib_all.items():
                # import IPython; IPython.embed()
                lib_path_abs = utils.abspath(lib_path, basedir)
                if VERBOSE:
                    print((indent_str + "  "), "Library: ", filepath, " -> ", lib_path_abs, sep="")
                    print((indent_str + "  "), lib_block_codes)
                yield from FilePath.visit_from_blend(
                        lib_path_abs,
                        readonly=readonly,
                        temp_remap_cb=temp_remap_cb,
                        recursive=True,
                        block_codes=set(lib_block_codes),
                        rootdir=rootdir,
                        level=level + 1,
                        )


class utils:
    # fake module
    __slots__ = ()

    @staticmethod
    def abspath(path, start, library=None):
        import os
        if path.startswith(b'//'):
            # if library:
            #     start = os.path.dirname(abspath(library.filepath))
            return os.path.join(start, path[2:])
        return path


def pack(blendfile_src, blendfile_dst):
    import os
    import shutil

    path_temp_ls = []
    path_copy_ls = []

    def temp_remap_cb(filepath):
        """
        Create temp files in the destination path.
        """
        filepath_tmp = os.path.join(base_dir_dst, os.path.basename(filepath)) + b'@'
        print(filepath, filepath_tmp)
        shutil.copy(filepath, filepath_tmp)
        path_temp_ls.append(filepath_tmp)
        return filepath_tmp

    base_dir_src = os.path.dirname(blendfile_src)
    base_dir_dst = os.path.dirname(blendfile_dst)

    for fp, rootdir in FilePath.visit_from_blend(
            blendfile_src,
            readonly=False,
            temp_remap_cb=temp_remap_cb,
            recursive=True):

        # assume the path might be relative
        path_rel = fp.filepath
        path_base = path_rel.split(b"\\")[-1].split(b"/")[-1]
        path_src = utils.abspath(path_rel, fp.basedir)
        path_dst = os.path.join(base_dir_dst, path_base)

        # rename in the blend
        fp.filepath = b"//" + path_base

        # add to copylist
        path_copy_ls.append((path_src, path_dst))

    for i, fn in enumerate(path_temp_ls):
        if i == 0:
            shutil.move(fn, blendfile_dst)
        else:
            # strip '@'
            shutil.move(fn, fn[:-1])

    for src, dst in path_copy_ls:
        if not os.path.exists(src):
            print("  Source missing! %r" % src)
        else:
            print("  Copying %r -> %r" % (src, dst))
            shutil.copy(src, dst)

    print("  Written:", blendfile_dst)


if __name__ == "__main__":
    pack(b"/src/blendfile/test/paths.blend", b"/src/blendfile/test/out/paths.blend")
