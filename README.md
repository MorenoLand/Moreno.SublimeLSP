# Moreno.SublimeLSP

LSP and syntax highlighting for GScript language used in Graal Online servers.

## Features

- **Syntax highlighting** for `.gs2`, `.gscript`, `.gscript2`, `.gs` files
- **Auto-completion** with function/variable suggestions
- **Hover documentation** showing function signatures, parameters, return types
- **Parameter hints** while typing
- **Wiki search** integration for API documentation
- **Type/scope badges** (FUNCTION, VARIABLE, GLOBAL, CLIENT, SERVER, USER)

## Installation

1. Download this repository
2. Copy to `Sublime Text\Data\Packages\Moreno.SublimeLSP`
3. Restart Sublime Text

## Usage

Open any GScript file - LSP activates automatically. Hover over functions for docs, start typing for completions.

## Settings

Configure in `SublimeRC.sublime-settings`:

- `popup_font_scale`: Scale font size in popups
- `popup_ui_scale`: Scale UI elements
- `popup_max_width`: Max popup width
- `wiki_search_engine`: Search engine for wiki links
