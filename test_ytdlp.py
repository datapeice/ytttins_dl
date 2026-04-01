import yt_dlp

def test_search(prefix, query):
    ydl_opts = {'quiet': True, 'extract_flat': True, 'noplaylist': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(f"{prefix}{query}", download=False)
            if 'entries' in info:
                for entry in info['entries'][:1]:
                    print(f"{prefix} found: {entry.get('title')} ({entry.get('url')})")
            else:
                print(f"{prefix} found: {info.get('title')} ({info.get('url')})")
        except Exception as e:
            print(f"{prefix} error: {e}")

test_search("vksearch1:", "Never Gonna Give You Up")
test_search("scsearch1:", "Never Gonna Give You Up")
test_search("ytsearch1:", "Never Gonna Give You Up")
