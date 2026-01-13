import sublime
import sublime_plugin
import json
import os
import threading
import re

try:
    from . import _lsp_players
    _has_player_completions = True
except ImportError:
    _has_player_completions = False

def get_package_name():
    """Get the package name dynamically from the current file location."""
    try:
        file_path = __file__
        packages_path = sublime.packages_path()
        installed_packages_path = os.path.join(os.path.dirname(packages_path), "Installed Packages")
        
        if packages_path in file_path:
            rel_path = os.path.relpath(file_path, packages_path)
            package_name = rel_path.split(os.sep)[0]
            return package_name
        elif installed_packages_path in file_path:
            rel_path = os.path.relpath(file_path, installed_packages_path)
            package_name = rel_path.split(os.sep)[0]
            if package_name.endswith('.sublime-package'):
                package_name = package_name[:-16]
            return package_name
    except:
        pass
    return "SublimeLSP"

def syntax_highlight_gscript(code):
    window = sublime.active_window()
    if not window:
        return code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    view = window.create_output_panel('gscript_syntax_temp', unlisted=True)
    package_name = get_package_name()
    view.set_syntax_file('Packages/{}/gscript.sublime-syntax'.format(package_name))
    view.run_command('append', {'characters': code})
    color_map = {
        'comment': '#6a9955',
        'string': '#ce9178',
        'constant.numeric': '#b5cea8',
        'constant.language': '#569cd6',
        'variable.parameter': '#4fc3f7',
        'variable.language': '#9cdcfe',
        'keyword.control': '#c586c0',
        'keyword.other': '#c586c0',
        'storage.modifier': '#c586c0',
        'storage.type': '#c586c0',
        'entity.name.function': '#dcdcaa',
        'keyword.operator': '#d4d4d4',
        'punctuation': '#d4d4d4',
    }

    def get_color_for_scope(scope):
        for scope_key in color_map:
            if scope_key in scope:
                return color_map[scope_key]
        return None

    result = []
    i = 0
    while i < len(code):
        scope = view.scope_name(i)
        color = get_color_for_scope(scope)
        j = i + 1
        while j < len(code) and view.scope_name(j) == scope:
            j += 1

        text = code[i:j].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        if color:
            result.append('<span style="color: {};">{}</span>'.format(color, text))
        else:
            result.append(text)

        i = j
    window.destroy_output_panel('gscript_syntax_temp')

    return ''.join(result)

class GScriptLspListener(sublime_plugin.ViewEventListener):
    api_definitions = None

    @classmethod
    def is_applicable(cls, settings):
        syntax = settings.get('syntax')
        return syntax and 'gscript.sublime-syntax' in syntax

    def __init__(self, view):
        super().__init__(view)
        self.document_functions = {}
        self.parse_timer = None
        self.parse_document_functions()

    def parse_document_functions(self):
        content = self.view.substr(sublime.Region(0, self.view.size()))
        self.document_functions = {}
        clientside_marker = content.find('//#CLIENTSIDE')
        pattern = r'(?:public\s+|private\s+)?function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(([^)]*)\)'
        for match in re.finditer(pattern, content):
            func_name = match.group(1)
            params_str = match.group(2).strip()
            params = [p.strip() for p in params_str.split(',') if p.strip()] if params_str else []
            func_scope = 'clientside' if clientside_marker != -1 and match.start() > clientside_marker else ('serverside' if clientside_marker != -1 else 'document')
            self.document_functions[func_name] = {'name': func_name, 'params': params, 'returns': 'void', 'description': 'User-defined function in current script', 'scope': func_scope, 'is_custom': True}

    @classmethod
    def load_api_definitions(cls):
        if cls.api_definitions is None:
            try:
                package_path = sublime.packages_path()
                package_name = get_package_name()
                json_path = os.path.join(package_path, package_name, "api_definitions.json")
                if not os.path.exists(json_path):
                    user_data_path = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Sublime Text", "Packages", package_name, "api_definitions.json")
                    if os.path.exists(user_data_path):
                        json_path = user_data_path
                with open(json_path, 'r', encoding='utf-8') as f:
                    cls.api_definitions = json.load(f)
                sublime.status_message("Loaded {} API definitions".format(len(cls.api_definitions)))
            except Exception:
                cls.api_definitions = {}
        return cls.api_definitions
    
    def on_query_completions(self, prefix, locations):
        if not self.view.match_selector(locations[0], "source.gscript"):
            return None
        point = locations[0]
        line_region = self.view.line(point)
        line_text = self.view.substr(line_region)
        line_start = line_region.begin()
        col = point - line_start

        in_string = False
        quote_char = None
        for i in range(col):
            if line_text[i] in ('"', "'") and (i == 0 or line_text[i-1] != '\\'):
                if quote_char is None:
                    quote_char = line_text[i]
                    in_string = True
                elif line_text[i] == quote_char:
                    quote_char = None
                    in_string = False

        if in_string and _has_player_completions:
            quote_start = col - 1
            while quote_start > 0 and line_text[quote_start] not in ('"', "'"):
                quote_start -= 1
            string_content = line_text[quote_start + 1:col]
            if '.' in string_content:
                pass
            else:
                start = col
                while start > 0 and (line_text[start - 1].isalnum() or line_text[start - 1] in '_'):
                    start -= 1
                prefix = line_text[start:col]
                player_completions = _lsp_players.get_player_completions(prefix)
                if player_completions:
                    return sublime.CompletionList(player_completions, flags=sublime.INHIBIT_WORD_COMPLETIONS | sublime.INHIBIT_EXPLICIT_COMPLETIONS)

        definitions = self.load_api_definitions()
        if not definitions:
            definitions = {}
        all_definitions = dict(self.document_functions)
        all_definitions.update(definitions)
        completions = []
        start = col
        while start > 0 and (line_text[start - 1].isalnum() or line_text[start - 1] in '$_:'):
            start -= 1
        expanded_prefix = line_text[start:col]
        if expanded_prefix:
            prefix = expanded_prefix
        prefix_lower = prefix.lower()
        max_results = 50 if len(prefix) < 2 else 200
        result_count = 0

        for name, info in all_definitions.items():
            if result_count >= max_results:
                break
            name_lower = name.lower()
            if name_lower.startswith(prefix_lower):
                result_count += 1
                params = info.get('params', [])
                returns = info.get('returns', 'void')
                description = info.get('description', '')
                example = info.get('example', '')
                scope = info.get('scope', '')
                is_custom = info.get('is_custom', False)
                item_type = info.get('type', '')
                is_variable = name.startswith('$')
                badges = []
                annotation = ""
                if is_custom or scope:
                    if scope == 'document' or is_custom:
                        annotation = 'USER'
                    elif scope == 'global':
                        annotation = 'GLOBAL'
                    elif 'client' in scope.lower():
                        annotation = 'CLIENTSIDE'
                    elif 'server' in scope.lower():
                        annotation = 'SERVERSIDE'
                    else:
                        annotation = 'UNDEFINED'
                if is_variable:
                    type_color, type_text = '#f44336', 'VAR'
                elif item_type:
                    type_color, type_text = '#9c27b0', 'FUNC'
                else:
                    type_color, type_text = '#81c784', 'UNDEFINED'
                details = ""
                if description:
                    details = description.replace('\n', ' ')[:100] + '...' if len(description) > 100 else description.replace('\n', ' ')
                if is_variable:
                    insert_text = name
                    kind = sublime.KIND_VARIABLE
                elif not params:
                    insert_text = "{}() {{".format(name)
                    kind = sublime.KIND_FUNCTION
                else:
                    insert_text = "{}()".format(name)
                    kind = sublime.KIND_FUNCTION
                completion_item = sublime.CompletionItem.snippet_completion(trigger=name, snippet=insert_text, annotation=annotation, kind=kind, details=details)
                completions.append(completion_item)
        return sublime.CompletionList(completions, flags=sublime.INHIBIT_WORD_COMPLETIONS)
    
    def on_hover(self, point, hover_zone):
        if hover_zone != sublime.HOVER_TEXT:
            return
        if not self.view.match_selector(point, "source.gscript"):
            return
        line_region = self.view.line(point)
        line_text = self.view.substr(line_region)
        line_start = line_region.begin()
        col = point - line_start
        func_param_pattern = r'function\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\(([^)]*)\)'
        func_match = re.search(func_param_pattern, line_text)
        if func_match:
            param_start = func_match.start(1)
            param_end = func_match.end(1)
            if param_start <= col <= param_end:
                return
        if '//#CLIENTSIDE' in line_text:
            html = "<div style='padding: 10px; font-family: system-ui, -apple-system, sans-serif;'><div style='font-family: \"Consolas\", \"Monaco\", monospace; font-size: 13px; color: #569cd6; margin-bottom: 8px;'><strong>//#CLIENTSIDE</strong></div><div style='font-size: 12px; line-height: 1.5; margin: 10px 0; padding-top: 8px; border-top: 1px solid rgba(128,128,128,0.2);'>Marks the divider between server-side and client-side code. Functions after this marker are executed on the client.</div></div>"
            self.view.show_popup(html, location=point, max_width=500, flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY)
            return
        start = col
        end = col
        while start > 0 and (line_text[start - 1].isalnum() or line_text[start - 1] in '_'):
            start -= 1
        while end < len(line_text) and (line_text[end].isalnum() or line_text[end] in '_'):
            end += 1
        word = line_text[start:end].strip()
        if _has_player_completions and word:
            player_info = _lsp_players.get_player_info(word)
            if player_info:
                badges_html = ''.join([
                    "<span style='background-color: {}; color: #fff; padding: 2px 8px; border-radius: 3px; font-size: 10px; font-weight: bold; margin-right: 4px;'>{}</span>".format(
                        '#4caf50' if badge == 'RC' else '#2196f3', badge
                    ) for badge in player_info['badges']
                ])
                html = """
                <div style='padding: 10px; font-family: system-ui, -apple-system, sans-serif;'>
                    <div style='margin-bottom: 8px;'>{badges}</div>
                    <div style='font-family: "Consolas", "Monaco", monospace; font-size: 13px; color: #569cd6; margin-bottom: 8px;'>
                        <strong>{account}</strong>
                    </div>
                    <div style='font-size: 12px; line-height: 1.8; margin: 10px 0; padding-top: 8px; border-top: 1px solid rgba(128,128,128,0.2);'>
                        <div><strong>Nickname:</strong> {nick}</div>
                        <div><strong>Level:</strong> {level}</div>
                        <div><strong>Player ID:</strong> {player_id}</div>
                    </div>
                </div>
                """.format(
                    badges=badges_html,
                    account=player_info['account'],
                    nick=player_info['nick'],
                    level=player_info['level'],
                    player_id=player_info['id']
                )
                self.view.show_popup(html, location=point, max_width=400, flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY)
                return
        definitions = self.load_api_definitions()
        if not definitions:
            definitions = {}
        all_definitions = dict(self.document_functions)
        all_definitions.update(definitions)
        line_region = self.view.line(point)
        line_text = self.view.substr(line_region)
        line_start = line_region.begin()
        col = point - line_start
        start = col
        end = col
        while start > 0 and (line_text[start - 1].isalnum() or line_text[start - 1] in '$_:'):
            start -= 1
        while end < len(line_text) and (line_text[end].isalnum() or line_text[end] in '_:'):
            end += 1
        word = line_text[start:end].strip()
        if not word:
            return
        if word not in all_definitions:
            return
        info = all_definitions[word]
        params = info.get('params', [])
        returns = info.get('returns', 'void')
        description = info.get('description', '')
        example = info.get('example', '')
        scope = info.get('scope', '')
        item_type = info.get('type', '')
        is_variable = word.startswith('$')
        if is_variable:
            signature = word
        elif params:
            param_str = ', '.join(params)
            signature = "{}({})".format(word, param_str)
        else:
            signature = "{}()".format(word)
        html = """
        <div style='padding: 10px; font-family: system-ui, -apple-system, sans-serif;'>
            <div style='font-family: "Consolas", "Monaco", monospace; font-size: 13px; color: #569cd6; margin-bottom: 8px;'>
                <strong>{signature}</strong>
            </div>
        """.format(signature=signature)
        if returns and returns != 'void':
            html += "<div style='font-size: 11px; color: #888; margin-bottom: 8px;'>"
            html += "Returns: <code style='background: rgba(128,128,128,0.15); padding: 2px 6px; border-radius: 3px; color: #4ec9b0;'>{}</code>".format(returns)
            html += "</div>"
        badges = []
        if scope:
            if scope == 'document':
                scope_color, scope_text = '#ff9800', 'USER'
            elif scope == 'global':
                scope_color, scope_text = '#607d8b', 'GLOBAL'
            elif 'client' in scope.lower():
                scope_color, scope_text = '#4fc3f7', 'CLIENT'
            elif 'server' in scope.lower():
                scope_color, scope_text = '#81c784', 'SERVER'
            else:
                scope_color, scope_text = '#81c784', 'UNDEFINED'
            badges.append("<span style='background-color: {}; color: #fff; padding: 2px 8px; border-radius: 3px; font-size: 10px; font-weight: bold; margin-right: 6px;'>{}</span>".format(scope_color, scope_text))
        if is_variable:
            type_color, type_text = '#f44336', 'VARIABLE'
        elif item_type:
            type_color, type_text = '#9c27b0', 'FUNCTION'
        else:
            type_color, type_text = '#81c784', 'UNDEFINED'
        badges.append("<span style='background-color: {}; color: #fff; padding: 2px 8px; border-radius: 3px; font-size: 10px; font-weight: bold;'>{}</span>".format(type_color, type_text))
        if badges:
            html += "<div style='margin-bottom: 8px;'>{}</div>".format(''.join(badges))
        if description and description != "No matching script function found!":
            html += "<div style='font-size: 12px; line-height: 1.5; margin: 10px 0; padding-top: 8px; border-top: 1px solid rgba(128,128,128,0.2);'>"
            html += "{}".format(description.replace('\n', '<br>'))
            html += "</div>"
        html += "<div style='margin-top: 10px; padding-top: 8px; border-top: 1px solid rgba(128,128,128,0.2);'>"
        html += "<div style='font-size: 11px; color: #888; margin-bottom: 4px;'>Example:</div>"
        if example:
            html += "<pre style='background: rgba(128,128,128,0.1); padding: 8px; border-radius: 4px; margin: 0; font-family: \"Consolas\", \"Monaco\", monospace; font-size: 12px; overflow-x: auto; white-space: pre-wrap;'>{}</pre>".format(syntax_highlight_gscript(example.strip()))
        else:
            html += "<div style='color: #888; font-style: italic; font-size: 11px;'>(no example)</div>"
        html += "</div>"
        html += "</div>"
        self.view.hide_popup()
        def show():
            self.view.hide_popup()
            self.view.show_popup(
                html,
                flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY | sublime.COOPERATE_WITH_AUTO_COMPLETE,
                location=point,
                max_width=600
            )
        sublime.set_timeout(show, 10)
        return True

    def show_param_hint(self):
        if not self.view.match_selector(self.view.sel()[0].begin(), "source.gscript"):
            return
        definitions = self.load_api_definitions()
        if not definitions:
            definitions = {}
        all_definitions = dict(self.document_functions)
        all_definitions.update(definitions)
        point = self.view.sel()[0].begin()
        line_region = self.view.line(point)
        line_text = self.view.substr(line_region)
        line_start = line_region.begin()
        col = point - line_start
        if col > 0:
            paren_pos = line_text.rfind('(', 0, col)
            if paren_pos != -1:
                close_pos = line_text.find(')', paren_pos)
                if close_pos == -1 or close_pos >= col:
                    start = paren_pos - 1
                    while start >= 0 and (line_text[start].isalnum() or line_text[start] == '_'):
                        start -= 1
                    start += 1
                    func_name = line_text[start:paren_pos].strip()
                    if func_name and func_name in all_definitions:
                        info = all_definitions[func_name]
                        params = info.get('params', [])
                        returns = info.get('returns', 'void')
                        description = info.get('description', '')
                        example = info.get('example', '')
                        scope = info.get('scope', '')
                        if params:
                            param_text = line_text[paren_pos + 1:col]
                            comma_count = param_text.count(',')
                            current_param = comma_count if comma_count < len(params) else len(params) - 1
                            param_list = []
                            for i, param in enumerate(params):
                                if i == current_param:
                                    param_list.append("<strong style='color: #ffd700; text-decoration: underline;'>{}</strong>".format(param))
                                else:
                                    param_list.append("<span style='color: #4ec9b0;'>{}</span>".format(param))
                            param_str = ', '.join(param_list)
                            hint = """
                            <div style='padding: 8px; font-family: system-ui, -apple-system, sans-serif; background: #1e1e1e;'>
                                <div style='font-family: "Consolas", "Monaco", monospace; font-size: 13px; margin-bottom: 6px;'>
                                    <span style='color: #569cd6;'>{}</span><span style='color: #dcdcdc;'>(</span>{}<span style='color: #dcdcdc;'>)</span>
                                </div>
                            """.format(func_name, param_str)
                            if scope:
                                if scope == 'document':
                                    scope_color = '#ff9800'
                                    scope_text = 'USER'
                                elif scope == 'global':
                                    scope_color = '#607d8b'
                                    scope_text = 'GLOBAL'
                                elif 'client' in scope.lower():
                                    scope_color = '#4fc3f7'
                                    scope_text = 'CLIENT'
                                elif 'server' in scope.lower():
                                    scope_color = '#81c784'
                                    scope_text = 'SERVER'
                                else:
                                    scope_color = '#81c784'
                                    scope_text = 'UNDEFINED'
                                hint += "<div style='margin-bottom: 6px;'>"
                                hint += "<span style='background: {}; color: #fff; padding: 2px 6px; border-radius: 3px; font-size: 9px; font-weight: bold;'>{}</span>".format(scope_color, scope_text)
                                hint += "</div>"
                            hint += """
                                <div style='font-size: 11px; color: #888; margin-bottom: 4px;'>
                                    Parameter {}/{} • Returns: <span style='color: #4ec9b0;'>{}</span>
                                </div>
                            """.format(current_param + 1, len(params), returns)
                            if description and description != "No matching script function found!":
                                short_desc = description[:100] + '...' if len(description) > 100 else description
                                hint += "<div style='font-size: 11px; color: #aaa; padding-top: 6px; border-top: 1px solid #333;'>{}</div>".format(short_desc)
                            hint += "<div style='margin-top: 6px; padding-top: 6px; border-top: 1px solid #333;'>"
                            hint += "<div style='font-size: 10px; color: #666; margin-bottom: 3px;'>Example:</div>"
                            if example:
                                hint += "<pre style='background: rgba(0,0,0,0.3); padding: 6px; border-radius: 3px; margin: 0; font-family: \"Consolas\", \"Monaco\", monospace; font-size: 11px; white-space: pre-wrap;'>{}</pre>".format(syntax_highlight_gscript(example.strip()))
                            else:
                                hint += "<div style='color: #666; font-style: italic; font-size: 10px;'>(no example)</div>"
                            hint += "</div>"
                            hint += "</div>"
                            self.view.show_popup(hint, sublime.HIDE_ON_MOUSE_MOVE_AWAY | sublime.COOPERATE_WITH_AUTO_COMPLETE, location=point, max_width=600)
                            return
        self.view.hide_popup()

    def on_post_save_async(self):
        self.parse_document_functions()

    def schedule_parse(self):
        if self.parse_timer:
            try:
                sublime.cancel_timeout(self.parse_timer)
            except:
                pass
        self.parse_timer = sublime.set_timeout(lambda: self.parse_document_functions(), 1000)

    def on_modified_async(self):
        self.schedule_parse()
        self.show_param_hint()

    def on_selection_modified_async(self):
        self.show_param_hint()
    
    def on_load(self):
        self.load_api_definitions()

class RcUpdateLspDefinitionsCommand(sublime_plugin.WindowCommand):
    def run(self):
        print("[LSP UPDATE] Starting LSP definitions update...")
        sublime.status_message("Downloading LSP definitions...")
        threading.Thread(target=self.download_definitions).start()

    def download_definitions(self):
        try:
            import urllib.request
            url = "https://api.gscript.dev"
            response = urllib.request.urlopen(url, timeout=30)
            data = response.read()
            print("[LSP UPDATE] Downloaded {} bytes".format(len(data)))
            package_path = sublime.packages_path()
            package_name = get_package_name()
            package_dir = os.path.join(package_path, package_name)
            try:
                os.makedirs(package_dir, exist_ok=True)
                test_file = os.path.join(package_dir, ".test_write")
                with open(test_file, 'w') as f:
                    f.write("test")
                os.remove(test_file)
            except (OSError, PermissionError):
                user_data_path = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Sublime Text", "Packages", package_name)
                try:
                    os.makedirs(user_data_path, exist_ok=True)
                    package_dir = user_data_path
                except (OSError, PermissionError):
                    def error_popup():
                        sublime.error_message("Failed to update LSP definitions: Permission denied. Please run Sublime Text as administrator or check folder permissions.")
                    sublime.set_timeout(error_popup, 0)
                    return
            json_path = os.path.join(package_dir, "api_definitions.json")
            print("[LSP UPDATE] Saving to: {}".format(json_path))
            with open(json_path, 'wb') as f:
                f.write(data)
            GScriptLspListener.api_definitions = None
            GScriptLspListener.load_api_definitions()
            def success_msg():
                sublime.status_message("LSP definitions updated successfully! {} definitions loaded".format(len(GScriptLspListener.api_definitions)))
            sublime.set_timeout(success_msg, 0)
        except Exception as e:
            error_msg = str(e)
            print("[LSP UPDATE] Error: {}".format(error_msg))
            import traceback
            traceback.print_exc()
            def error_popup():
                sublime.error_message("Failed to update LSP definitions: {}".format(error_msg))
            sublime.set_timeout(error_popup, 0)

def plugin_loaded():
    GScriptLspListener.load_api_definitions()

