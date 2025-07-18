DEFAULTS = {
    "label": "<span>\udb82\udd0c</span> {count}",
    "label_alt": "{count} notes",
    "container_padding": {"top": 0, "left": 0, "bottom": 0, "right": 0},
    "animation": {"enabled": True, "type": "fadeInOut", "duration": 200},
    "menu": {
        "blur": True,
        "round_corners": True,
        "round_corners_type": "normal",
        "border_color": "System",
        "alignment": "right",
        "direction": "down",
        "offset_top": 6,
        "offset_left": 0,
        "max_title_size": 150,
        "show_date_time": True,
    },
    "icons": {
        "note": "\udb82\udd0c",
        "delete": "\ueab8",
        "copy": "\uebcc",
    },
    "callbacks": {"on_left": "toggle_menu", "on_middle": "do_nothing", "on_right": "toggle_label"},
}

VALIDATION_SCHEMA = {
    "label": {"type": "string", "default": DEFAULTS["label"]},
    "label_alt": {"type": "string", "default": DEFAULTS["label_alt"]},
    "container_padding": {
        "type": "dict",
        "required": False,
        "schema": {
            "top": {"type": "integer", "default": DEFAULTS["container_padding"]["top"]},
            "left": {"type": "integer", "default": DEFAULTS["container_padding"]["left"]},
            "bottom": {"type": "integer", "default": DEFAULTS["container_padding"]["bottom"]},
            "right": {"type": "integer", "default": DEFAULTS["container_padding"]["right"]},
        },
        "default": DEFAULTS["container_padding"],
    },
    "animation": {
        "type": "dict",
        "required": False,
        "schema": {
            "enabled": {"type": "boolean", "default": DEFAULTS["animation"]["enabled"]},
            "type": {"type": "string", "default": DEFAULTS["animation"]["type"]},
            "duration": {"type": "integer", "default": DEFAULTS["animation"]["duration"]},
        },
        "default": DEFAULTS["animation"],
    },
    "menu": {
        "type": "dict",
        "required": False,
        "schema": {
            "blur": {"type": "boolean", "default": DEFAULTS["menu"]["blur"]},
            "round_corners": {"type": "boolean", "default": DEFAULTS["menu"]["round_corners"]},
            "round_corners_type": {
                "type": "string",
                "default": DEFAULTS["menu"]["round_corners_type"],
                "allowed": ["normal", "small"],
            },
            "border_color": {"type": "string", "default": DEFAULTS["menu"]["border_color"]},
            "alignment": {"type": "string", "default": DEFAULTS["menu"]["alignment"]},
            "direction": {"type": "string", "default": DEFAULTS["menu"]["direction"]},
            "offset_top": {"type": "integer", "default": DEFAULTS["menu"]["offset_top"]},
            "offset_left": {"type": "integer", "default": DEFAULTS["menu"]["offset_left"]},
            "max_title_size": {"type": "integer", "default": DEFAULTS["menu"]["max_title_size"]},
            "show_date_time": {"type": "boolean", "default": DEFAULTS["menu"]["show_date_time"]},
        },
        "default": DEFAULTS["menu"],
    },
    "icons": {
        "type": "dict",
        "required": False,
        "schema": {
            "note": {"type": "string", "default": DEFAULTS["icons"]["note"]},
            "delete": {"type": "string", "default": DEFAULTS["icons"]["delete"]},
            "copy": {"type": "string", "default": DEFAULTS["icons"]["copy"]},
        },
        "default": DEFAULTS["icons"],
    },
    "label_shadow": {
        "type": "dict",
        "required": False,
        "schema": {
            "enabled": {"type": "boolean", "default": False},
            "color": {"type": "string", "default": "black"},
            "offset": {"type": "list", "default": [1, 1]},
            "radius": {"type": "integer", "default": 3},
        },
        "default": {"enabled": False, "color": "black", "offset": [1, 1], "radius": 3},
    },
    "container_shadow": {
        "type": "dict",
        "required": False,
        "schema": {
            "enabled": {"type": "boolean", "default": False},
            "color": {"type": "string", "default": "black"},
            "offset": {"type": "list", "default": [1, 1]},
            "radius": {"type": "integer", "default": 3},
        },
        "default": {"enabled": False, "color": "black", "offset": [1, 1], "radius": 3},
    },
    "callbacks": {
        "type": "dict",
        "required": False,
        "schema": {
            "on_left": {"type": "string", "default": DEFAULTS["callbacks"]["on_left"]},
            "on_middle": {"type": "string", "default": DEFAULTS["callbacks"]["on_middle"]},
            "on_right": {"type": "string", "default": DEFAULTS["callbacks"]["on_right"]},
        },
        "default": DEFAULTS["callbacks"],
    },
}
