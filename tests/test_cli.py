#!/usr/bin/env python3
# Apache License, Version 2.0

"""
Test bam command line client

Run all tests:

   python3 test_cli.py

Run a single test:

   python3 -m unittest test_cli.BamCommitTest.test_checkout
"""

VERBOSE = 1

# ------------------
# Ensure module path
import os
import sys
path = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "client", "cli"))
if path not in sys.path:
    sys.path.append(path)
del os, sys, path
# --------


# ------------------
# Ensure module path
import os
import sys
path = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "webservice", "bam"))
if path not in sys.path:
    sys.path.append(path)
del os, sys, path
# --------


# -----------------------------------------
# Ensure we get stdout & stderr on sys.exit
#
# We have this because we override the standard output,
# _AND_ during this state a command may call `sys.exit`
# In this case, we the output is hidden which is very annoying.
#
# So override `sys.exit` with one that prints to the original
# stdout/stderr on exit.
if 1:
    import sys

    def exit(status):
        import io
        globals().update(sys.exit.exit_data)
        if isinstance(sys.stdout, io.StringIO):

            _stdout.write("\nsys.exit(%d) with message:\n" % status)

            sys.stdout.seek(0)
            sys.stderr.seek(0)
            _stdout.write(sys.stdout.read())
            _stderr.write(sys.stderr.read())

            _stdout.write("\n")

            _stdout.flush()
            _stderr.flush()
        _exit(status)

    exit.exit_data = {
        "_exit": sys.exit,
        "_stdout": sys.stdout,
        "_stderr": sys.stderr,
        }
    sys.exit = exit
    del exit
    del sys
# --------

# --------------------------------------------
# Don't Exit when argparse fails to parse args
#
# Argparse can call `sys.exit` if the wrong args are given.
# This messes with testing, which we want to keep the process running.
#
# This monkey-patches in an exist function which simply raises an exception.
# We could do something a bit nicer here,
# but for now just use a basic exception.
import argparse
def argparse_fake_exit(self, status, message):
    sys.__stdout__.write(message)
    raise Exception(message)

argparse.ArgumentParser.exit = argparse_fake_exit
del argparse_fake_exit
del argparse
# --------


# ----------------------------------------------------------------------------
# Real beginning of code!

import os
import sys
import shutil
import json

TEMP_LOCAL = "/tmp/bam_test"
# Separate tmp folder for server, since we don't reset the server at every test
TEMP_SERVER = "/tmp/bam_test_server"
PORT = 5555
PROJECT_NAME = "test_project"

# running scripts next to this one!
CURRENT_DIR = os.path.dirname(__file__)


def args_as_string(args):
    """ Print args so we can paste them to run them again.
    """
    import shlex
    return " ".join([shlex.quote(c) for c in args])


def run(cmd, cwd=None):
    if VERBOSE:
        print(">>> ", args_as_string(cmd))
    import subprocess
    kwargs = dict(
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
        )
    if cwd is not None:
        kwargs["cwd"] = cwd

    proc = subprocess.Popen(cmd, **kwargs)
    stdout, stderr = proc.communicate()
    returncode = proc.returncode

    if VERBOSE:
        sys.stdout.write("   stdout:  %s\n" % stdout.strip())
        sys.stdout.write("   stderr:  %s\n" % stderr.strip())
        sys.stdout.write("   return:  %d\n" % returncode)

    return stdout, stderr, returncode


def run_check(cmd, cwd=None, returncode_ok=(0,)):
    stdout, stderr, returncode = run(cmd, cwd)
    if returncode in returncode_ok:
        return True

    # verbose will have already printed
    if not VERBOSE:
        print(">>> ", args_as_string(cmd))
        sys.stdout.write("   stdout:  %s\n" % stdout.strip())
        sys.stdout.write("   stderr:  %s\n" % stderr.strip())
        sys.stdout.write("   return:  %d\n" % returncode)
    return False


class CHDir:
    __slots__ = (
        "dir_old",
        "dir_new",
        )

    def __init__(self, directory):
        self.dir_old = os.getcwd()
        self.dir_new = directory

    def __enter__(self):
        os.chdir(self.dir_new)

    def __exit__(self, exc_type, exc_value, traceback):
        os.chdir(self.dir_old)


class StdIO:
    __slots__ = (
        "stdout",
        "stderr",
        )

    def __init__(self):
        self.stdout = sys.stdout
        self.stderr = sys.stderr

    def read(self):
        sys.stdout.seek(0)
        sys.stderr.seek(0)
        return sys.stdout.read(), sys.stderr.read()

    def __enter__(self):
        import io
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is not None:
            self.stdout.write("\n".join(self.read()))

        sys.stdout = self.stdout
        sys.stderr = self.stderr


def svn_repo_create(id_, dirname):
    return run_check(["svnadmin", "create", id_], cwd=dirname)


def svn_repo_checkout(repo, path):
    return run_check(["svn", "checkout", repo, path])


def svn_repo_populate(path):
    if not os.path.exists(path):
        os.makedirs(path)

    # TODO, we probably want to define files externally, for now this is just to see it works
    dummy_file = os.path.join(path, "file1")
    file_quick_touch(dummy_file)

    # adds all files recursively
    if not run_check(["svn", "add", path]):
        return False

    if not run_check(["svn", "commit", "-m", "First commit"], path):
        return False

    return True


def bam_run(argv, cwd=None):
    with CHDir(cwd):
        import bam

        if VERBOSE:
            sys.stdout.write("\n  running:  ")
            if cwd is not None:
                sys.stdout.write("cd %r ; " % cwd)
            import shlex
            sys.stdout.write("bam %s\n" % " ".join([shlex.quote(c) for c in argv]))


            # input('press_key!:')

        with StdIO() as fakeio:
            bam.main(argv)
            ret = fakeio.read()

        if VERBOSE:
            sys.stdout.write("   stdout:  %s\n" % ret[0].strip())
            sys.stdout.write("   stderr:  %s\n" % ret[1].strip())

    return ret


def file_quick_write(path, filepart=None, data=None):
    """Quick file creation utility.
    """
    if data is None:
        data = b''
    elif type(data) is bytes:
        mode = 'wb'
    elif type(data) is str:
        mode = 'w'
    else:
        raise Exception("type %r not known" % type(data))

    if filepart is not None:
        path = os.path.join(path, filepart)

    with open(path, mode) as f:
        f.write(data)

def file_quick_read(path, filepart=None, mode='rb'):

    if filepart is not None:
        path = os.path.join(path, filepart)

    with open(path, mode) as f:
        return f.read()


def file_quick_touch(path, filepart=None, times=None):
    if filepart is not None:
        path = os.path.join(path, filepart)
    with open(path, 'a'):
        os.utime(path, times)


def blendfile_template_create(blendfile, create_id, deps):
    returncode_test = 123
    blendfile_deps_json = os.path.join(TEMP_LOCAL, "blend_template_deps.json")
    os.makedirs(os.path.dirname(blendfile), exist_ok=True)
    stdout, stderr, returncode = run(
            ("blender",
             "--background",
             "--factory-startup",
             "-noaudio",
             "--python",
             os.path.join(CURRENT_DIR, "blendfile_templates.py"),
             "--",
             blendfile,
             blendfile_deps_json,
             create_id,
             str(returncode_test),
             ))

    if os.path.exists(blendfile_deps_json):
        import json
        with open(blendfile_deps_json, 'r') as f:
            deps[:] = json.load(f)
        os.remove(blendfile_deps_json)
    else:
        deps.clear()

    if returncode != returncode_test:
        # verbose will have already printed
        if not VERBOSE:
            print(">>> ", args_as_string(cmd))
            sys.stdout.write("   stdout:  %s\n" % stdout.strip())
            sys.stdout.write("   stderr:  %s\n" % stderr.strip())
            sys.stdout.write("   return:  %d\n" % returncode)
        return False
    else:
        return True


def wait_for_input():
    """for debugging,
    so we can inspect the state of the system before the test finished.
    """
    input('press any key to continue:')

# ------------------------------------------------------------------------------
# Server


def server(mode='testing', debug=False):
    """Start development server via Flask app.run() in a separate thread. We need server
    to run in order to check most of the client commands.
    """

    def run_testing_server():
        from application import app

        # If we run the server in testing mode (the default) we override sqlite database,
        # with a testing, disposable one (create TMP dir)
        if mode == 'testing':
            from application import db
            from application.modules.projects.model import Project, ProjectSetting
            # Override sqlite database
            if not os.path.isdir(TEMP_SERVER):
                os.makedirs(TEMP_SERVER)
            app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + TEMP_SERVER + '/bam_test.db'
            # Use the model definitions to create all the tables
            db.create_all()
            # Create a testing project, based on the global configuration (depends on a
            # correct initialization of the SVN repo and on the creation of a checkout)

            # TODO(fsiddi): turn these values in variables
            project = Project(
                name=PROJECT_NAME,
                repository_path="/tmp/bam_test/remote_store/svn_checkout",
                upload_path="/tmp/bam_test/remote_store/upload",
                status="active",
                )
            db.session.add(project)
            db.session.commit()

            setting = ProjectSetting(
                project_id=project.id,
                name="svn_password",
                value="my_password",
                data_type="str",
                )
            db.session.add(setting)
            db.session.commit()

            setting = ProjectSetting(
                project_id=project.id,
                name="svn_default_user",
                value="my_user",
                data_type="str",
                )
            db.session.add(setting)
            db.session.commit()

        # Run the app in production mode (prevents tests to run twice)
        app.run(port=PORT, debug=debug)

    from multiprocessing import Process
    p = Process(target=run_testing_server, args=())
    p.start()

    os.system("sleep 1")
    return p


def global_setup(use_server=True):
    data = []

    if VERBOSE:
        # for server
        import logging
        logging.basicConfig(level=logging.DEBUG)
        del logging

    shutil.rmtree(TEMP_SERVER, ignore_errors=True)
    shutil.rmtree(TEMP_LOCAL, ignore_errors=True)

    if use_server:
        p = server()
        data.append(p)

    return data


def global_teardown(data, use_server=True):

    if use_server:
        p = data.pop(0)
        p.terminate()

    shutil.rmtree(TEMP_SERVER, ignore_errors=True)
    shutil.rmtree(TEMP_LOCAL, ignore_errors=True)


# ------------------------------------------------------------------------------
# Unit Tests

import unittest


class BamSimpleTestCase(unittest.TestCase):
    """ Basic testcase, only make temp dirs.
    """
    def setUp(self):

        # for running single tests
        if __name__ != "__main__":
            self._data = global_setup(use_server=False)

        if not os.path.isdir(TEMP_LOCAL):
            os.makedirs(TEMP_LOCAL)

    def tearDown(self):
        # input('Wait:')
        shutil.rmtree(TEMP_LOCAL)

        # for running single tests
        if __name__ != "__main__":
            global_teardown(self._data, use_server=False)


class BamSessionTestCase(unittest.TestCase):

    def setUp(self):

        # for running single tests
        if __name__ != "__main__":
            self._data = global_setup()

        if not os.path.isdir(TEMP_LOCAL):
            os.makedirs(TEMP_LOCAL)
        # Create local storage folder
        if not os.path.isdir(self.path_local_store):
            os.makedirs(self.path_local_store)

        # Create remote storage (usually is on the server).
        # SVN repo and SVN checkout will live here
        if not os.path.isdir(self.path_remote_store):
            os.makedirs(self.path_remote_store)

        # Check for SVN repo folder
        path_svn_repo = os.path.join(self.path_remote_store, "svn_repo")
        if not os.path.isdir(path_svn_repo):
            os.makedirs(path_svn_repo)

        # Create a fresh SVN repository
        if not svn_repo_create(self.proj_name, path_svn_repo):
            self.fail("svn_repo: create")

        # Check for SVN checkout
        path_svn_checkout = os.path.join(self.path_remote_store, "svn_checkout")

        # Create an SVN checkout of the freshly created repo
        path_svn_repo_url = "file://%s" % os.path.join(path_svn_repo, self.proj_name)
        if not svn_repo_checkout(path_svn_repo_url, path_svn_checkout):
            self.fail("svn_repo: checkout %r" % path_svn_repo_url)

        # Populate the repo with an empty file
        if not svn_repo_populate(os.path.join(path_svn_checkout, self.proj_name)):
            self.fail("svn_repo: populate")

    def tearDown(self):
        # input('Wait:')
        shutil.rmtree(TEMP_LOCAL)

        # for running single tests
        if __name__ != "__main__":
            global_teardown(self._data)

    def get_url(self):
        url_full = "%s@%s/%s" % (self.user_name, self.server_addr, self.proj_name)
        user_name, url = url_full.rpartition('@')[0::2]
        return url_full, user_name, url

    def init_defaults(self):
        self.path_local_store = os.path.join(TEMP_LOCAL, "local_store")
        self.path_remote_store = os.path.join(TEMP_LOCAL, "remote_store")

        self.proj_name = PROJECT_NAME
        self.user_name = "user"
        self.server_addr = "http://localhost:%s" % PORT

    def init_repo(self):
        url_full, user_name, url = self.get_url()
        bam_run(["init", url_full], self.path_local_store)


class BamInitTest(BamSessionTestCase):
    """Test the `bam init user@http://bamserver/projectname` command.
    We verify that a project folder is created, and that it contains a .bam subfolder
    with a config file, with the right url and user values (given in the command)
    """

    def __init__(self, *args):
        self.init_defaults()
        super().__init__(*args)

    def test_init(self):
        self.init_repo()

        url_full, user_name, url = self.get_url()
        with open(os.path.join(self.path_local_store, self.proj_name, ".bam", "config")) as f:
            cfg = json.load(f)
            self.assertEqual(url, cfg["url"])
            self.assertEqual(user_name, cfg["user"])


class BamListTest(BamSessionTestCase):
    """Test for the `bam ls --json` command. We run it with --json for easier command
    output parsing.
    """

    def __init__(self, *args):
        self.init_defaults()
        super().__init__(*args)

    def test_ls(self):
        self.init_repo()

        d = os.path.join(self.path_local_store, self.proj_name)

        stdout, stderr = bam_run(["ls", "--json"], d)

        self.assertEqual("", stderr)

        import json
        ret = json.loads(stdout)


class BamCommitTest(BamSessionTestCase):
    """Test for the `bam create` command. We run it with --json for easier command
    output parsing.
    """

    def __init__(self, *args):
        self.init_defaults()
        super().__init__(*args)

    def test_commit(self):
        self.init_repo()
        file_name = "testfile.txt"
        file_data = b"hello world!\n"

        proj_path = os.path.join(self.path_local_store, self.proj_name)
        co_id = "mysession"
        session_path = os.path.join(proj_path, co_id)

        stdout, stderr = bam_run(["create", co_id], proj_path)
        self.assertEqual("", stderr)

        # check an empty commit fails gracefully
        stdout, stderr = bam_run(["commit", "-m", "test message"], session_path)
        self.assertEqual("", stderr)
        self.assertEqual("Nothing to commit!\n", stdout)

        # now do a real commit
        file_quick_write(session_path, file_name, file_data)
        stdout, stderr = bam_run(["commit", "-m", "test message"], session_path)
        self.assertEqual("", stderr)

    def test_checkout(self):
        self.init_repo()
        file_data = b"yo world!\n"
        file_name = "other_file.txt"

        proj_path = os.path.join(self.path_local_store, self.proj_name)
        co_id = "mysession"
        session_path = os.path.join(proj_path, co_id)

        stdout, stderr = bam_run(["create", co_id], proj_path)
        self.assertEqual("", stderr)

        # now do a real commit
        file_quick_write(session_path, file_name, file_data)
        stdout, stderr = bam_run(["commit", "-m", "test message"], session_path)
        self.assertEqual("", stderr)

        # remove the path
        shutil.rmtree(session_path)

        # checkout the file again
        stdout, stderr = bam_run(["checkout", file_name, "--output", session_path], proj_path)
        self.assertEqual("", stderr)
        # wait_for_input()
        self.assertTrue(os.path.exists(os.path.join(session_path, file_name)))

        file_data_test = file_quick_read(os.path.join(session_path, file_name))
        self.assertEqual(file_data, file_data_test)


class BamBlendTest(BamSimpleTestCase):

    def test_create_all(self):
        """ This simply tests all the create functions run without error.
        """
        import blendfile_templates
        TEMP_SESSION = os.path.join(TEMP_LOCAL, "blend_file_template")

        def iter_files_session():
            for dirpath, dirnames, filenames in os.walk(TEMP_SESSION):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    yield filepath

        for create_id, create_fn in blendfile_templates.__dict__.items():
            if     (create_id.startswith("create_") and
                    create_fn.__class__.__name__ == "function"):

                os.makedirs(TEMP_SESSION)

                blendfile = os.path.join(TEMP_SESSION, create_id + ".blend")
                deps = []

                if not blendfile_template_create(blendfile, create_id, deps):
                    # self.fail("blend file couldn't be create")
                    # ... we want to keep running
                    self.assertTrue(False, True)  # GRR, a better way?
                    shutil.rmtree(TEMP_SESSION)
                    continue

                self.assertTrue(os.path.exists(blendfile))
                with open(blendfile, 'rb') as blendfile_handle:
                    self.assertEqual(b'BLENDER', blendfile_handle.read(7))
                os.remove(blendfile)

                # check all deps are accounted for
                for f in deps:
                    self.assertTrue(os.path.exists(f))
                for f in iter_files_session():
                    self.assertIn(f, deps)

                shutil.rmtree(TEMP_SESSION)

    def test_empty(self):
        file_name = "testfile.blend"
        blendfile = os.path.join(TEMP_LOCAL, file_name)
        if not blendfile_template_create(blendfile, "create_blank", []):
            self.fail("blend file couldn't be created")
            return

        self.assertTrue(os.path.exists(blendfile))


class BamDeleteTest(BamSessionTestCase):
    """Test for the `bam commit` command when files are being deleted.
    """

    def __init__(self, *args):
        self.init_defaults()
        super().__init__(*args)

    def test_delete(self):
        self.init_repo()
        file_name = "testfile.blend"
        file_data = b"hello world!\n"

        proj_path = os.path.join(self.path_local_store, self.proj_name)
        co_id = "mysession"
        session_path = os.path.join(proj_path, co_id)

        stdout, stderr = bam_run(["create", co_id], proj_path)
        self.assertEqual("", stderr)

        # now do a real commit
        blendfile = os.path.join(session_path, file_name)
        if not blendfile_template_create(blendfile, "create_blank", []):
            self.fail("blend file couldn't be created")
            return

        stdout, stderr = bam_run(["commit", "-m", "tests message"], session_path)
        self.assertEqual("", stderr)

         # remove the path
        shutil.rmtree(session_path)
        del session_path

        # -----------
        # New Session

        # checkout the file again
        stdout, stderr = bam_run(["checkout", file_name, "--output", "new_out"], proj_path)
        self.assertEqual("", stderr)


        # now delete the file we just checked out
        session_path = os.path.join(proj_path, "new_out")
        os.remove(os.path.join(session_path, file_name))
        stdout, stderr = bam_run(["commit", "-m", "test deletion"], session_path)
        self.assertEqual("", stderr)
        # check if deletion of the file has happened

        stdout, stderr = bam_run(["ls", "--json"], session_path)
        # check for errors in the response
        self.assertEqual("", stderr)

        # parse the response searching for the file. If it fails it means the file has
        # not been removed
        listing = json.loads(stdout)
        print(listing)
        for e in listing:
            self.assertNotEqual(e[0], file_name)


if __name__ == '__main__':
    data = global_setup()
    unittest.main(exit=False)
    global_teardown(data)

