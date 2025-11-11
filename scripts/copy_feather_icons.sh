#!/usr/bin/env bash

# Copy the Feather icons required by Ghost Files Finder into the project resources
# directory. Adjust the icon list as the toolbar or UI grows.

set -euo pipefail

SRC_DIR="/Users/rich/temp/feather-icons/node_modules/feather-icons/dist/icons"
DEST_DIR="/Users/rich/dev/github/richlewis007/show-excluded-and-ignored/src/rfe/resources/icons/feather"
TARGET_STROKE_WIDTH="1.3"

ICONS=(
  "delete.svg"
  "folder.svg"
  "x-circle.svg"
)

  # "play.svg"
  # "refresh-ccw.svg"
  # "folder.svg"
  # "file-text.svg"
  # "trash-2.svg"
  # "download.svg"
  # "log-out.svg"
  # "chevrons-down.svg"
  # "chevrons-up.svg"
  # "external-link.svg"
  # "pause.svg"
  # "square.svg"
  # "tag.svg"

if [[ ! -d "$SRC_DIR" ]]; then
  echo "Source directory not found: $SRC_DIR" >&2
  exit 1
fi

mkdir -p "$DEST_DIR"

for icon in "${ICONS[@]}"; do
  if [[ ! -f "$SRC_DIR/$icon" ]]; then
    echo "Missing icon in source directory: $icon" >&2
    exit 1
  fi
  cp -f "$SRC_DIR/$icon" "$DEST_DIR/$icon"
  echo "Copied $icon"
done

export DEST_DIR TARGET_STROKE_WIDTH

python - <<'PY'
import os
from pathlib import Path
from xml.etree import ElementTree as ET

dest_dir = Path(os.environ["DEST_DIR"])
target_stroke = os.environ["TARGET_STROKE_WIDTH"]

for svg_path in dest_dir.glob("*.svg"):
    tree = ET.parse(svg_path)
    root = tree.getroot()
    changed = False

    for element in root.iter():
        value = element.attrib.get("stroke-width")
        if value and value != target_stroke:
            element.attrib["stroke-width"] = target_stroke
            changed = True

    if changed:
        tree.write(svg_path, encoding="utf-8", xml_declaration=True)

PY

echo "Feather icons copied to $DEST_DIR with stroke width adjusted to ${TARGET_STROKE_WIDTH}"
