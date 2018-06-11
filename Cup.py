import os
import sys
import logging
import functools
import subprocess

import sublime
import sublime_plugin

sys.path.append(os.path.dirname(__file__))

startupinfo = None
if hasattr(subprocess, "STARTUPINFO"):
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags = subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE


def save_view(vid):
    view = sublime.View(vid)
    if view.is_valid():
        view.run_command("save")


class CupReplaceRegionCommand(sublime_plugin.TextCommand):

    def run(self, edit, text=None, save=False, region=None):
        if text:
            region = sublime.Region(*region) or sublime.Region(0, self.view.size())
            self.view.replace(edit, region, text)
            if save:
                sublime.set_timeout_async(
                    functools.partial(save_view, self.view.id()), 1
                )


class CoffeescriptSortImportsCommand(sublime_plugin.TextCommand):
    import_re = r'^import\s+[^\'"]+\s+from\s+[\'"][^\'"]+[\'"]$'
    sorter = "isort-coffee"

    def get_import_region(self):
        import_regions = self.view.find_all(self.import_re, sublime.IGNORECASE)
        if import_regions:
            return import_regions[0].cover(import_regions[-1])

        return None

    def sort_cmd(self, isort_coffee_bin=None):
        return [isort_coffee_bin or self.sorter]

    def sort_imports(self, import_region, cmd, vid, save=False):
        view = sublime.View(vid)
        if view.is_valid():
            code = view.substr(import_region)

        with subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            startupinfo=startupinfo,
        ) as coffee:
            try:
                out, err = coffee.communicate(code.encode(), timeout=10)
                if err:
                    logging.error(err)
                    return

            except subprocess.TimeoutExpired:
                coffee.kill()
                logging.error("Sorter timed out")
                return

        sorted_imports = out.decode("utf-8")
        if not sorted_imports:
            logging.error("No sorted imports returned")
            return

        args = {
            "text": sorted_imports.strip(),
            "region": (import_region.a, import_region.b),
            "save": save,
        }
        view = sublime.View(vid)
        if view.is_valid():
            view.run_command("cup_replace_region", args)

    def is_enabled(self):
        return self.view.match_selector(0, "source.coffee")

    def is_visible(self):
        return self.view.match_selector(0, "source.coffee")

    def run(self, edit, save=False):
        settings = self.view.settings().get("cup") or {}
        import_region = self.get_import_region()
        if not import_region:
            logging.warning("No import region detected")
            if save:
                self.view.run_command("save")
            return

        cmd = self.sort_cmd(settings.get("isort_coffee_bin"))
        sublime.set_timeout_async(
            functools.partial(
                self.sort_imports, import_region, cmd, self.view.id(), save=save
            )
        )


class CupInsertSnippet(sublime_plugin.TextCommand):

    def run(self, edit, **kwargs):
        if not kwargs:
            return

        if self.view.sel():
            sel = self.view.sel()[0]
            if not self.view.substr(
                sublime.Region(sel.begin() - 1, sel.begin())
            ).isspace():
                self.view.insert(edit, sel.begin(), " ")

        self.view.run_command("insert_snippet", kwargs)
