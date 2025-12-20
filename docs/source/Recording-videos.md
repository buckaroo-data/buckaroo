vertical
735/900


https://ezgif.com/video-to-gif?err=expired



ffmpeg -i $InPattern -vf "palettegen" palette.png

ffmpeg -framerate 24 -i $InPattern -i palette.png -lavfi "paletteuse" $Output
