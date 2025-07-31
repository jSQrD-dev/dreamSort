# dreamSort Mod Manager
### A Ryujinx Mod Manager for MHGU
```
Developed by Handburger
Thanks to jSQrD for providing Linux Binaries for dreamSort
```
Supports Windows x64, Linux, Steam Deck
> Here's a list of features:

* Install mods easily with drag-drop folders, 7z or zip files (6.2.4 feature).
* Install cheats easily via checkbox and have it be applied to Ryujinx. (bugfixed)
* Clear all loaded mods & cheats via UI buttons.
* Direct Ryujinx integration (you don't have to use the various menus in Ryujinx anymore!)
* Launch GU from dreamSort directly
* Sort mods based on importance or conflicts.
* Renames Mods to align with user-defined sorting.
* Pre-set to Ryujinx MHGU mod folder automatically.
* Colour coded outline based on mod installation compatibility (Green is overrides, Red means conflicts, blue for no conflicts).
* List View and Tree View, with list is where you enable or disable desired mods, and tree view being which files specifically are overriding or conflicting.
* Edit cheats in-app with the editor.
* Right-click to delete any mod or cheat you don't want.
* App warnings if Ryujinx is running before you press apply - avoiding errors.
* Permanent Dark Mode (Hurray!)
* Yoohyeon from Dreamcatcher as the icon.

For Compiling for Linux Binaries
```
Python 3
Need tkinter from your package manager 
For Ubuntu/Debian:
  apt-get install python3-tk
For Fedora:
  dnf install python3-tkinter
For Arch:
  pacman -S tk

TkinterDnD2 via pip
  pip install tkinterdnd2
CustomTkinter via pip
  pip install  customtkinter
pyinstaller via pip
  pip install -U pyinstaller

pyinstaller --onefile --windowed --noconfirm HB_dreamSort.py
```

For Windows Python Pyinstaller compilation
```
pyinstaller --onefile --windowed --noconfirm --icon="yoohyeon.ico" --add-data="yoohyeon.ico;." --add-data="C:\Users\[redacted]\AppData\Local\Programs\Python\Python313\Lib\site-packages\tkinterdnd2;tkinterdnd2" HB_dreamSort.py
```
