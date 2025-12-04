# Python Review – Indent/Syntax-Probleme

Kurzer Check per `python3 -m py_compile $(rg --files -g '*.py')` hat drei Fehler gemeldet:

- `hub/app_core.py` Zeile 371: `IndentationError: unexpected indent`. Im Bereich der Sidebar/Health-URL-Ermittlung sind `urls = []`, das `if slug == "metadatacreator":` und der Hilfsblock `_find_tool` falsch eingerückt – bitte an die Einrückung der umgebenden Funktion anpassen.
- `hub/app_core.raw.py` Zeile 139: `SyntaxError: invalid syntax`, weil die Beschreibung `Dünner Wrapper: ...` ohne Kommentar/Docstring im Code steht. Als Kommentar (`# ...`) oder Docstring einrücken.
- `hub/app_core.work.py` Zeile 696: `SyntaxError: invalid decimal literal`. Der Parser liest das Docstring `"""2xx-3xx = UP..."""` als Code; vermutlich fehlt eine schließende/öffnende Triple-Quote oder die Einrückung im Health-Override-Block ist verrutscht (Tokenize bricht zusätzlich bei Zeile 813 mit `unindent does not match any outer indentation level` ab). Block rund um `check_health_disabled`, `_check_health_v3` und `_check_health_v4` prüfen.

Nach Fixes erneut `python3 -m py_compile $(rg --files -g '*.py')` ausführen, um sicherzustellen, dass die Syntax wieder sauber ist.
