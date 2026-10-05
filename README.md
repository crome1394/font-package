# US English fonts

One script installs a short font menu for a word processor, a spreadsheet, and a terminal. It works on CachyOS, Pop!_OS, and other Linux systems. It does not need apt or pacman.

The menu is the list a Word user or a Pages user can search: Arial, Calibri, Cambria, Times New Roman, Garamond, Helvetica, and the rest of the usual names. A document that asks for one of those names finds a font. Foreign-script fonts can be installed. They are not dumped into that menu by the hundred. A handful stay, because a hidden font cannot draw its characters.

## Install

Copy this whole directory onto the other computer. The fonts are already in the `fonts/` folder, so a fresh install does not need a network connection and does not need apt or pacman. From this directory:

```bash
./install.sh
```

That copies `fonts/` to `~/.local/share/fonts/us-english` and writes three fontconfig files in `~/.config/fontconfig/conf.d/`. Run it again after a reinstall. The computer needs Python 3 and fontconfig (`fc-cache`), which a normal desktop install already has.

`./install.sh --download` rebuilds the open faces from the internet and refreshes the `fonts/` folder. Use that on a machine that is online when you want newer files on the USB stick. A normal install leaves `fonts/` as it is. `--download` does not fetch the Windows fonts when `ms-fonts/arial.ttf` is already in this folder. It uses those files instead.

```bash
./install.sh --all
```

`--all` accepts the core fonts EULA and installs the extra coding fonts. It does not by itself rebuild from the internet. `./install.sh --all --download` does both. `--skip-mscorefonts` still leaves the classic core fonts out.

The first run on this machine moved the old folders (`Apple`, `EB Garamond`, `Hack`, `ms-fonts`, `Nerd-fonts`, `Noto`, `ubuntu`) from `~/.local/share/fonts` to:

```text
~/.local/share/fonts-backup-20261005
```

That backup is left in place. The script does not delete it.

## Other computers in the family

Copy this directory to the USB stick and run `./install.sh` on the fresh install. The open fonts (Noto, Liberation, the Google faces, Ubuntu, TeX Gyre, JetBrains Mono, and the rest) are in `fonts/`.

`fonts/microsoft/` and `ms-fonts/` are the Windows faces from a machine that already has Windows or Microsoft 365. Leave them in the copy for a family computer that has that license. Take both folders off the stick for a computer that does not. Calibri, Cambria, and Segoe UI then open through Carlito, Caladea, and Selawik.

On a machine without those Microsoft files, `./install.sh --download` can still fetch the classic core fonts: Arial, Arial Black, Times New Roman, Verdana, Georgia, Courier New, Comic Sans MS, Impact, Trebuchet MS, Andale Mono, and Webdings. Running that command accepts the [Microsoft core fonts EULA](https://sourceforge.net/projects/corefonts/) for the person installing them. Pass `--skip-mscorefonts` to leave that download out. The classic package does not include Calibri, Cambria, or Segoe UI.

A git clone of this repository does not include `ms-fonts/`, `fonts/microsoft/`, or fonts dropped into `additions/`. Those stay in the directory on disk. Copy that directory to the USB stick when a licensed computer should keep Calibri, Cambria, and Segoe UI. The clone still installs the open fonts.

## Classic core fonts from the distro

Ubuntu, Debian, and Arch can install the same classic core fonts with a package. The set is Andale Mono, Arial, Arial Black, Comic Sans MS, Courier New, Georgia, Impact, Times New Roman, Trebuchet MS, Verdana, and Webdings. The package downloads the fonts during install and asks you to accept the Microsoft core fonts EULA. It does not include Calibri, Cambria, Segoe UI, or Aptos.

Ubuntu and Pop!_OS, from the multiverse archive:

```bash
sudo apt install ttf-mscorefonts-installer
```

Package page: [ttf-mscorefonts-installer](https://packages.ubuntu.com/ttf-mscorefonts-installer)

Enable multiverse and update the package lists if apt cannot find the package. Pop!_OS uses this Ubuntu package.

Debian, from the contrib archive:

```bash
sudo apt install ttf-mscorefonts-installer
```

Package page: [ttf-mscorefonts-installer](https://packages.debian.org/ttf-mscorefonts-installer)

Enable the contrib component if apt cannot find the package.

Arch and CachyOS, from the AUR:

```bash
yay -S ttf-ms-fonts
```

Use `paru -S ttf-ms-fonts` when the machine has paru instead of yay.

Package page: [ttf-ms-fonts](https://aur.archlinux.org/packages/ttf-ms-fonts)

Arch wiki: [Microsoft fonts](https://wiki.archlinux.org/title/Microsoft_fonts)

The AUR package downloads the same SourceForge core-font installers. When that download fails, the wiki is the place to check. These packages are separate from `./install.sh`. The script still uses `ms-fonts/` when that folder is present.

Fonts you find later go in the `additions/` folder next to `install.sh`. The next run copies every `.ttf`, `.otf`, and `.ttc` in that folder into the menu under the name stored in the file. `uninstall.sh` does not delete that folder. A `private/` folder still works the same way.

Developers often add more mono faces than the default list. Those are in `fonts-coding/` and stay out of the menu until you ask for them:

```bash
./install.sh --coding
```

That adds Inconsolata, Victor Mono, Intel One Mono, Iosevka, Space Mono, Anonymous Pro, DM Mono, Red Hat Mono, Overpass Mono, Geist Mono, Commit Mono, Cousine, Fira Mono, JuliaMono, and Monaspace Neon, Argon, Xenon, Radon, and Krypton. `./install.sh --all` installs the same coding fonts. `./install.sh` without `--coding` or `--all` leaves them out.

## What stays in the word-processor list

On this machine the menu is 110 families. These are included on purpose:

- The usual Word and Pages names, including Calibri Light, Segoe UI Light, Segoe UI Semibold, and Arial Black. Word treats those as their own fonts.
- Google and Ubuntu faces used for reading and for code: Inter is listed as SF Pro, Nunito Sans as Avenir, League Spartan as Futura, EB Garamond as Garamond.
- Coding faces a terminal already expects: JetBrainsMono Nerd Font Mono, Cascadia Code, Cascadia Mono, Fira Code, Hack, Source Code Pro, IBM Plex Mono, Roboto Mono, PT Mono, Noto Sans Mono, Ubuntu Mono, and Ubuntu Sans Mono. Consolas is included with the Windows fonts.
- Desktop faces that belong to the system: Adwaita, Cantarell, DejaVu. LibreOffice's own OpenSymbol stays too.

Noto Sans is one row, and it draws the living scripts: Arabic, Hebrew, Devanagari, Bengali, Tamil, Khmer, Thai, Ethiopic, and the other scripts people still write. Italic cuts of those scripts are not published, so italic text uses the regular Noto Sans glyphs. Chinese, Japanese, and Korean stay on Noto Sans CJK SC. Emoji stays on Noto Color Emoji. Tibetan is drawn from Noto Serif, because that is the Tibetan face Noto publishes. The old per-script names (Noto Sans Arabic, Noto Sans Bengali, and the rest) are not separate rows.

The distro copies that used to flood the list are turned off by the folder they live in: the distro Noto set, WenQuanYi, Meslo, Fantasque Sans, and the extra Fira Code, Open Sans, and DejaVu weight files. The copies from this pack are the ones that draw.

## When the distro adds or changes a font

Running the script again replaces `~/.local/share/fonts/us-english` and the three `us-english` files in `~/.config/fontconfig/conf.d/`. It does not remove packages. It does not edit fonts that belong to LibreOffice, Wine, Calibre, Steam, SDDM, projectM, imlib2, or any other application.

The hide list names folders that are already known to flood the menu. A new file name inside one of those folders stays hidden, and the copy from this pack draws. A font the distro adds in any other folder stays available and can show up in the menu. The script does not hide a font it has not been told about, because that could turn off a face an application needs. After a large font update, run `./install.sh` again. If a duplicate name comes back, the check at the end says so, and the distro file is still on disk.

## Names a document can ask for

When the real Microsoft or Apple file is installed, that file is used. The open font is the fallback.

Same letter widths:

| Document asks for | Opens |
| --- | --- |
| Arial | Arial, or Liberation Sans |
| Times New Roman | Times New Roman, or Liberation Serif |
| Courier New | Courier New, or Liberation Mono |
| Calibri | Calibri, or Carlito |
| Cambria | Cambria, or Caladea |
| Georgia | Georgia, or Gelasio |
| Cambria Math | Cambria Math, or STIX Two Math |
| Segoe UI | Segoe UI, or Selawik |
| Consolas | Consolas, or Cascadia Mono |
| Helvetica, Helvetica Neue | TeX Gyre Heros |
| Helvetica Narrow, Arial Narrow | TeX Gyre Heros Cn |
| Times | TeX Gyre Termes |
| Palatino, Palatino Linotype, Book Antiqua | TeX Gyre Pagella |
| Bookman Old Style | TeX Gyre Bonum |
| Century Schoolbook | TeX Gyre Schola |
| Century Gothic, Avant Garde, ITC Avant Garde Gothic | TeX Gyre Adventor |
| Courier | TeX Gyre Cursor |
| ITC Zapf Chancery | TeX Gyre Chorus |

Close, not the same widths. The menu shows the name on the left:

| Menu name | File underneath |
| --- | --- |
| Garamond, Apple Garamond, ITC Garamond | EB Garamond |
| Aptos | Carlito (Calibri's widths, not Aptos's) |
| Futura | League Spartan |
| Avenir, Avenir Next | Nunito Sans |
| Gill Sans, Gill Sans MT | Gillius ADF No2 |
| Optima | Philosopher |
| Baskerville, Hoefler Text | Libre Baskerville |
| Baskerville Old Face | Bacasime Antique |
| Didot | GFS Didot |
| Lucida Grande | Lunasima |
| Lucida Handwriting | Lumanosimo |
| Lucida Calligraphy | Lugrasimo |
| Agency FB | Agdasima |
| Berlin Sans FB | Belanosima |
| Cooper Black | Caprasimo |
| SF Pro, San Francisco | Inter |
| New York | Source Serif 4 |
| Menlo, Monaco | DejaVu Sans Mono |

Asking for the open name still works. League Spartan, Inter, Nunito Sans, EB Garamond, and Carlito all resolve.

There is no honest stand-in for Copperplate, American Typewriter, or Wingdings, so those names are not aliased.

## Terminal icons and emoji

JetBrainsMono Nerd Font Mono contains the powerline and programming icons. It also answers to JetBrainsMono NFM. Symbols Nerd Font is the fallback when the current face has no icon for that codepoint. Adwaita Mono covers some of the same private-use icons, so a search that does not name a font may land on Adwaita Mono. A terminal set to JetBrainsMono Nerd Font Mono uses its own icons.

Noto Color Emoji is installed and is the emoji font. A few emoji, including U+1F600, are missing from fontconfig's character index, so a bare character search can land on DejaVu Sans. Choosing Noto Color Emoji, or an app that asks for the emoji font, uses the color file.

## Remove

```bash
./uninstall.sh
```

This deletes `~/.local/share/fonts/us-english` and the three `us-english` fontconfig files. It does not delete `fonts-backup-*` or `ms-fonts/`.

## Licenses

The open fonts in `fonts/` and `fonts-coding/` are redistributable. The license texts are in [`licenses/`](licenses/README.md). Copyright lines are stored inside each font file. Most of the text faces are SIL Open Font License. Ubuntu and Ubuntu Sans use the Ubuntu Font Licence. TeX Gyre uses the GUST font license. Gillius ADF No2 is GPL-2.0-or-later with the font exception. DejaVu and Hack include the Bitstream Vera terms. `D050000L` and Standard Symbols PS are the URW fonts under the AGPL-3.0 with the PostScript and PDF embedding exception. Noto Color Emoji is SIL Open Font License, taken from the Debian `fonts-noto-color-emoji` package.

Running `./install.sh` downloads the classic core fonts from the official corefonts archive under the Microsoft EULA when `ms-fonts/arial.ttf` is not already here. `--skip-mscorefonts` leaves them out.

`ms-fonts/` and `fonts/microsoft/` are a local copy for a machine that already has Windows or Microsoft 365. They are not in the git repository. Do not publish those folders. Each person uses their own licensed copies, the distro packages above, or Carlito, Caladea, and Selawik.
