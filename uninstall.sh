#!/usr/bin/env bash
# Remove the fonts and fontconfig files this installer added.
# Does not delete ~/.local/share/fonts-backup-* or the ms-fonts folder.
set -euo pipefail
FONT_DIR="${HOME}/.local/share/fonts/us-english"
CONF_DIR="${HOME}/.config/fontconfig/conf.d"
rm -rf "$FONT_DIR"
rm -f \
  "$CONF_DIR/60-us-english-aliases.conf" \
  "$CONF_DIR/61-us-english-menu.conf" \
  "$CONF_DIR/62-us-english-names.conf"
if command -v fc-cache >/dev/null; then
  fc-cache -f
fi
echo "Removed $FONT_DIR and the us-english fontconfig snippets."
echo "Distro packages, application fonts, additions/, and fonts-backup directories were left in place."
