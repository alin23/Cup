import os
import re
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
    def run(self, edit, text=None, save=False, region=None, prettify=False):
        if text:
            region = sublime.Region(*region) or sublime.Region(0, self.view.size())
            self.view.replace(edit, region, text)
            if save and not prettify:
                sublime.set_timeout_async(
                    functools.partial(save_view, self.view.id()), 1
                )
            if prettify:
                self.view.run_command("js_prettier", {"save_file": save})


class CupSortImportsCommand(sublime_plugin.TextCommand):
    import_re = r'^import\s+[^\'"]+\s+from\s+[\'"][^\'"]+[\'"]$'
    sorter = "isort-coffee"

    def get_import_region(self, code=None):
        import_regions = self.view.find_all(self.import_re, sublime.IGNORECASE)
        if import_regions:
            return import_regions[0].cover(import_regions[-1])

        return None

    def sort_cmd(self, isort_coffee_bin=None):
        return [isort_coffee_bin or self.sorter]

    def get_import_code(self, code):
        import_pattern = re.compile(self.import_re, re.M)
        matches = list(import_pattern.finditer(code))
        if matches:
            start, end = matches[0].start(), matches[-1].end()
            return start, end, code[start:end]

        return None

    def sort_imports(
        self, cmd, vid, import_region=None, code=None, save=False, prettify=False
    ):
        view = sublime.View(vid)
        if not view.is_valid():
            return

        sublime.status_message("Sorting imports...")

        import_code = ""
        if import_region:
            import_code = view.substr(import_region)
        else:
            imports = self.get_import_code(code)
            if imports:
                start, end, import_code = imports

        if import_code:
            with subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                startupinfo=startupinfo,
            ) as coffee:
                try:
                    out, err = coffee.communicate(import_code.encode(), timeout=10)
                    if err:
                        logging.error(err)
                except subprocess.TimeoutExpired:
                    coffee.kill()
                    logging.error("Sorter timed out")
                else:
                    sorted_imports = out.decode("utf-8")
                    if not sorted_imports:
                        logging.error("No sorted imports returned")

            if import_region:
                text = sorted_imports.strip()
                region = (import_region.a, import_region.b)
            else:
                text = code[:start] + sorted_imports.strip() + code[end:]
                region = (0, view.size())

            args = {"text": text, "region": region, "save": save, "prettify": prettify}
        else:
            args = {
                "text": code,
                "region": (0, view.size()),
                "save": save,
                "prettify": prettify,
            }

        view = sublime.View(vid)
        if view.is_valid():
            view.run_command("cup_replace_region", args)

    def is_enabled(self):
        return self.view.match_selector(0, "source.coffee")

    def is_visible(self):
        return self.view.match_selector(0, "source.coffee")

    def run(self, edit, save=False, code=None, prettify=False):
        try:
            settings = self.view.settings().get("cup") or {}
            cmd = self.sort_cmd(settings.get("isort_coffee_bin"))
            if not code:
                import_region = self.get_import_region()
                if not import_region:
                    logging.warning("No import region detected")
                    if save:
                        self.view.run_command("save")
                    return

                sublime.set_timeout_async(
                    functools.partial(
                        self.sort_imports,
                        cmd,
                        self.view.id(),
                        import_region=import_region,
                        save=save,
                        prettify=prettify,
                    )
                )
            else:
                sublime.set_timeout_async(
                    functools.partial(
                        self.sort_imports,
                        cmd,
                        self.view.id(),
                        code=code,
                        save=save,
                        prettify=prettify,
                    )
                )
        except:
            if save:
                self.view.run_command("save")


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
