"""
Helpers to run alr in the testsuite.
"""

import os
import os.path

from shutil import copytree
from e3.os.process import Run, quote_arg
from e3.fs import mkdir
from e3.testsuite.driver.classic import ProcessResult

import re


TESTSUITE_ROOT = os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))


class CalledProcessError(Exception):
    pass


def distro_is_known():
    p = run_alr('version')
    return not re.match('.*platform properties:.*DISTRO_UNKNOWN.*',
                        p.out, flags=re.S)


def prepare_env(config_dir, env):
    """
    Prepare the environment to run "alr".

    This creates the `config_dir` directory and updates `env` (environment
    variables) to point to it as alr's configuration directory.
    """
    config_dir = os.path.abspath(config_dir)
    mkdir(config_dir)
    env['ALR_CONFIG'] = config_dir

    # If distro detection is disabled via environment, configure so in alr
    if "ALIRE_DISABLE_DISTRO" in env:
        if env["ALIRE_DISABLE_DISTRO"] == "true":
            run_alr("config", "--global",
                    "--set", "distribution.disable_detection", "true")


def run_alr(*args, **kwargs):
    """
    Run "alr" with the given arguments.

    :param bool complain_on_error: If true and the subprocess exits with a
        non-zero status code, print information on the standard output (for
        debugging) and raise a CalledProcessError (to abort the test).
    :param bool quiet: If true (which is the default), append "-q" to the
        command line.
    :param bool debug: If true (which is the default), append "-d" to the
        command line. This ensures uncaught exceptions are logged instead
        of presenting a sanitized error intended for final users.
    :rtype: ProcessResult
    """

    complain_on_error = kwargs.pop('complain_on_error', True)
    debug = kwargs.pop('debug', True)
    force = kwargs.pop('force', False)
    quiet = kwargs.pop('quiet', True)
    if kwargs:
        first_unknown_kwarg = sorted(kwargs)[0]
        raise ValueError('Invalid argument: {}'.format(first_unknown_kwarg))

    argv = ['alr']
    argv.append('-n')  # always non-interactive
    if debug:
        argv.append('-d')
    if force:
        argv.append('-f')
    if quiet:
        argv.append('-q')
    argv.extend(args)
    p = Run(argv)
    if p.status != 0 and complain_on_error:
        print('The following command:')
        print('  {}'.format(' '.join(quote_arg(arg) for arg in argv)))
        print('Exitted with status code {}'.format(p.status))
        print('Output:')
        print(p.out)
        raise CalledProcessError('alr returned non-zero status code')

    # Convert CRLF line endings (Windows-style) to LF (Unix-style). This
    # canonicalization is necessary to make output comparison work on all
    # platforms.
    return ProcessResult(p.status, p.out.replace('\r\n', '\n'))


def fixtures_path(*args):
    """
    Return a path under the testsuite `fixtures` directory.
    """
    return os.path.join(TESTSUITE_ROOT, 'fixtures', *args)


def prepare_indexes(config_dir, working_dir, index_descriptions):
    """
    Populate alr's config directory with the provided indexes.

    :param str config_dir: Configuration directory for "alr".

    :param dict[str, dict] index_description: Mapping from index names to data
        used to prepare the corresponding indexes. This data dictionary accepts
        the following keys:

        * "dir" (str): Name of the directory that contains the index files. It
          is optional: if not provided, use the name of the index.

        * "in_fixtures" (bool): Whether the directory that contains the index
          files is to be found in the "fixtures" directory (by default). Look
          in the testcase's directory otherwise.

        * "priority" (int): Priority for this index. 1 by default.
    """
    indexes_dir = os.path.join(config_dir, 'indexes')
    mkdir(indexes_dir)

    for name, desc in index_descriptions.items():
        # Extract individual fields in `desc`
        def invalid_desc(reason):
            raise ValueError('invalid index description for {}: {}'
                             .format(name, reason))

        def check_type(what, type_name, value, typ):
            if not isinstance(value, typ):
                invalid_desc('{} must be a {}'.format(what, type_name))

        check_type('description', 'a dictionary', desc, dict)

        files_dir = desc.pop('dir', name)
        check_type('"dir"', 'a string', files_dir, str)

        in_fixtures = desc.pop('in_fixtures', True)
        check_type('"in_fixtures"', 'a boolean', in_fixtures, bool)

        copy_crates_src = desc.pop('copy_crates_src', False)
        check_type('"copy_crates_src"', 'a boolean', copy_crates_src, bool)

        priority = desc.pop('priority', 1)
        check_type('"priority"', 'an integer', priority, int)

        if desc:
            first_unknown_key = sorted(desc)[0]
            invalid_desc('unknown key {}'.format(repr(first_unknown_key)))

        # Compute the directory that contains index files
        files_dir = (fixtures_path(files_dir)
                     if in_fixtures else
                     files_dir)

        if copy_crates_src:
            crates_dir = fixtures_path('crates')
            copytree(crates_dir, os.path.join(working_dir, 'crates'))
            # Crates are adjacent to the index but outside it (otherwise the
            # index loader detects spurious files).

        # Finally create the index description in the config directory
        index_dir = os.path.join(indexes_dir, name)
        mkdir(index_dir)
        with open(os.path.join(index_dir, 'index.toml'), 'w') as f:
            f.write("""
name = '{}'
priority = {}
url = '{}'
            """.format(name, priority, os.path.join(working_dir, files_dir)))


def index_branch():
    """
    Identify the expected index branch from `alr version`
    """
    p = run_alr("version", quiet=False)
    for line in p.out.splitlines():
        if line.startswith("community index"):
            return line.split(':')[1].strip()
    raise Exception("Unexpected alr output, cannot find index version")


def index_version():
    """
    Identify the expected index version from `alr version`
    """
    return index_branch().split('-')[1]


def init_local_crate(name="xxx", binary=True, enter=True):
    """
    Initialize a local crate and enter its folder for further testing.

    :param str name: Name of the crate

    :param bool binary: Initialize as --bin or --lib

    :param bool enter: Enter the created crate directory
    """
    run_alr("init", name, "--bin" if binary else "--lib")
    if enter:
        os.chdir(name)


def alr_lockfile():
    return "alire.lock"


def alr_manifest():
    return "alire.toml"


def alr_touch_manifest(path="."):
    """
    Make the lockfile older than the manifest, to ensure editions to the
    manifest are detected.
    """
    os.utime(os.path.join(path, "alire.lock"), (0, 0))


def delete_array_entry_from_manifest(array, crate,
                                     fail_if_missing=True, update=True):
    """
    Manual deletion of dependencies/pins. As we emit the additions too, this is
    simpler than the actual code in alr.
    """
    with open(alr_manifest(), "rt") as manifest:
            found = False
            lines = manifest.readlines()
            orig = lines
            for i in range(1, len(lines)):
                if lines[i].startswith(f"{crate} =") \
                  and lines[i-1] == f"[[{array}]]\n":
                    lines.pop(i)
                    lines.pop(i-1)
                    found = True
                    break

    # Write the new manifest
    if found:
        with open(alr_manifest(), "wt") as manifest:
            manifest.writelines(lines)
        if update:
            run_alr("pin")  # Ensure changes don't affect next command output
    elif fail_if_missing:
            raise RuntimeError
            (f"Could not remove crate {crate} in lines:\n" + str(orig))

    # Make the lockfile "older" (otherwise timestamp is identical)
    os.utime(alr_lockfile(), (0, 0))


def alr_unpin(crate, manual=True, fail_if_missing=True, update=True):
    """
    Unpin a crate, if pinned, or no-op otherwise. Will edit the manifest or use
    the command-line, according to manual. Must be run in a crate root.
    If update, run `alr pin` to force computation of new solution
    """

    if manual:
        # Locate and remove the lines with the pin
        delete_array_entry_from_manifest("pins", crate,
                                         fail_if_missing, update)

    else:
        if not update:
            raise RuntimeError("Update cannot be disabled when using the"
                               " command-line interface")

        run_alr("pin", "--unpin", crate)


def alr_pin(crate, version="", path="", url="", commit="", branch="",
            manual=True, update=True):
    """
    Pin a crate, either manually or using the command-line interface. Use only
    one of version, path, url. Must be run in a crate root.
    When update, run `alr pin` so the new solution is computed.
    """

    if commit != "" and branch != "":
        raise RuntimeError("Do not specify both commit and branch")

    if manual:
        alr_unpin(crate, fail_if_missing=False)  # Just in case

        if version != "":
            pin_line = f'{crate} = {{ version = "{version}" }}'
        elif path != "":
            pin_line = f"{crate} = {{ path = '{path}' }}"  # literal so \ works
        elif url != "" and commit != "":
            pin_line = f"{crate} = {{ url = '{url}', commit = '{commit}' }}"
        elif url != "" and branch != "":
            pin_line = f"{crate} = {{ url = '{url}', branch = '{branch}' }}"
        elif url != "":
            pin_line = f"{crate} = {{ url = '{url}' }}"
        else:
            raise ValueError("Specify either version, path or url")

        with open(alr_manifest(), "at") as manifest:
            manifest.writelines(["\n[[pins]]\n", pin_line + "\n"])

        # Make the lockfile "older" (otherwise timestamp is identical)
        os.utime(alr_lockfile(), (0, 0))

        if update:
            run_alr("pin")  # so the changes in the manifest are applied

    else:
        if not update:
            raise RuntimeError("Update cannot be disabled when using the"
                               " command-line interface")

        args = []
        if version != "":
            args += [f"{crate}={version}"]
        else:
            args += [crate]

            if path != "":
                args += ["--use", f"{path}"]
            elif url != "":
                args += ["--use", f"{url}"]

            if commit != "":
                args += ["--commit", f"{commit}"]
            elif branch != "":
                args += ["--branch", f"{branch}"]

        run_alr("pin", *args)


def alr_with(dep="", path="", url="", commit="", branch="",
             delete=False, manual=True, update=True, force=False):
    """
    Add/remove dependencies either through command-line or manifest edition
    """
    if commit != "" and branch != "":
        raise RuntimeError("Do not specify both commit and branch")
    if path != "" and url != "":
        raise RuntimeError("Do not specify both path and url")

    if manual and dep == "":
        raise RuntimeError("Cannot manually add without explicit dependency")

    separators = "=^~<>*"

    # Fix the dependency if no version subset is in dep
    if manual and not any([separator in dep for separator in separators]):
        dep += "*"

    # Find the separator position
    pos = max([dep.find(separator) for separator in separators])

    if manual:
        if delete:
            delete_array_entry_from_manifest("depends-on", dep, update=update)
        else:
            with open(alr_manifest(), "at") as manifest:
                lines = ["\n[[depends-on]]\n",
                         f'{dep[:pos]} = "{dep[pos:]}"\n']
                manifest.writelines(lines)

            if path != "" or url != "":
                alr_pin(crate=f'{dep[:pos]}', path=path, url=url,
                        commit=commit, branch=branch, manual=manual,
                        update=False)

            # Make the lockfile "older" (otherwise timestamp is identical)
            os.utime(alr_lockfile(), (0, 0))

            if update:
                run_alr("with", force=force)

    else:
        if delete:
            run_alr("with", "--del", dep)
        else:
            args = ["with"]
            if dep != "":
                args += [dep]

            if path != "":
                args += ["--use", f"{path}"]
            elif url != "":
                args += ["--use", f"{url}"]

            if commit != "":
                args += ["--commit", f"{commit}"]
            elif branch != "":
                args += ["--branch", f"{branch}"]

            run_alr(*args, force=force)
