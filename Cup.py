import os
import sys
import logging
import subprocess

import sublime
import sublime_plugin

sys.path.append(os.path.dirname(__file__))

startupinfo = None
if hasattr(subprocess, 'STARTUPINFO'):
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags = subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE


class CoffeescriptSortImportsCommand(sublime_plugin.TextCommand):
    import_re = r'^import\s+[^\'"]+\s+from\s+[\'"][^\'"]+[\'"]$'
    sorter = os.path.join(os.path.dirname(__file__), 'sort.js')

    def get_import_region(self):
        import_regions = self.view.find_all(self.import_re, sublime.IGNORECASE)
        if import_regions:
            return import_regions[0].cover(import_regions[-1])

        return None

    def sort_cmd(self, node_bin=None):
        return [node_bin or 'node', self.sorter]

    def sort_imports(self, import_region, cmd, edit):
        code = self.view.substr(import_region)

        with subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, stdout=subprocess.PIPE,
            startupinfo=startupinfo
        ) as coffee:
            try:
                out, err = coffee.communicate(code.encode(), timeout=10)
                if err:
                    logging.error(err)
                    return

            except subprocess.TimeoutExpired:
                coffee.kill()
                logging.error('Sorter timed out')
                return

        sorted_imports = out.decode('utf-8')
        if not sorted_imports:
            logging.error("No sorted imports returned")
            return

        try:
            self.view.replace(edit, import_region, sorted_imports.strip())
        except Exception as e:
            logging.exception(e)

    def is_enabled(self):
        return self.view.match_selector(0, 'source.coffee')

    def is_visible(self):
        return self.view.match_selector(0, 'source.coffee')

    def run(self, edit):
        settings = self.view.settings().get('cup') or {}
        import_region = self.get_import_region()
        if not import_region:
            logging.warning('No import region detected')
            return

        cmd = self.sort_cmd(settings.get('node_bin'))
        self.sort_imports(import_region, cmd, edit)


class CupInsertSnippet(sublime_plugin.TextCommand):

    def run(self, edit, **kwargs):
        if not kwargs:
            return

        if self.view.sel():
            sel = self.view.sel()[0]
            if not self.view.substr(
                sublime.Region(sel.begin() - 1, sel.begin())
            ).isspace():
                self.view.insert(edit, sel.begin(), ' ')

        self.view.run_command('insert_snippet', kwargs)
