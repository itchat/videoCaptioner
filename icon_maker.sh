#!/bin/bash

# Function to convert SVG to ICNS
svg_to_icns() {
    local RESOLUTIONS=(
        16,16x16
        32,16x16@2x
        32,32x32
        64,32x32@2x
        128,128x128
        256,128x128@2x
        256,256x256
        512,256x256@2x
        512,512x512
        1024,512x512@2x
    )

    for SVG in "$@"; do
        BASE=$(basename "$SVG" | sed 's/\.[^\.]*$//')
        ICONSET="$BASE.iconset"
        ICONSET_DIR="./icons/$ICONSET"
        mkdir -p "$ICONSET_DIR"
        for RES in "${RESOLUTIONS[@]}"; do
            SIZE=$(echo $RES | cut -d, -f1)
            LABEL=$(echo $RES | cut -d, -f2)
            svg2png -w $SIZE -h $SIZE "$SVG" "$ICONSET_DIR"/icon_$LABEL.png
        done

        iconutil -c icns "$ICONSET_DIR"
    done
}

# Check if svg2png and iconutil are installed
if ! command -v svg2png &> /dev/null || ! command -v iconutil &> /dev/null; then
    echo "Error: svg2png or iconutil is not installed."
    exit 1
fi

# Call the function with the provided SVG files
svg_to_icns "$@"

