# Neo YT Downloader

A little desktop app for downloading YouTube videos, built with Python and yt-dlp. I wanted something that didn't look like every other Tkinter app from 2009, so it's styled in a neo-brutalist look — thick black borders, hard shadows, no gradients, no rounded corners.

<img width="400" height="500" alt="Screenshot 2026-08-24 at 9 31 01 PM" src="https://github.com/user-attachments/assets/3f16de3c-0a42-449d-8244-9c5648a6c247" />


## What it does

- Paste a link, hit fetch, and it pulls the title, channel, duration, and thumbnail before you download anything
- Download video+audio, video only, or audio only as MP3
- Picks up the actual resolutions available for that video instead of a fixed list
- Works on playlists too, if you want the whole thing
- Shows live progress with speed and ETA, and you can cancel mid-download
- Keeps a history of what you've downloaded and where, with a button to jump straight to the folder

## Before you install

You'll need Python 3.9+ and FFmpeg. FFmpeg does the heavy lifting of merging video and audio streams and converting to MP3, and the app won't work right without it.

- **Windows:** grab a build from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) and add the `bin` folder to your PATH
- **Mac:** `brew install ffmpeg`
- **Linux:** `sudo apt install ffmpeg` (or whatever your distro's package manager is)

Run `ffmpeg -version` in a terminal after installing — if it prints a version number you're good.

## Setup

```bash
git clone https://github.com/keshxvv21/Neo-Youtube-Downloader.git
cd Neo-Youtube-Downloader
pip install -r requirements.txt
python youtube_downloader.py
```

That's it, no build step or config file to mess with.

## Using it

1. Paste a YouTube link (or hit the paste button)
2. Click "Fetch Info" to see what you're about to download
3. Pick a mode — video+audio, video only, or audio only
4. Pick a quality if you want something other than "best available"
5. Hit download and watch the progress bar do its thing

Your download history lives in a small JSON file in your home folder (`.ytdl_neo_history.json`), not in the repo, so it won't get committed by accident.

## A quick note on how you use this

This is meant for downloading stuff you have the rights to — your own uploads, content that's Creative Commons licensed, or videos you're just keeping a personal copy of. It's not built or intended to help anyone rip and redistribute other people's work. Respect the actual creators.

## Known rough edges

- YouTube changes things fairly often, and yt-dlp usually catches up within a day or two. If downloads suddenly start failing, run `pip install -U yt-dlp` first — that fixes it almost every time
- Very long playlists can take a while, there's no batch/parallel downloading yet
- No cookie/login support yet, so age-restricted or private videos won't work

## Contributing

If you find a bug or want to add something, open an issue or just send a PR. Nothing formal here.

## License

MIT 
