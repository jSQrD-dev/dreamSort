import os
import re
import sys
import shutil
import zipfile
import json
import customtkinter as ctk
import tkinter as tk  # Imported for context menu
from tkinter import filedialog, messagebox, ttk
from tkinterdnd2 import DND_FILES, TkinterDnD
import traceback
import threading
from queue import Queue
import subprocess
import platform  # Imported for OS-specific checks

try:
    import py7zr

    PY7ZR_SUPPORT = True
except ImportError:
    PY7ZR_SUPPORT = False

VERSION = "v6.2.4"  # Incremented version


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def is_process_running(process_name):
    """Check if there is any running process that contains the given name."""
    system = platform.system()
    try:
        if system == "Windows":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            command = ["tasklist", "/FI", f"IMAGENAME eq {process_name}.exe"]
            output = subprocess.check_output(
                command, startupinfo=startupinfo, stderr=subprocess.STDOUT
            )
            return process_name.lower() in output.decode(errors="ignore").lower()
        else:  # Linux and macOS
            command = ["pgrep", "-f", process_name]
            output = subprocess.check_output(command, stderr=subprocess.STDOUT)
            return output.strip() != b""
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


class Colors:
    BG = "#2b2b2b"
    TEXT = "#ffebcd"
    WIDGET_BG = "#3c3c3c"
    FRAME_BG = "#2b2b2b"
    BUTTON_BG = "#4c4c4c"
    BUTTON_HOVER = "#636363"
    BUTTON_BORDER = "#ffebcd"
    HEADER_BG = "#ffebcd"
    HEADER_TEXT = "#000000"
    HIGHLIGHT_BG = "#636363"
    TREE_HEADING_BG = "#4c4c4c"
    CONFLICT = "#FF7D7D"
    RESOLVED_CONFLICT = "#3EFF65"
    NO_CONFLICT = "#d5d0ff"
    CHEAT_MOD = "#FFA500"
    CAUTION_CONFLICT = "#FFA500"
    DISABLED = "#808080"
    DRAG_HIGHLIGHT = "#FFD700"
    PROGRESS_OVERLAY = ("#000000", "#000000")  # Dark overlay color


class DreamSort:
    CHEAT_BUILD_ID_PREFIX = "FB08F1D20FD1204F-"

    def __init__(self):
        self.mods_path = ""
        self.mods_json_path = None
        self.mod_files = {}
        self.conflicts = {}
        self.load_order = []
        self.cheat_only_mods = set()
        self.special_cheats_folder_name = None

    def set_mods_path(self, path):
        """Sets the mod content path and attempts to derive the mods.json path."""
        if not os.path.isdir(path):
            return False

        self.mods_path = os.path.normpath(path)
        self.mods_json_path = None  # Reset on new path

        try:
            norm_path = os.path.normpath(self.mods_path)
            parts = norm_path.split(os.sep)

            if (
                len(parts) >= 3
                and parts[-2].lower() == "contents"
                and parts[-3].lower() == "mods"
            ):
                game_id = parts[-1]
                ryujinx_root_path = os.sep.join(parts[:-3])
                json_path = os.path.join(
                    ryujinx_root_path, "games", game_id, "mods.json"
                )
                self.mods_json_path = json_path
                print(
                    f"Found Ryujinx structure. Set mods.json path to: {self.mods_json_path}"
                )
            else:
                print(
                    "Warning: Selected path does not match standard Ryujinx structure. mods.json will not be updated."
                )
        except Exception as e:
            print(f"Could not determine mods.json path: {e}")
            self.mods_json_path = None

        return True

    def get_current_load_order(self):
        if not self.mods_path:
            return []
        try:
            dirs = [
                d
                for d in os.listdir(self.mods_path)
                if os.path.isdir(os.path.join(self.mods_path, d))
            ]
            dirs.sort(
                key=lambda x: [
                    int(c) if c.isdigit() else c for c in re.split("([0-9]+)", x)
                ]
            )
            return dirs
        except FileNotFoundError:
            return []

    @staticmethod
    def strip_prefix(name):
        match = re.match(r"^(?:\d+_)|(?:[.!~]+_?)", name)
        return name[match.end() :] if match else name

    def scan_and_analyze(self):
        if not self.mods_path:
            return
        self.load_order = self.get_current_load_order()
        file_to_mods_map = {}
        self.mod_files = {}
        self.cheat_only_mods.clear()
        self.special_cheats_folder_name = None

        for mod_name in self.load_order:
            if self.strip_prefix(mod_name).lower() == "cheats":
                self.special_cheats_folder_name = mod_name
                break

        for mod_name in self.load_order:
            if mod_name == self.special_cheats_folder_name:
                continue

            mod_path = os.path.join(self.mods_path, mod_name)
            self.mod_files[mod_name] = set()
            try:
                top_level_contents = os.listdir(mod_path)
                top_level_contents_lower = [d.lower() for d in top_level_contents]
                if (
                    "cheats" in top_level_contents_lower
                    and "romfs" not in top_level_contents_lower
                ):
                    self.cheat_only_mods.add(mod_name)
            except OSError:
                continue

            for root, dirs, files in os.walk(mod_path):
                dirs[:] = [d for d in dirs if d.lower() != "cheats"]
                for file in files:
                    relative_path = os.path.relpath(
                        os.path.join(root, file), mod_path
                    ).replace("\\", "/")
                    self.mod_files[mod_name].add(relative_path)
                    if relative_path not in file_to_mods_map:
                        file_to_mods_map[relative_path] = []
                    file_to_mods_map[relative_path].append(mod_name)

        self.conflicts = {}
        for file_path, mods in file_to_mods_map.items():
            if len(mods) > 1:
                for mod_name in mods:
                    if mod_name in self.cheat_only_mods:
                        continue
                    if mod_name not in self.conflicts:
                        self.conflicts[mod_name] = {}
                    self.conflicts[mod_name][file_path] = [
                        m for m in mods if m != mod_name
                    ]

    def _update_ryujinx_mods_json(self, final_mod_list, progress_queue):
        if not self.mods_json_path:
            progress_queue.put(
                {"type": "status", "text": "Skipping mods.json (path not found)."}
            )
            return

        progress_queue.put(
            {"type": "status", "text": "Phase 3: Updating Ryujinx mods.json..."}
        )
        progress_queue.put(
            {
                "type": "progress",
                "value": 0.95,
                "text": f"Writing to {os.path.basename(self.mods_json_path)}",
            }
        )

        mod_entries = []
        for mod_config in final_mod_list:
            final_name = mod_config["name"]
            is_enabled = mod_config["enabled"]
            full_path = os.path.abspath(os.path.join(self.mods_path, final_name))

            mod_entries.append(
                {"name": final_name, "path": full_path, "enabled": is_enabled}
            )

        json_data = {"mods": mod_entries}

        try:
            json_dir = os.path.dirname(self.mods_json_path)
            os.makedirs(json_dir, exist_ok=True)
            with open(self.mods_json_path, "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=2)
        except Exception as e:
            error_msg = f"Could not write to mods.json file.\n\nPath: {self.mods_json_path}\nError: {e}"
            progress_queue.put({"type": "error", "message": error_msg})
            return

    def _apply_cheat_selections_threaded(self, pending_cheats, progress_queue):
        special_cheats_folder = (
            self.special_cheats_folder_name
            if self.special_cheats_folder_name
            else "cheats"
        )
        enabled_path = os.path.join(
            self.mods_path, special_cheats_folder, "enabled.txt"
        )

        try:
            os.makedirs(os.path.dirname(enabled_path), exist_ok=True)

            if not pending_cheats:
                open(enabled_path, "w").close()
                progress_queue.put(
                    {
                        "type": "status",
                        "text": "No cheats selected, cleared enabled.txt.",
                    }
                )
                return

            progress_queue.put(
                {"type": "status", "text": "Phase 4: Applying Cheat Selections..."}
            )

            all_enabled_cheats = set()
            for mod_name, cheat_states in pending_cheats.items():
                enabled_cheats = {
                    cheat_name
                    for cheat_name, is_enabled in cheat_states.items()
                    if is_enabled
                }
                all_enabled_cheats.update(enabled_cheats)

            sorted_cheats = sorted(list(all_enabled_cheats))

            with open(enabled_path, "w", encoding="utf-8") as f:
                if sorted_cheats:
                    for cheat_name in sorted_cheats:
                        f.write(f"{self.CHEAT_BUILD_ID_PREFIX}<{cheat_name} Cheat>\n")

            if sorted_cheats:
                progress_queue.put(
                    {
                        "type": "status",
                        "text": f"Written {len(sorted_cheats)} cheats to enabled.txt",
                    }
                )
            else:
                progress_queue.put(
                    {
                        "type": "status",
                        "text": "No cheats enabled - created empty enabled.txt",
                    }
                )

        except Exception as e:
            error_msg = f"Could not write cheats to enabled.txt.\n\nPath: {enabled_path}\nError: {e}"
            progress_queue.put({"type": "error", "message": error_msg})
            return

    def apply_new_order_threaded(
        self, ordered_mods_config, pending_cheats, progress_queue
    ):
        if not self.mods_path:
            progress_queue.put({"type": "error", "message": "Mods path not set."})
            return

        temp_map = {}
        final_mod_list = []
        current_mods = []
        try:
            current_mods = [
                d
                for d in os.listdir(self.mods_path)
                if os.path.isdir(os.path.join(self.mods_path, d))
            ]
        except Exception as e:
            progress_queue.put(
                {"type": "error", "message": f"Failed to list mod directories: {e}"}
            )
            return

        total_ops = len(current_mods) + len(ordered_mods_config)
        ops_done = 0

        progress_queue.put(
            {"type": "status", "text": "Phase 1: Backing up current mods..."}
        )
        for mod_name in current_mods:
            try:
                clean_name = self.strip_prefix(mod_name)
                temp_name = f"{clean_name}__temp_rename__"
                progress_queue.put(
                    {
                        "type": "progress",
                        "value": ops_done / total_ops,
                        "text": f"Backing up: '{mod_name}'",
                    }
                )
                shutil.move(
                    os.path.join(self.mods_path, mod_name),
                    os.path.join(self.mods_path, temp_name),
                )
                temp_map[clean_name] = temp_name
                ops_done += 1
            except PermissionError:
                error_msg = (
                    f"Permission denied while renaming '{mod_name}'. "
                    "Please close Ryujinx and try again. If the issue persists, "
                    "try running dreamSort Mod Manager as an administrator."
                )
                progress_queue.put({"type": "error", "message": error_msg})
                return
            except Exception as e:
                error_msg = f"Could not rename mod '{mod_name}' to a temporary state (Phase 1). The process has been halted.\n\nError: {e}"
                progress_queue.put({"type": "error", "message": error_msg})
                return

        try:
            progress_queue.put(
                {"type": "status", "text": "Phase 2: Applying new load order..."}
            )
            if self.special_cheats_folder_name:
                clean_name = self.strip_prefix(self.special_cheats_folder_name)
                temp_name_for_cheats = temp_map.pop(clean_name, None)
                if temp_name_for_cheats:
                    final_name = self.special_cheats_folder_name
                    shutil.move(
                        os.path.join(self.mods_path, temp_name_for_cheats),
                        os.path.join(self.mods_path, final_name),
                    )

            enabled_romfs_index = 0
            for mod_name, is_enabled in ordered_mods_config.items():
                if mod_name == self.special_cheats_folder_name:
                    continue

                clean_name = self.strip_prefix(mod_name)
                temp_name = temp_map.get(clean_name)
                if not temp_name:
                    continue

                final_name = ""
                final_enabled_status = False
                if mod_name in self.cheat_only_mods or not is_enabled:
                    final_name = f"~{clean_name}"
                    final_enabled_status = False
                else:
                    enabled_romfs_index += 1
                    final_name = f"{enabled_romfs_index:02d}_{clean_name}"
                    final_enabled_status = True

                progress_queue.put(
                    {
                        "type": "progress",
                        "value": ops_done / total_ops,
                        "text": f"Writing: '{final_name}'",
                    }
                )
                shutil.move(
                    os.path.join(self.mods_path, temp_name),
                    os.path.join(self.mods_path, final_name),
                )
                final_mod_list.append(
                    {"name": final_name, "enabled": final_enabled_status}
                )
                ops_done += 1
        except PermissionError as e:
            error_msg = (
                f"Permission denied while applying new order. Your mods may be in a temporary state (ending with '__temp_rename__').\n\n"
                "Please close Ryujinx, restart dreamSort, and try again. If that fails, manually remove the suffix from your mod folders.\n\n"
                f"Error: {e}"
            )
            progress_queue.put({"type": "error", "message": error_msg})
            return
        except Exception as e:
            error_msg = f"Could not apply new order (Phase 2). Your mods are in a temporary state (ending with '__temp_rename__'). Please rename them manually.\n\nError: {e}"
            progress_queue.put({"type": "error", "message": error_msg})
            return

        self._update_ryujinx_mods_json(final_mod_list, progress_queue)

        self._apply_cheat_selections_threaded(pending_cheats, progress_queue)
        progress_queue.put({"type": "done"})


class DreamSortApp(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)

        self.analyzer = DreamSort()
        self.mod_item_widgets = {}
        self.drag_data = {"item": None, "y": 0}
        self.apply_thread = None
        self.progress_queue = Queue()
        self.current_state = "idle"
        self.pending_cheat_selections = {}
        self.current_details_mod = None
        self.real_mods_path = ""
        self.ryujinx_exe_path = ""
        self.game_file_path = ""
        self.load_config()

        # <<< PERFORMANCE FIX: Variables for debouncing resize >>>
        self._after_id = None
        self._is_resizing = False

        self.configure(fg_color=Colors.BG)
        ctk.set_appearance_mode("Dark")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.main_content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_content_frame.grid(row=0, column=0, rowspan=3, sticky="nsew")
        self.main_content_frame.grid_columnconfigure(0, weight=1)
        self.main_content_frame.grid_rowconfigure(1, weight=1)

        self.top_frame = ctk.CTkFrame(self.main_content_frame, fg_color="transparent")
        self.top_frame.grid(
            row=0, column=0, columnspan=2, padx=10, pady=10, sticky="ew"
        )
        self.top_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.top_frame, text="Mod Folder:", text_color=Colors.TEXT).grid(
            row=0, column=0, padx=(0, 5)
        )
        self.path_entry = ctk.CTkEntry(
            self.top_frame,
            placeholder_text="Select your game's mod directory...",
            text_color=Colors.TEXT,
            fg_color=Colors.WIDGET_BG,
        )
        self.path_entry.grid(row=0, column=1, sticky="ew")

        try:
            if os.name == "nt":  # Windows
                default_path_str = (
                    "~/AppData/Roaming/Ryujinx/mods/contents/0100770008dd8000/"
                )
            else:  # Linux/Unix/MacOS
                default_path_str = "~/.config/Ryujinx/mods/contents/0100770008dd8000/"
            expanded_path = os.path.expanduser(default_path_str)
            self._update_path_display(expanded_path)
        except Exception:
            pass

        self.browse_btn = ctk.CTkButton(
            self.top_frame,
            text="...",
            width=40,
            command=self.select_folder,
            fg_color=Colors.BUTTON_BG,
            hover_color=Colors.BUTTON_HOVER,
            text_color=Colors.TEXT,
            border_color=Colors.BUTTON_BORDER,
            border_width=1,
        )
        self.browse_btn.grid(row=0, column=2, padx=5)
        self.scan_btn = ctk.CTkButton(
            self.top_frame,
            text="Scan/Refresh",
            command=self.run_scan,
            fg_color=Colors.BUTTON_BG,
            hover_color=Colors.BUTTON_HOVER,
            text_color=Colors.TEXT,
            border_color=Colors.BUTTON_BORDER,
            border_width=1,
        )
        self.scan_btn.grid(row=0, column=3, padx=5)
        self.open_dir_btn = ctk.CTkButton(
            self.top_frame,
            text="Open Directory",
            command=self.open_mod_directory,
            fg_color=Colors.BUTTON_BG,
            hover_color=Colors.BUTTON_HOVER,
            text_color=Colors.TEXT,
            border_color=Colors.BUTTON_BORDER,
            border_width=1,
        )
        self.open_dir_btn.grid(row=0, column=4, padx=5)
        self.preview_cheats_btn = ctk.CTkButton(
            self.top_frame,
            text="Preview enabled.txt",
            command=self.preview_enabled_cheats_popup,
            fg_color=Colors.BUTTON_BG,
            hover_color=Colors.BUTTON_HOVER,
            text_color=Colors.TEXT,
            border_color=Colors.BUTTON_BORDER,
            border_width=1,
        )
        self.preview_cheats_btn.grid(row=0, column=5, padx=5)

        self.clear_mods_btn = ctk.CTkButton(
            self.top_frame,
            text="Disable All Mods",
            command=self.clear_all_mods,
            fg_color=Colors.BUTTON_BG,
            hover_color=Colors.BUTTON_HOVER,
            text_color=Colors.TEXT,
            border_color=Colors.BUTTON_BORDER,
            border_width=1,
        )
        self.clear_mods_btn.grid(row=0, column=6, padx=5)
        self.clear_cheats_btn = ctk.CTkButton(
            self.top_frame,
            text="Disable All Cheats",
            command=self.clear_all_cheats,
            fg_color=Colors.BUTTON_BG,
            hover_color=Colors.BUTTON_HOVER,
            text_color=Colors.TEXT,
            border_color=Colors.BUTTON_BORDER,
            border_width=1,
        )
        self.clear_cheats_btn.grid(row=0, column=7, padx=5)
        self.launch_game_btn = ctk.CTkButton(
            self.top_frame,
            text="Launch MHGU",
            command=self.launch_game,
            fg_color="#00ffdd",
            hover_color="#3acdc3",
            text_color="#000000",
            border_color=Colors.BUTTON_BORDER,
            border_width=1,
        )
        self.launch_game_btn.grid(row=0, column=8, padx=5)

        style = ttk.Style()
        style.configure("TPanedwindow", background=Colors.BG)
        style.configure(
            "TPanedwindow.Sash",
            background=Colors.BUTTON_BG,
            bordercolor=Colors.BG,
            relief="flat",
            sashthickness=6,
        )
        style.map("TPanedwindow.Sash", background=[("active", Colors.BUTTON_HOVER)])

        self.paned_window = ttk.PanedWindow(
            self.main_content_frame, orient="horizontal"
        )
        self.paned_window.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 5))

        self.list_panel = ctk.CTkFrame(self.paned_window, fg_color=Colors.FRAME_BG)
        self.list_panel.grid_rowconfigure(3, weight=1)
        self.list_panel.grid_columnconfigure(0, weight=1)
        self.paned_window.add(self.list_panel, weight=1)

        self.list_panel.drop_target_register(DND_FILES)
        self.list_panel.dnd_bind("<<Drop>>", self.on_drop)

        ctk.CTkLabel(
            self.list_panel,
            text="Mod Load Order (Drag files here to install)",
            text_color=Colors.HEADER_TEXT,
            fg_color=Colors.HEADER_BG,
            corner_radius=5,
        ).grid(row=0, column=0, sticky="ew", padx=2, pady=2)

        self.view_switcher = ctk.CTkSegmentedButton(
            self.list_panel,
            values=["List View", "Tree View"],
            command=self.switch_view,
            fg_color=Colors.WIDGET_BG,
            selected_color=Colors.BUTTON_BG,
            selected_hover_color=Colors.BUTTON_HOVER,
            unselected_color=Colors.WIDGET_BG,
            unselected_hover_color=Colors.BUTTON_HOVER,
            text_color=Colors.TEXT,
        )
        self.view_switcher.set("List View")
        self.view_switcher.grid(row=1, column=0, sticky="ew", padx=5, pady=5)

        self.legend_frame = ctk.CTkFrame(self.list_panel, fg_color="transparent")
        self.legend_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=(0, 5))
        self.legend_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        def create_legend_item(parent, color, text):
            item_frame = ctk.CTkFrame(parent, fg_color="transparent")
            color_box = ctk.CTkFrame(
                item_frame,
                fg_color=color,
                width=15,
                height=15,
                corner_radius=4,
                border_width=1,
                border_color=Colors.TEXT,
            )
            color_box.pack(side="left", padx=(0, 5))
            label = ctk.CTkLabel(
                item_frame, text=text, text_color=Colors.TEXT, font=("", 11)
            )
            label.pack(side="left", anchor="w")
            return item_frame

        legend_items = [
            (Colors.RESOLVED_CONFLICT, "Overrides other mods"),
            (Colors.CONFLICT, "Is overridden by others"),
            (Colors.NO_CONFLICT, "No conflicts"),
            (Colors.DISABLED, "Disabled"),
        ]
        for i, (color, text) in enumerate(legend_items):
            item = create_legend_item(self.legend_frame, color, text)
            item.grid(row=0, column=i, sticky="w", padx=5)

        self.view_container = ctk.CTkFrame(self.list_panel, fg_color="transparent")
        self.view_container.grid(row=3, column=0, sticky="nsew")
        self.view_container.grid_rowconfigure(0, weight=1)
        self.view_container.grid_columnconfigure(0, weight=1)

        self.mod_list_frame = ctk.CTkScrollableFrame(
            self.view_container, label_text="", fg_color="transparent"
        )
        self.tree_frame = ctk.CTkFrame(self.view_container, fg_color="transparent")

        self.setup_treeview(style)
        self.mod_list_frame.grid(row=0, column=0, sticky="nsew")

        self.details_frame = ctk.CTkFrame(self.paned_window, fg_color=Colors.FRAME_BG)
        self.details_frame.grid_rowconfigure(1, weight=1)
        self.details_frame.grid_columnconfigure(0, weight=1)
        self.paned_window.add(self.details_frame, weight=1)

        ctk.CTkLabel(
            self.details_frame,
            text="Details / Actions",
            text_color=Colors.HEADER_TEXT,
            fg_color=Colors.HEADER_BG,
            corner_radius=5,
        ).grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        self.details_content_frame = ctk.CTkFrame(
            self.details_frame, fg_color="transparent"
        )
        self.details_content_frame.grid(row=1, column=0, sticky="nsew", padx=2, pady=2)
        self.details_content_frame.grid_rowconfigure(0, weight=1)
        self.details_content_frame.grid_columnconfigure(0, weight=1)

        bottom_frame = ctk.CTkFrame(self.main_content_frame, fg_color="transparent")
        bottom_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=10, sticky="ew")

        self.apply_btn = ctk.CTkButton(
            bottom_frame,
            text="Apply New Order",
            command=self.apply_changes,
            fg_color=Colors.BUTTON_BG,
            hover_color=Colors.BUTTON_HOVER,
            text_color=Colors.TEXT,
            border_color=Colors.BUTTON_BORDER,
            border_width=1,
        )
        self.apply_btn.pack(side="right")

        self.status_label = ctk.CTkLabel(
            bottom_frame,
            text="Ready. Select a folder and click Scan.",
            text_color=Colors.TEXT,
            anchor="w",
        )
        self.status_label.pack(side="left", fill="x", expand=True, padx=5)

        self.progress_overlay = ctk.CTkFrame(
            self, fg_color=Colors.PROGRESS_OVERLAY, corner_radius=0
        )
        self.progress_overlay.grid_columnconfigure(0, weight=1)
        self.progress_overlay.grid_rowconfigure(1, weight=1)

        progress_content_frame = ctk.CTkFrame(
            self.progress_overlay, fg_color=Colors.FRAME_BG
        )
        progress_content_frame.grid(row=1, column=0, padx=50, pady=200, sticky="ew")
        progress_content_frame.grid_columnconfigure(0, weight=1)

        self.progress_header_label = ctk.CTkLabel(
            progress_content_frame,
            text="Applying New Mod Order...",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=Colors.TEXT,
        )
        self.progress_header_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.progress_bar = ctk.CTkProgressBar(
            progress_content_frame,
            fg_color=Colors.WIDGET_BG,
            progress_color=Colors.RESOLVED_CONFLICT,
        )
        self.progress_bar.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        self.progress_bar.set(0)

        self.progress_detail_label = ctk.CTkLabel(
            progress_content_frame,
            text="Initializing...",
            text_color=Colors.TEXT,
            anchor="w",
        )
        self.progress_detail_label.grid(
            row=2, column=0, padx=20, pady=(0, 20), sticky="ew"
        )

        self.set_ui_state("idle")
        self.after(100, self.set_initial_sash_pos)

        self.bind("<Configure>", self.on_resize)

    # <<< PERFORMANCE FIX: New resize handling logic >>>
    def on_resize(self, event=None):
        if not self._is_resizing:
            self.on_resize_start()
        if self._after_id:
            self.after_cancel(self._after_id)
        self._after_id = self.after(250, self.on_resize_end)

    def on_resize_start(self):
        self._is_resizing = True
        if self.view_switcher.get() == "List View":
            self.mod_list_frame.grid_remove()
        else:
            self.tree_frame.grid_remove()

    def on_resize_end(self):
        if self.view_switcher.get() == "List View":
            self.mod_list_frame.grid()
        else:
            self.tree_frame.grid()
        self.set_initial_sash_pos()
        self._is_resizing = False
        self._after_id = None

    # <<< END PERFORMANCE FIX >>>

    def load_config(self):
        try:
            with open("config.json", "r") as f:
                config_data = json.load(f)
                self.ryujinx_exe_path = config_data.get("ryujinx_exe_path", "")
                self.game_file_path = config_data.get("game_file_path", "")
                print(f"Loaded Ryujinx path: {self.ryujinx_exe_path}")
                print(f"Loaded game path: {self.game_file_path}")
        except (FileNotFoundError, json.JSONDecodeError):
            print(
                "config.json not found or is invalid. Paths will be requested on first launch."
            )
            self.ryujinx_exe_path = ""
            self.game_file_path = ""

    def save_config(self):
        try:
            config_data = {
                "ryujinx_exe_path": self.ryujinx_exe_path,
                "game_file_path": self.game_file_path,
            }
            with open("config.json", "w") as f:
                json.dump(config_data, f, indent=2)
                print("Saved Ryujinx and game paths to config.json")
        except Exception as e:
            messagebox.showerror(
                "Config Error", f"Could not save settings to config.json:\n{e}"
            )

    def _get_current_path(self):
        entry_path = self.path_entry.get()
        expected_redacted_path = self._redact_path(self.real_mods_path)
        if entry_path == expected_redacted_path:
            return self.real_mods_path
        else:
            new_path = self._unredact_path(entry_path)
            self._update_path_display(new_path)
            return new_path

    def _redact_path(self, path):
        if not path:
            return ""
        try:
            home_dir = os.path.expanduser("~")
            if os.path.normcase(path).startswith(os.path.normcase(home_dir)):
                redacted_path = (
                    os.path.join(os.path.dirname(home_dir), "[REDACTED]")
                    + path[len(home_dir) :]
                )
                return os.path.normpath(redacted_path)
        except Exception as e:
            print(f"Error redacting path: {e}")
        return path

    def _unredact_path(self, path):
        if not path or "[REDACTED]" not in path:
            return path
        try:
            home_dir = os.path.expanduser("~")
            redacted_home_prefix = os.path.normpath(
                os.path.join(os.path.dirname(home_dir), "[REDACTED]")
            )
            if os.path.normcase(path).startswith(
                os.path.normcase(redacted_home_prefix)
            ):
                unredacted_path = home_dir + path[len(redacted_home_prefix) :]
                return os.path.normpath(unredacted_path)
        except Exception as e:
            print(f"Error un-redacting path: {e}")
        return path

    def _update_path_display(self, new_path):
        self.real_mods_path = os.path.normpath(new_path) if new_path else ""
        redacted_path = self._redact_path(self.real_mods_path)
        self.path_entry.delete(0, "end")
        self.path_entry.insert(0, redacted_path)

    def clear_all_mods(self):
        if not self.analyzer.mods_path:
            messagebox.showwarning("No Folder", "Please select a mod folder first.")
            return
        if not messagebox.askyesno(
            "Confirm Disable All",
            "Are you sure you want to disable all mods?\n\nThis will uncheck all mods in the list. You must click 'Apply New Order' to save this change.",
        ):
            return
        for widget in self.mod_item_widgets.values():
            if hasattr(widget, "checkbox"):
                widget.checkbox.deselect()
        self.update_all_border_colors()
        if self.view_switcher.get() == "Tree View":
            self.populate_mod_tree()
        self.status_label.configure(
            text="All mods have been disabled. Click 'Apply New Order' to save."
        )

    def clear_all_cheats(self):
        if not self.analyzer.mods_path:
            messagebox.showwarning("No Folder", "Please select a mod folder first.")
            return
        if not messagebox.askyesno(
            "Confirm Disable All",
            "Are you sure you want to disable all cheats?\n\nThis will clear all pending cheat selections. You must click 'Apply New Order' to save this change.",
        ):
            return
        self.pending_cheat_selections.clear()
        self._initialize_pending_cheats()
        if self.current_details_mod and (
            self.current_details_mod in self.analyzer.cheat_only_mods
        ):
            self.show_details(self.current_details_mod)
        self.status_label.configure(
            text="All cheat selections cleared. Click 'Apply New Order' to save."
        )

    def set_initial_sash_pos(self):
        try:
            if self.paned_window.winfo_viewable():
                total_width = self.paned_window.winfo_width()
                self.paned_window.sashpos(0, total_width // 2)
        except Exception:
            pass

    def set_ui_state(self, state):
        self.current_state = state
        if state == "working":
            self.main_content_frame.grid_remove()
            self.progress_overlay.grid(row=0, column=0, rowspan=3, sticky="nsew")
            self.progress_overlay.tkraise()
        elif state == "idle":
            self.progress_overlay.grid_remove()
            self.main_content_frame.grid()
            self.main_content_frame.tkraise()

    def get_ordered_mods_config(self):
        ordered_widgets = [
            w for w in self.mod_list_frame.pack_slaves() if hasattr(w, "original_name")
        ]
        config = {}
        for widget in ordered_widgets:
            mod_name = widget.original_name
            if hasattr(widget, "checkbox"):
                config[mod_name] = widget.checkbox.get()
            else:
                config[mod_name] = True
        return config

    def apply_changes(self):
        if self.current_state == "working":
            return
        if not self.analyzer.mods_path:
            messagebox.showerror("Error", "No mod folder selected.")
            return
        if is_process_running("Ryujinx"):
            messagebox.showerror(
                "Process Running",
                "Ryujinx is currently running.\n\nPlease close Ryujinx before applying changes to prevent file access errors.",
            )
            return
        config = self.get_ordered_mods_config()
        conflicts_exist = False
        conflict_details = []
        ordered_widgets = [
            w for w in self.mod_list_frame.pack_slaves() if hasattr(w, "original_name")
        ]
        current_order_names = [w.original_name for w in ordered_widgets]
        for widget in ordered_widgets:
            mod_name = widget.original_name
            is_enabled = widget.checkbox.get() if hasattr(widget, "checkbox") else False
            if not is_enabled:
                continue
            if mod_name in self.analyzer.conflicts:
                my_index = current_order_names.index(mod_name)
                for file, other_mods in self.analyzer.conflicts[mod_name].items():
                    for other_name in other_mods:
                        if self._is_mod_enabled(other_name):
                            other_index = current_order_names.index(other_name)
                            if other_index > my_index:
                                conflicts_exist = True
                                winner = self.analyzer.strip_prefix(mod_name)
                                loser = self.analyzer.strip_prefix(other_name)
                                conflict_details.append(
                                    f"• File: {file}\n  '{winner}' will override '{loser}'"
                                )
        if conflicts_exist:
            conflict_text = (
                "The following file overrides will occur based on your new load order:\n\n"
                + "\n\n".join(list(set(conflict_details))[:10])
            )
            if len(conflict_details) > 10:
                conflict_text += (
                    f"\n\n... and {len(conflict_details) - 10} more overrides."
                )
            conflict_text += "\n\nThis is generally intended. Do you want to proceed with saving this order?"
            if not messagebox.askyesno("Confirm Load Order Overrides", conflict_text):
                self.status_label.configure(text="Apply cancelled by user.")
                return
        self.start_apply_worker(config)

    def start_apply_worker(self, config):
        self.set_ui_state("working")
        self.progress_bar.set(0)
        self.progress_detail_label.configure(text="Initializing...")
        self.apply_thread = threading.Thread(
            target=self.analyzer.apply_new_order_threaded,
            args=(config, self.pending_cheat_selections, self.progress_queue),
            daemon=True,
        )
        self.apply_thread.start()
        self.after(100, self.check_apply_progress)

    def check_apply_progress(self):
        try:
            while not self.progress_queue.empty():
                msg = self.progress_queue.get_nowait()
                msg_type = msg.get("type")
                if msg_type == "progress":
                    self.progress_bar.set(msg.get("value", 0))
                    self.progress_detail_label.configure(text=msg.get("text", ""))
                elif msg_type == "status":
                    self.progress_header_label.configure(
                        text=msg.get("text", "Working...")
                    )
                elif msg_type == "done":
                    self.set_ui_state("idle")
                    messagebox.showinfo(
                        "Success",
                        "New mod order and cheat selections applied successfully!",
                    )
                    self.run_scan()
                    return
                elif msg_type == "error":
                    self.set_ui_state("idle")
                    messagebox.showerror("Saving Error", msg.get("message"))
                    self.run_scan()
                    return
            if self.apply_thread and self.apply_thread.is_alive():
                self.after(100, self.check_apply_progress)
        except Exception as e:
            self.set_ui_state("idle")
            traceback.print_exc()
            messagebox.showerror(
                "UI Error", f"A critical error occurred while updating progress: {e}"
            )

    def run_scan(self):
        path = self._get_current_path()
        if not self.analyzer.set_mods_path(path):
            self.status_label.configure(text="Error: Invalid folder path.")
            return
        self.current_details_mod = None
        for widget in self.details_content_frame.winfo_children():
            widget.destroy()
        self.status_label.configure(text="Scanning...")
        self.update_idletasks()
        self.analyzer.scan_and_analyze()
        self._initialize_pending_cheats()
        self.populate_mod_list()
        self.update_all_border_colors()
        if self.view_switcher.get() == "Tree View":
            self.populate_mod_tree()
        conflict_count = len(
            [m for m in self.analyzer.conflicts if self._is_mod_enabled(m)]
        )
        scan_msg = f"Scan complete. Found {conflict_count} mods with enabled conflicts."
        if self.analyzer.mods_json_path:
            scan_msg += " (Ryujinx mods.json path found)"
        else:
            scan_msg += " (Ryujinx mods.json path not found)"
        self.status_label.configure(text=scan_msg)

    def _initialize_pending_cheats(self):
        self.pending_cheat_selections.clear()
        globally_enabled_cheats = set()
        special_cheats_folder = (
            self.analyzer.special_cheats_folder_name
            if self.analyzer.special_cheats_folder_name
            else "cheats"
        )
        central_enabled_path = os.path.join(
            self.analyzer.mods_path, special_cheats_folder, "enabled.txt"
        )
        if os.path.exists(central_enabled_path):
            try:
                with open(
                    central_enabled_path, "r", encoding="utf-8", errors="ignore"
                ) as f:
                    for line in f:
                        match = re.search(r"<(.*?) Cheat>", line)
                        if match:
                            globally_enabled_cheats.add(match.group(1).strip())
            except Exception as e:
                print(f"Warning: Could not read global enabled.txt: {e}")
        for mod_name in self.analyzer.cheat_only_mods:
            self.pending_cheat_selections[mod_name] = {}
            mod_cheat_path = os.path.join(self.analyzer.mods_path, mod_name, "cheats")
            if not os.path.isdir(mod_cheat_path):
                continue
            try:
                cheat_files = [
                    f
                    for f in os.listdir(mod_cheat_path)
                    if f.endswith(".txt") and f.lower() != "enabled.txt"
                ]
                for filename in cheat_files:
                    with open(
                        os.path.join(mod_cheat_path, filename),
                        "r",
                        encoding="utf-8",
                        errors="ignore",
                    ) as f:
                        content = f.read()
                    found_cheats = re.findall(
                        r"(\[.*?\])\s*([\s\S]*?)(?=\n\s*\[|$)", content
                    )
                    for name_with_brackets, code in found_cheats:
                        cheat_name = name_with_brackets.strip()[1:-1]
                        if cheat_name and code.strip():
                            is_enabled = cheat_name in globally_enabled_cheats
                            self.pending_cheat_selections[mod_name][cheat_name] = (
                                is_enabled
                            )
            except Exception as e:
                print(f"Warning: Could not parse cheats for '{mod_name}': {e}")

    def populate_mod_list(self):
        for widget in self.mod_list_frame.winfo_children():
            widget.destroy()
        self.mod_item_widgets.clear()
        special_cheat_folder = self.analyzer.special_cheats_folder_name
        romfs_mods = [
            m
            for m in self.analyzer.load_order
            if m not in self.analyzer.cheat_only_mods and m != special_cheat_folder
        ]
        cheat_mods = [
            m for m in self.analyzer.load_order if m in self.analyzer.cheat_only_mods
        ]
        for mod_name in romfs_mods:
            self.create_mod_item(mod_name, "romfs")
        if special_cheat_folder:
            self.create_mod_item(special_cheat_folder, "special_cheats")
        if cheat_mods:
            ctk.CTkLabel(
                self.mod_list_frame,
                text="--- Detected Cheats ---",
                text_color=Colors.CHEAT_MOD,
                anchor="center",
            ).pack(fill="x", padx=5, pady=(10, 2))
        for mod_name in cheat_mods:
            self.create_mod_item(mod_name, "cheat_only")

    def create_mod_item(self, mod_name, mod_type):
        clean_name = self.analyzer.strip_prefix(mod_name)
        border_frame = ctk.CTkFrame(
            self.mod_list_frame, corner_radius=8, fg_color=Colors.DISABLED
        )
        border_frame.pack(fill="x", padx=5, pady=2)
        content_frame = ctk.CTkFrame(
            border_frame, fg_color=Colors.WIDGET_BG, corner_radius=7
        )
        content_frame.pack(expand=True, fill="both", padx=1, pady=1)
        border_frame.original_name = mod_name
        content_frame.grid_columnconfigure(1, weight=1)
        label = ctk.CTkLabel(
            content_frame,
            text=clean_name,
            text_color=Colors.TEXT,
            anchor="w",
            fg_color="transparent",
        )
        if mod_type == "romfs":
            is_enabled = not mod_name.startswith("~")
            checkbox = ctk.CTkCheckBox(
                content_frame,
                text="",
                width=20,
                onvalue=True,
                offvalue=False,
                command=self.on_checkbox_toggle,
            )
            checkbox.grid(row=0, column=0, padx=(5, 0), pady=4)
            if is_enabled:
                checkbox.select()
            border_frame.checkbox = checkbox
            drag_handle = ctk.CTkLabel(
                content_frame,
                text="≡",
                text_color=Colors.TEXT,
                fg_color="transparent",
                width=20,
            )
            drag_handle.grid(row=0, column=2, padx=(0, 5), pady=2)
            self.setup_drag_drop(border_frame, drag_handle)
        elif mod_type == "special_cheats":
            border_frame.configure(fg_color=Colors.BG)
            label.configure(text=clean_name)
        else:
            label.configure(text=f"~ {clean_name}")
        label.grid(row=0, column=1, sticky="ew", padx=10)
        self.mod_item_widgets[mod_name] = border_frame
        clickable_widget = content_frame if mod_type == "special_cheats" else label
        clickable_widget.bind("<Button-1>", lambda e, m=mod_name: self.show_details(m))
        if mod_type == "special_cheats":
            label.bind("<Button-1>", lambda e, m=mod_name: self.show_details(m))
        all_widgets_in_item = [border_frame, content_frame, label]
        if mod_type == "romfs":
            all_widgets_in_item.extend([border_frame.checkbox, drag_handle])
        for w in all_widgets_in_item:
            w.bind("<Button-3>", lambda e, m=mod_name: self.show_context_menu(e, m))
            w.bind("<Button-2>", lambda e, m=mod_name: self.show_context_menu(e, m))

    def on_checkbox_toggle(self):
        self.update_all_border_colors()
        if self.view_switcher.get() == "Tree View":
            self.populate_mod_tree()

    def update_all_border_colors(self):
        ordered_widgets = self.mod_list_frame.pack_slaves()
        current_order_names = [
            w.original_name for w in ordered_widgets if hasattr(w, "original_name")
        ]
        for widget in ordered_widgets:
            if not hasattr(widget, "original_name"):
                continue
            mod_name = widget.original_name
            if not hasattr(widget, "checkbox"):
                if mod_name == self.analyzer.special_cheats_folder_name:
                    widget.configure(fg_color=Colors.BG)
                elif mod_name in self.analyzer.cheat_only_mods:
                    widget.configure(fg_color=Colors.CHEAT_MOD)
                continue
            if not widget.checkbox.get():
                widget.configure(fg_color=Colors.DISABLED)
                continue
            is_overridden_by_higher_mod = False
            is_overriding_lower_mod = False
            if mod_name in self.analyzer.conflicts:
                my_index = current_order_names.index(mod_name)
                for file, other_mods in self.analyzer.conflicts[mod_name].items():
                    for other_name in other_mods:
                        if self._is_mod_enabled(other_name):
                            try:
                                other_index = current_order_names.index(other_name)
                                if other_index < my_index:
                                    is_overridden_by_higher_mod = True
                                else:
                                    is_overriding_lower_mod = True
                            except ValueError:
                                continue
            if is_overridden_by_higher_mod:
                widget.configure(fg_color=Colors.CONFLICT)
            elif is_overriding_lower_mod:
                widget.configure(fg_color=Colors.RESOLVED_CONFLICT)
            else:
                widget.configure(fg_color=Colors.NO_CONFLICT)

    def _is_mod_enabled(self, mod_name):
        widget = self.mod_item_widgets.get(mod_name)
        if not widget:
            return False
        if hasattr(widget, "checkbox"):
            return widget.checkbox.get()
        return True

    def populate_mod_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        ordered_widgets = [
            w for w in self.mod_list_frame.pack_slaves() if hasattr(w, "original_name")
        ]
        current_order_names = [w.original_name for w in ordered_widgets]
        tree_data = []
        try:
            for mod_name in current_order_names:
                mod_info = {
                    "name": mod_name,
                    "status": "",
                    "tag": "noconflict",
                    "files": [],
                }
                widget = self.mod_item_widgets.get(mod_name)
                is_romfs_mod = widget and hasattr(widget, "checkbox")
                if not is_romfs_mod:
                    mod_info["status"] = (
                        "Cheat Only"
                        if mod_name in self.analyzer.cheat_only_mods
                        else "Ryujinx Enabled Cheats File"
                    )
                    mod_info["tag"] = "cheat"
                elif not widget.checkbox.get():
                    mod_info["status"] = "Disabled"
                else:
                    conflict_count = 0
                    override_count = 0
                    is_overridden = False
                    if mod_name in self.analyzer.conflicts:
                        for file_path, other_mods in self.analyzer.conflicts[
                            mod_name
                        ].items():
                            enabled_involved = [mod_name] + [
                                m for m in other_mods if self._is_mod_enabled(m)
                            ]
                            if len(enabled_involved) > 1:
                                override_mod = min(
                                    enabled_involved,
                                    key=lambda m: current_order_names.index(m)
                                    if m in current_order_names
                                    else float("inf"),
                                )
                                if mod_name == override_mod:
                                    override_count += 1
                                else:
                                    conflict_count += 1
                                    is_overridden = True
                    if is_overridden:
                        mod_info["status"] = f"Conflicts ({conflict_count})"
                        mod_info["tag"] = "loser"
                    elif override_count > 0:
                        mod_info["status"] = f"Overrides ({override_count})"
                        mod_info["tag"] = "winner"
                    else:
                        mod_info["status"] = "No Conflicts"
                        mod_info["tag"] = "noconflict"
                if mod_name in self.analyzer.mod_files and is_romfs_mod:
                    for file_path in sorted(list(self.analyzer.mod_files[mod_name])):
                        file_info = {
                            "path": file_path,
                            "status": "",
                            "tag": "noconflict",
                        }
                        if widget.checkbox.get():
                            potential_conflict = (
                                mod_name in self.analyzer.conflicts
                                and file_path in self.analyzer.conflicts[mod_name]
                            )
                            if not potential_conflict:
                                file_info["status"] = "Loaded"
                                file_info["tag"] = "loaded"
                            else:
                                all_involved = self.analyzer.conflicts[mod_name][
                                    file_path
                                ] + [mod_name]
                                enabled_involved = [
                                    m for m in all_involved if self._is_mod_enabled(m)
                                ]
                                if len(enabled_involved) < 2:
                                    file_info["status"] = "Loaded"
                                    file_info["tag"] = "loaded"
                                else:
                                    override_mod = min(
                                        enabled_involved,
                                        key=lambda m: current_order_names.index(m)
                                        if m in current_order_names
                                        else float("inf"),
                                    )
                                    if mod_name == override_mod:
                                        losers = [
                                            self.analyzer.strip_prefix(m)
                                            for m in enabled_involved
                                            if m != mod_name
                                        ]
                                        file_info["status"] = (
                                            f"Overrides: {', '.join(losers)}"
                                        )
                                        file_info["tag"] = "winner"
                                    else:
                                        file_info["status"] = (
                                            f"Conflicts (by {self.analyzer.strip_prefix(override_mod)})"
                                        )
                                        file_info["tag"] = "loser"
                        mod_info["files"].append(file_info)
                tree_data.append(mod_info)
        except Exception as e:
            print("--- ERROR DURING TREE VIEW CALCULATION ---")
            traceback.print_exc()
            messagebox.showerror(
                "Tree View Error",
                f"A critical error occurred while analyzing the mod list.\n\nError: {e}",
            )
        for mod_data in tree_data:
            clean_name = self.analyzer.strip_prefix(mod_data["name"])
            mod_id = self.tree.insert(
                "",
                "end",
                text=clean_name,
                values=(mod_data["status"],),
                tags=(mod_data["tag"],),
            )
            priority_map = {"winner": 0, "loser": 0, "loaded": 1, "noconflict": 2}
            sorted_files = sorted(
                mod_data["files"],
                key=lambda f: (priority_map.get(f["tag"], 99), f["path"]),
            )
            for file_data in sorted_files:
                self.tree.insert(
                    mod_id,
                    "end",
                    text=file_data["path"],
                    values=(file_data["status"],),
                    tags=(file_data["tag"],),
                )

    def on_drop(self, event):
        if self.current_state == "working":
            return
        target_dir = self._get_current_path()
        if not target_dir or not os.path.isdir(target_dir):
            messagebox.showerror(
                "Error", "Please select a valid mod folder before dropping files."
            )
            return
        dropped_items = self.master.tk.splitlist(event.data)
        for item_path in dropped_items:
            base_name = os.path.basename(item_path)
            is_archive = item_path.lower().endswith((".zip", ".7z"))
            dest_name = os.path.splitext(base_name)[0] if is_archive else base_name
            destination_path = os.path.join(target_dir, dest_name)
            if os.path.exists(destination_path):
                if not messagebox.askyesno(
                    "Overwrite Confirmation",
                    f"A mod named '{dest_name}' already exists. Overwrite it?",
                ):
                    continue
                try:
                    if os.path.isdir(destination_path):
                        shutil.rmtree(destination_path)
                    else:
                        os.remove(destination_path)
                except Exception as e:
                    messagebox.showerror(
                        "Error", f"Failed to remove existing mod '{dest_name}':\n{e}"
                    )
                    continue
            try:
                self.status_label.configure(text=f"Installing {base_name}...")
                self.update_idletasks()
                if item_path.lower().endswith(".zip"):
                    with zipfile.ZipFile(item_path, "r") as zip_ref:
                        zip_ref.extractall(destination_path)
                elif item_path.lower().endswith(".7z"):
                    if not PY7ZR_SUPPORT:
                        messagebox.showerror(
                            "Missing Library",
                            "To extract .7z files, please install the 'py7zr' library.\n\nRun: pip install py7zr",
                        )
                        continue
                    with py7zr.SevenZipFile(item_path, mode="r") as z_ref:
                        z_ref.extractall(path=destination_path)
                elif os.path.isdir(item_path):
                    shutil.copytree(item_path, destination_path)
            except Exception as e:
                messagebox.showerror(
                    "Installation Failed", f"Could not install '{base_name}':\n{e}"
                )
        self.status_label.configure(text="Installation complete. Refreshing list...")
        self.run_scan()

    def setup_treeview(self, style):
        style.theme_use("default")
        style.configure(
            "Treeview",
            background=Colors.WIDGET_BG,
            foreground=Colors.TEXT,
            fieldbackground=Colors.WIDGET_BG,
            borderwidth=0,
        )
        style.map("Treeview", background=[("selected", Colors.HIGHLIGHT_BG)])
        style.configure(
            "Treeview.Heading",
            background=Colors.TREE_HEADING_BG,
            foreground=Colors.TEXT,
            relief="flat",
        )
        style.map("Treeview.Heading", background=[("active", Colors.BUTTON_HOVER)])
        self.tree = ttk.Treeview(
            self.tree_frame, columns=("status",), show="tree headings"
        )
        self.tree.heading("#0", text="Mod / File")
        self.tree.heading("status", text="Status")
        self.tree.column("#0", stretch=True, width=450)
        self.tree.column("status", stretch=True, width=200)
        self.tree.tag_configure("winner", foreground=Colors.RESOLVED_CONFLICT)
        self.tree.tag_configure("loser", foreground=Colors.CONFLICT)
        self.tree.tag_configure("loaded", foreground=Colors.NO_CONFLICT)
        self.tree.tag_configure("noconflict", foreground=Colors.TEXT)
        self.tree.tag_configure("cheat", foreground=Colors.CHEAT_MOD)
        self.tree.pack(expand=True, fill="both")

    def switch_view(self, view_name):
        if self.current_state == "working":
            return
        if view_name == "List View":
            self.tree_frame.grid_remove()
            self.mod_list_frame.grid(row=0, column=0, sticky="nsew")
        else:
            self.populate_mod_tree()
            self.mod_list_frame.grid_remove()
            self.tree_frame.grid(row=0, column=0, sticky="nsew")

    def select_folder(self):
        if self.current_state == "working":
            return
        path = filedialog.askdirectory(title="Select Game Mod Folder")
        if path:
            self._update_path_display(path)
            self.run_scan()

    def open_mod_directory(self):
        path = self._get_current_path()
        if not path or not os.path.isdir(path):
            messagebox.showwarning(
                "Warning", "The specified path is not a valid directory."
            )
            return
        try:
            if sys.platform == "win32":
                os.startfile(os.path.normpath(path))
            elif sys.platform == "darwin":
                subprocess.run(["open", path])
            else:
                subprocess.run(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open directory:\n{e}")

    def preview_enabled_cheats_popup(self):
        mods_path = self._get_current_path()
        if not mods_path or not os.path.isdir(mods_path):
            messagebox.showwarning("Warning", "The mod directory path is not valid.")
            return
        special_cheats_folder = (
            self.analyzer.special_cheats_folder_name
            if self.analyzer.special_cheats_folder_name
            else "cheats"
        )
        enabled_txt_path = os.path.join(mods_path, special_cheats_folder, "enabled.txt")
        file_content = ""
        if not os.path.exists(enabled_txt_path):
            file_content = (
                f"File not found at:\n{enabled_txt_path}\n\n"
                "This file will be created or updated when you click 'Apply New Order'."
            )
        else:
            try:
                with open(enabled_txt_path, "r", encoding="utf-8") as f:
                    file_content = f.read()
                if not file_content:
                    file_content = "(The enabled.txt file is empty. No cheats are currently enabled.)"
            except Exception as e:
                messagebox.showerror("Error", f"Could not read enabled.txt:\n{e}")
                return
        popup = ctk.CTkToplevel(self)
        popup.title("Preview of enabled.txt")
        popup.geometry("600x400")
        popup.transient(self.master)
        popup.grab_set()
        popup.grid_rowconfigure(0, weight=1)
        popup.grid_columnconfigure(0, weight=1)
        textbox = ctk.CTkTextbox(
            popup,
            text_color=Colors.TEXT,
            fg_color=Colors.WIDGET_BG,
            wrap="word",
            font=("Consolas", 12),
        )
        textbox.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        textbox.insert("1.0", file_content)
        textbox.configure(state="disabled")

    def setup_drag_drop(self, border_frame, drag_handle):
        def on_drag_start(event):
            if self.current_state == "working":
                return
            self.drag_data["item"] = border_frame
            drag_handle.configure(text_color=Colors.DRAG_HIGHLIGHT)
            border_frame.configure(fg_color=Colors.DRAG_HIGHLIGHT)

        def on_drag_motion(event):
            if self.drag_data["item"] is None:
                return
            reorderable_widgets = self.mod_list_frame.pack_slaves()
            for widget in reorderable_widgets:
                if widget == self.drag_data["item"] or not hasattr(
                    widget, "original_name"
                ):
                    continue
                widget_y = widget.winfo_rooty()
                widget_height = widget.winfo_height()
                if widget_y <= event.y_root <= widget_y + widget_height:
                    mouse_relative = event.y_root - widget_y
                    if mouse_relative < widget_height / 2:
                        self.drag_data["item"].pack_configure(before=widget)
                    else:
                        self.drag_data["item"].pack_configure(after=widget)
                    break

        def on_drag_end(event):
            if self.drag_data["item"]:
                drag_handle.configure(text_color=Colors.TEXT)
                self.update_all_border_colors()
                if self.view_switcher.get() == "Tree View":
                    self.populate_mod_tree()
                self.drag_data["item"] = None

        for widget in [drag_handle, border_frame, border_frame.winfo_children()[0]]:
            widget.bind("<Button-1>", on_drag_start)
            widget.bind("<B1-Motion>", on_drag_motion)
            widget.bind("<ButtonRelease-1>", on_drag_end)

    def show_details(self, mod_name):
        if self.current_state == "working":
            return
        self.current_details_mod = mod_name
        for widget in self.details_content_frame.winfo_children():
            widget.destroy()
        if mod_name == self.analyzer.special_cheats_folder_name:
            self.display_enabled_cheats_preview()
        elif mod_name in self.analyzer.cheat_only_mods:
            self.display_cheat_manager(mod_name)
        else:
            self.display_conflict_details(mod_name)

    def display_enabled_cheats_preview(self):
        ctk.CTkLabel(
            self.details_content_frame,
            text="Preview: enabled.txt",
            font=("", 14, "bold"),
            text_color=Colors.TEXT,
        ).pack(pady=5, anchor="w", padx=5)
        textbox = ctk.CTkTextbox(
            self.details_content_frame,
            text_color=Colors.TEXT,
            fg_color=Colors.WIDGET_BG,
            wrap="word",
            font=("Consolas", 12),
        )
        textbox.pack(expand=True, fill="both", padx=5, pady=5)
        special_cheats_folder = (
            self.analyzer.special_cheats_folder_name
            if self.analyzer.special_cheats_folder_name
            else "cheats"
        )
        enabled_txt_path = os.path.join(
            self.analyzer.mods_path, special_cheats_folder, "enabled.txt"
        )
        file_content = ""
        if not os.path.exists(enabled_txt_path):
            file_content = (
                f"File not found at:\n{enabled_txt_path}\n\n"
                "This file will be created or updated when you click 'Apply New Order'."
            )
        else:
            try:
                with open(enabled_txt_path, "r", encoding="utf-8") as f:
                    file_content = f.read()
                if not file_content:
                    file_content = "(The enabled.txt file is empty. No cheats are currently enabled.)"
            except Exception as e:
                file_content = f"Error reading file:\n{e}"
        textbox.insert("1.0", file_content)
        textbox.configure(state="disabled")

    def display_conflict_details(self, mod_name):
        textbox = ctk.CTkTextbox(
            self.details_content_frame,
            text_color=Colors.TEXT,
            fg_color=Colors.WIDGET_BG,
            wrap="word",
        )
        textbox.pack(expand=True, fill="both")
        clean_name = self.analyzer.strip_prefix(mod_name)
        if mod_name not in self.analyzer.conflicts:
            text = f"MOD: {clean_name}\n\nStatus: No conflicts detected."
        else:
            text = f"MOD: {clean_name}\n\nThis mod has conflicts with the following files:\n\n"
            for file, other_mods in self.analyzer.conflicts[mod_name].items():
                text += f"FILE: {file}\n  - Conflicts with: {', '.join(self.analyzer.strip_prefix(m) for m in other_mods)}\n\n"
            text += "REMINDER: The mod at the TOP of the list takes priority."
        textbox.insert("1.0", text)
        textbox.configure(state="disabled")

    def _update_pending_cheats(self, mod_name, cheat_name, var):
        if mod_name not in self.pending_cheat_selections:
            self.pending_cheat_selections[mod_name] = {}
        self.pending_cheat_selections[mod_name][cheat_name] = var.get()
        self.status_label.configure(
            text="Unsaved cheat selections. Click 'Apply New Order' to save."
        )

    def display_cheat_manager(self, mod_name):
        clean_name = self.analyzer.strip_prefix(mod_name)
        for widget in self.details_content_frame.winfo_children():
            widget.destroy()
        ctk.CTkLabel(
            self.details_content_frame,
            text=f"Cheat Manager for: {clean_name}",
            font=("", 14, "bold"),
            text_color=Colors.TEXT,
        ).pack(pady=5, anchor="w", padx=5)
        mod_base_path = os.path.join(self.analyzer.mods_path, mod_name)
        mod_cheat_path = os.path.join(mod_base_path, "cheats")
        if not os.path.isdir(mod_cheat_path):
            ctk.CTkLabel(
                self.details_content_frame,
                text="No 'cheats' subfolder found in this mod.",
                text_color=Colors.TEXT,
            ).pack(pady=10)
            return
        current_mod_cheats = self.pending_cheat_selections.get(mod_name, {})
        scroll_frame = ctk.CTkScrollableFrame(
            self.details_content_frame,
            label_text="Available Cheats",
            fg_color="transparent",
        )
        scroll_frame.pack(expand=True, fill="both", padx=5, pady=5)
        if not current_mod_cheats:
            ctk.CTkLabel(
                scroll_frame,
                text="No valid cheat definitions found in .txt files.",
                text_color=Colors.TEXT,
            ).pack()
            return
        for cheat_name in sorted(current_mod_cheats.keys()):
            row_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
            row_frame.pack(fill="x", expand=True, pady=2)
            row_frame.grid_columnconfigure(1, weight=1)
            var = ctk.BooleanVar(value=current_mod_cheats.get(cheat_name, False))
            var.trace_add(
                "write",
                lambda name,
                index,
                mode,
                v=var,
                m=mod_name,
                c=cheat_name: self._update_pending_cheats(m, c, v),
            )
            cb = ctk.CTkCheckBox(row_frame, text="", variable=var)
            cb.grid(row=0, column=0, padx=(5, 0))
            label = ctk.CTkLabel(
                row_frame,
                text=cheat_name,
                text_color=Colors.TEXT,
                anchor="w",
                cursor="hand2",
            )
            label.grid(row=0, column=1, sticky="ew", padx=(5, 10))
            label.bind("<Button-1>", lambda e, checkbox=cb: checkbox.toggle())
            view_btn = ctk.CTkButton(
                row_frame,
                text="View Code",
                width=80,
                fg_color=Colors.BUTTON_BG,
                hover_color=Colors.BUTTON_HOVER,
                command=lambda m=mod_name, c=cheat_name: self.show_cheat_code_popup(
                    m, c
                ),
            )
            view_btn.grid(row=0, column=2, padx=5)
            edit_btn = ctk.CTkButton(
                row_frame,
                text="Edit",
                width=60,
                fg_color=Colors.BUTTON_BG,
                hover_color=Colors.BUTTON_HOVER,
                command=lambda m=mod_name, c=cheat_name: self.edit_cheat_code_popup(
                    m, c
                ),
            )
            edit_btn.grid(row=0, column=3, padx=5)

    def show_cheat_code_popup(self, mod_name, cheat_name):
        cheat_code = (
            "Could not find cheat code. The cheat file may have been moved or renamed."
        )
        mod_base_path = os.path.join(self.analyzer.mods_path, mod_name)
        cheat_path = None
        try:
            for item in os.listdir(mod_base_path):
                if item.lower() == "cheats" and os.path.isdir(
                    os.path.join(mod_base_path, item)
                ):
                    cheat_path = os.path.join(mod_base_path, item)
                    break
        except Exception as e:
            print(f"Error finding cheat path for {mod_name}: {e}")
        if cheat_path:
            try:
                cheat_files = [
                    f
                    for f in os.listdir(cheat_path)
                    if f.endswith(".txt") and f.lower() != "enabled.txt"
                ]
                for filename in cheat_files:
                    with open(
                        os.path.join(cheat_path, filename),
                        "r",
                        encoding="utf-8",
                        errors="ignore",
                    ) as f:
                        content = f.read()
                    match = re.search(
                        r"\[" + re.escape(cheat_name) + r"\]\s*([\s\S]*?)(?=\n\s*\[|$)",
                        content,
                    )
                    if match:
                        cheat_code = match.group(1).strip()
                        break
            except Exception as e:
                print(f"Error reading cheat code for {cheat_name} in {mod_name}: {e}")
        popup = ctk.CTkToplevel(self)
        popup.title(f"Code for: {cheat_name}")
        popup.geometry("600x400")
        popup.transient(self.master)
        popup.grab_set()
        popup.grid_rowconfigure(0, weight=1)
        popup.grid_columnconfigure(0, weight=1)
        textbox = ctk.CTkTextbox(
            popup,
            text_color=Colors.TEXT,
            fg_color=Colors.WIDGET_BG,
            wrap="word",
            font=("Consolas", 12),
        )
        textbox.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        textbox.insert("1.0", cheat_code)
        textbox.configure(state="disabled")

    def edit_cheat_code_popup(self, mod_name, cheat_name):
        file_path, error = self._find_cheat_file_path(mod_name, cheat_name)
        if error:
            messagebox.showerror("Error", error)
            return
        cheat_code = ""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            match = re.search(
                r"\[\s*" + re.escape(cheat_name) + r"\s*\]\s*([\s\S]*?)(?=\n\s*\[|$)",
                content,
            )
            if match:
                cheat_code = match.group(1).strip()
            else:
                messagebox.showerror(
                    "Error",
                    f"Could not find cheat '{cheat_name}' in file '{os.path.basename(file_path)}'.",
                )
                return
        except Exception as e:
            messagebox.showerror("Read Error", f"Failed to read cheat code: {e}")
            return
        popup = ctk.CTkToplevel(self)
        popup.title(f"Edit: {cheat_name}")
        popup.geometry("700x500")
        popup.transient(self.master)
        popup.grab_set()
        popup.grid_rowconfigure(0, weight=1)
        popup.grid_columnconfigure(0, weight=1)
        textbox = ctk.CTkTextbox(
            popup,
            text_color=Colors.TEXT,
            fg_color=Colors.WIDGET_BG,
            wrap="word",
            font=("Consolas", 12),
        )
        textbox.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 0))
        textbox.insert("1.0", cheat_code)

        def save_changes():
            new_code = textbox.get("1.0", "end-1c")
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    full_content = f.read()
                pattern = re.compile(
                    r"(\[" + re.escape(cheat_name) + r"\]\s*)([\s\S]*?)((?=\n\s*\[)|$)",
                    re.IGNORECASE,
                )
                if not pattern.search(full_content):
                    raise ValueError(
                        f"Could not find the cheat block for '{cheat_name}' to replace."
                    )
                new_full_content = pattern.sub(
                    r"\1" + new_code.strip() + r"\3", full_content, count=1
                )
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_full_content)
                messagebox.showinfo(
                    "Success", f"Cheat '{cheat_name}' has been saved.", parent=popup
                )
                popup.destroy()
            except Exception as e:
                messagebox.showerror(
                    "Save Error", f"Failed to save cheat: {e}", parent=popup
                )

        button_frame = ctk.CTkFrame(popup, fg_color="transparent")
        button_frame.grid(row=1, column=0, pady=10, sticky="ew")
        button_frame.grid_columnconfigure((0, 1), weight=1)
        save_button = ctk.CTkButton(
            button_frame,
            text="Save",
            command=save_changes,
            fg_color=Colors.BUTTON_BG,
            hover_color=Colors.BUTTON_HOVER,
        )
        save_button.grid(row=0, column=0, padx=10, sticky="e")
        cancel_button = ctk.CTkButton(
            button_frame,
            text="Cancel",
            command=popup.destroy,
            fg_color=Colors.BUTTON_BG,
            hover_color=Colors.BUTTON_HOVER,
        )
        cancel_button.grid(row=0, column=1, padx=10, sticky="w")

    def _find_cheat_file_path(self, mod_name, cheat_name):
        mod_base_path = os.path.join(self.analyzer.mods_path, mod_name)
        cheat_dir_path = None
        try:
            for item in os.listdir(mod_base_path):
                if item.lower() == "cheats" and os.path.isdir(
                    os.path.join(mod_base_path, item)
                ):
                    cheat_dir_path = os.path.join(mod_base_path, item)
                    break
            if not cheat_dir_path:
                return None, "No 'cheats' subfolder found."
            cheat_files = [
                f
                for f in os.listdir(cheat_dir_path)
                if f.endswith(".txt") and f.lower() != "enabled.txt"
            ]
            for filename in cheat_files:
                file_path = os.path.join(cheat_dir_path, filename)
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                if re.search(
                    r"\[" + re.escape(cheat_name) + r"\]", content, re.IGNORECASE
                ):
                    return file_path, None
        except Exception as e:
            return None, f"Error finding cheat file: {e}"
        return None, "Cheat file not found."

    def launch_game(self):
        if not self.ryujinx_exe_path or not os.path.exists(self.ryujinx_exe_path):
            messagebox.showinfo(
                "Ryujinx Location Needed",
                "Please select your Ryujinx executable (Ryujinx.exe).",
            )
            filetypes = [("Executable files", "*.exe"), ("All files", "*.*")]
            if sys.platform == "darwin":
                filetypes = [("Application", "*.app"), ("All files", "*.*")]
            elif sys.platform != "win32":
                filetypes = [("All files", "*.*")]
            user_selected_path = filedialog.askopenfilename(
                title="Select your Ryujinx Executable", filetypes=filetypes
            )
            if not user_selected_path:
                self.status_label.configure(text="Game launch cancelled.")
                return
            self.ryujinx_exe_path = user_selected_path
            self.save_config()
        if not self.game_file_path or not os.path.exists(self.game_file_path):
            messagebox.showinfo(
                "Game File Needed",
                "Please select your Monster Hunter Generations Ultimate game file (.nsp, .xci, etc.).",
            )
            user_selected_path = filedialog.askopenfilename(
                title="Select your MHGU game file",
                filetypes=(
                    ("Switch Game Files", "*.nsp *.xci *.nca"),
                    ("All files", "*.*"),
                ),
            )
            if not user_selected_path:
                self.status_label.configure(text="Game launch cancelled.")
                return
            self.game_file_path = user_selected_path
            self.save_config()
        try:
            self.status_label.configure(text="Launching MHGU...")
            command_list = [self.ryujinx_exe_path, self.game_file_path]
            if sys.platform == "darwin" and self.ryujinx_exe_path.endswith(".app"):
                command_list[0] = os.path.join(
                    self.ryujinx_exe_path, "Contents", "MacOS", "Ryujinx"
                )
            subprocess.Popen(command_list)
            self.status_label.configure(text="Launch command sent to Ryujinx.")
            messagebox.showinfo(
                "Ryujinx Launched",
                "Launch command sent to Ryujinx.\n\ndreamSort will wait for you. Press OK when you have closed the game to continue.",
            )
        except Exception as e:
            messagebox.showerror(
                "Launch Error",
                f"An error occurred while trying to launch the game:\n{e}",
            )

    def show_context_menu(self, event, mod_name):
        context_menu = tk.Menu(
            self,
            tearoff=0,
            bg=Colors.WIDGET_BG,
            fg=Colors.TEXT,
            activebackground=Colors.BUTTON_HOVER,
            activeforeground=Colors.TEXT,
            relief="flat",
            borderwidth=1,
        )
        context_menu.add_command(
            label="Delete", command=lambda m=mod_name: self.delete_mod(m)
        )
        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()

    def delete_mod(self, mod_name):
        clean_name = self.analyzer.strip_prefix(mod_name)
        if not messagebox.askyesno(
            "Confirm Deletion",
            f"Are you sure you want to permanently delete the mod '{clean_name}'?\n\nThis action cannot be undone.",
        ):
            return
        mod_path = os.path.join(self.analyzer.mods_path, mod_name)
        try:
            if os.path.isdir(mod_path):
                shutil.rmtree(mod_path)
            elif os.path.exists(mod_path):
                os.remove(mod_path)
            self.status_label.configure(
                text=f"Deleted '{clean_name}'. Refreshing list..."
            )
            if self.current_details_mod == mod_name:
                self.current_details_mod = None
                for widget in self.details_content_frame.winfo_children():
                    widget.destroy()
            self.run_scan()
        except PermissionError:
            messagebox.showerror(
                "Deletion Failed",
                f"Permission denied. Could not delete '{clean_name}'.\n\nPlease make sure the file is not in use (e.g., by Ryujinx) and that you have the necessary permissions. Try running as administrator.",
            )
        except Exception as e:
            messagebox.showerror(
                "Deletion Failed",
                f"An error occurred while deleting '{clean_name}':\n{e}",
            )


class DreamSortMainWindow(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"dreamSort - Mod Manager {VERSION}")
        try:
            self.iconbitmap(resource_path("yoohyeon.ico"))
        except Exception:
            print("Warning: yoohyeon.ico not found. Skipping icon set.")
        self.geometry("1600x900")
        self.minsize(800, 600)
        self.configure(bg=Colors.BG)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.app = DreamSortApp(self)
        self.app.grid(row=0, column=0, sticky="nsew")


if __name__ == "__main__":
    app = DreamSortMainWindow()
    app.mainloop()
