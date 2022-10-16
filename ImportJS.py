import os
import json
import functools
import subprocess
from textwrap import dedent

import sublime
import sublime_plugin

import_js_environment = {}
daemon = None


def handle_resolved_imports(
    view, resolved_imports, save=False, prettify=False, sort=False
):
    view.run_command(
        "cup_import_js",
        {
            "command": "add",
            "imports": resolved_imports,
            "save": save,
            "prettify": prettify,
            "sort": sort,
        },
    )


def plugin_loaded():
    global import_js_environment

    import_js_environment = dict(os.environ).copy()
    print("ImportJS loaded")


def plugin_unloaded():
    global daemon
    print("Stopping ImportJS daemon process")
    try:
        daemon.terminate()
    except:
        pass
    daemon = None


def no_executable_error(executable):
    return dedent(
        """
        Couldn't find executable {executable}.

        Make sure you have the `importjsd` binary installed (`npm install
        import-js -g`).

        If it is installed but you still get this message, and you are using
        something like nvm or nodenv, you probably need to configure your PATH
        correctly. Make sure that the code that sets up your PATH for these
        tools is located in .bash_profile, .zprofile, or the equivalent file
        for your shell.

        Alternatively, you might have to set the `paths` option in your
        ImportJS package user settings. Example:

        {{
            "paths": ["/Users/USERNAME/.nvm/versions/node/v4.4.3/bin"]
        }}

        To see where the importjsd binary is located, run `which importjsd`
        from the command line in your project's root.
        """.format(
            executable=executable
        )
    ).strip()


def save_view(vid):
    view = sublime.View(vid)
    if view.is_valid():
        view.run_command("save")


class CupImportJsReplaceCommand(sublime_plugin.TextCommand):
    def run(self, edit, code=None, save=False, prettify=False):
        if code and code != self.view.substr(sublime.Region(0, self.view.size())):
            self.view.replace(edit, sublime.Region(0, self.view.size()), code)
            self.view.show_at_center(0)
            if save and not prettify:
                sublime.set_timeout_async(
                    functools.partial(save_view, self.view.id()), 1
                )
            if prettify:
                self.view.run_command("js_prettier", {"save_file": save})


class CupImportJsCommand(sublime_plugin.TextCommand):
    def project_root(self):
        return self.view.window().extract_variables()["folder"]

    def start_or_get_daemon(self, project_root):
        global daemon
        if daemon is not None and daemon.poll() is not None:
            return daemon

        is_windows = os.name == "nt"
        executable = "importjsd"

        try:
            daemon = subprocess.Popen(
                [executable, "start", "--parent-pid", str(os.getppid())],
                cwd=project_root,
                env=import_js_environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=is_windows,
            )
            # The daemon process will print one line at startup of the command,
            # something like "DAEMON active. Logs will go to [...]". We need to
            # ignore this line so that we can expect json output when running
            # commands.
            daemon.stdout.readline()

            return daemon
        except FileNotFoundError as e:
            if e.strerror.find(executable) > -1:
                # If the executable is in the error message, then we believe
                # that the executable cannot be found and show a more helpful
                # message.
                sublime.error_message(no_executable_error(executable))
            else:
                # Something other than the executable cannot be found, so we
                # pass through the original message.
                sublime.error_message(e.strerror)
            raise e

    def fix_imports(
        self, cmd, payload, project_root, vid, sort=False, save=False, prettify=False
    ):
        view = sublime.View(vid)
        if not view.is_valid():
            return

        sublime.status_message("Fixing imports...")

        process = self.start_or_get_daemon(project_root)
        process.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        process.stdin.flush()
        resultJson = process.stdout.readline().decode("utf-8")
        try:
            result = json.loads(resultJson)
        except:
            print(resultJson)
            return

        if result.get("error"):
            sublime.error_message(
                "Error when executing importjs:\n\n" + result.get("error")
            )
            return

        if result.get("messages"):
            sublime.status_message("\n".join(result.get("messages")))

        if result.get("unresolvedImports"):
            view.run_command(
                "cup_import_js_replace",
                {"save": save, "prettify": prettify, "code": result.get("fileContent")},
            )
            self.ask_to_resolve(
                result.get("unresolvedImports"),
                functools.partial(
                    handle_resolved_imports,
                    view,
                    save=save,
                    prettify=prettify,
                    sort=sort,
                ),
            )
            return

        if cmd == "goto":
            view.window().open_file(result.get("goto"))
        elif sort:
            view.run_command(
                "cup_sort_imports",
                {"save": save, "prettify": prettify, "code": result.get("fileContent")},
            )
        else:
            view.run_command(
                "cup_import_js_replace",
                {"save": save, "prettify": prettify, "code": result.get("fileContent")},
            )

    def run(self, edit, **args):
        current_file_contents = self.view.substr(sublime.Region(0, self.view.size()))

        cmd = args.get("command")
        sort = args.get("sort", False)
        save = args.get("save", False)
        prettify = args.get("prettify", False)
        payload = {"command": cmd, "fileContent": current_file_contents}

        file_name = self.view.file_name()
        if file_name:
            payload["pathToFile"] = file_name
        else:
            ext = self.view.scope_name(0).split()[0].split(".")[-1]
            payload["pathToFile"] = os.path.join(self.project_root(), "tmp." + ext)

        if cmd in ("word", "goto"):
            payload["commandArg"] = self.view.substr(self.view.word(self.view.sel()[0]))

        if cmd == "add":
            payload["commandArg"] = args.get("imports")

        sublime.set_timeout_async(
            functools.partial(
                self.fix_imports,
                cmd,
                payload,
                self.project_root(),
                self.view.id(),
                sort=sort,
                save=save,
                prettify=prettify,
            )
        )

    def ask_to_resolve(self, unresolved_imports, on_resolve):
        resolved = {}
        unresolved_iter = iter(unresolved_imports)

        def ask_recurse(word):
            if not word:
                on_resolve(resolved)
                return

            def on_done(i):
                if i > -1:
                    resolved[word] = unresolved_imports[word][i]["data"]
                ask_recurse(next(unresolved_iter, None))

            self.view.show_popup_menu(
                list(map(lambda imp: imp.get("displayName"), unresolved_imports[word])),
                on_done,
            )

        ask_recurse(next(unresolved_iter, None))
