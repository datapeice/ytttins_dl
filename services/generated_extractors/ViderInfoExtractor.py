import re
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import (
    ExtractorError,
    int_or_none,
    str_or_none,
    url_or_none,
    unified_strdate,
)


class ViderInfoIE(InfoExtractor):
    IE_NAME = 'vider.info'
    # The video ID may start with '+', so [^/?#\s]+ is used instead of \w+
    _VALID_URL = r'https?://vider\.info/vid/(?P<id>[^/?#\s]+)'
    _TESTS = [
        {
            'url': 'https://vider.info/vid/+femmsv5',
            'info_dict': {
                'id': '+femmsv5',
                'ext': 'mp4',
                'title': str,
            },
        },
    ]

    def _real_extract(self, url):
        video_id = self._match_id(url)

        # 1. Try JSON API endpoint
        api_url = f'https://vider.info/api/video/{video_id}'
        data = self._download_json(
            api_url, video_id, fatal=False,
            headers={'Referer': url, 'X-Requested-With': 'XMLHttpRequest'},
            note='Fetching video metadata from API',
        )
        if data and (data.get('url') or data.get('sources') or data.get('file')):
            result = self._build_info_from_api(video_id, data)
            if result:
                return result

        # 2. Scrape the video page
        webpage = self._download_webpage(url, video_id)

        # 2a. JSON config in script tag (JW Player / generic)
        for json_pattern in [
            r'var\s+(?:videoConfig|playerConfig|config|video)\s*=\s*(\{[^<]+\})',
            r'jwplayer\s*\([^)]*\)\s*\.setup\s*\(\s*(\{[^<]+\})',
            r'data-config=(?:\'|")(\{[^"\']+\})(?:\'|")',
        ]:
            json_str = self._search_regex(json_pattern, webpage, 'video config', default=None)
            if json_str:
                cfg = self._parse_json(json_str, video_id, fatal=False)
                if cfg:
                    result = self._build_info_from_config(video_id, cfg, webpage)
                    if result:
                        return result

        # 2b. sources array in JS
        sources_str = self._search_regex(
            r'sources\s*:\s*\[([^\]]+)\]', webpage, 'sources', default=None,
        )
        if sources_str:
            video_url = self._search_regex(
                r'(?:file|src)\s*:\s*["\']([^"\']+\.(?:mp4|m3u8|webm)(?:[^"\']*)?)["\']',
                sources_str, 'video url', default=None,
            )
            if video_url:
                return {
                    'id': video_id,
                    'title': self._og_search_title(webpage, default=video_id),
                    'url': video_url,
                    'thumbnail': self._og_search_thumbnail(webpage),
                    'description': self._og_search_description(webpage),
                }

        # 2c. Direct <source> / JS patterns
        video_url = self._search_regex(
            [
                r'<source[^>]+src=["\']([^"\']+\.(?:mp4|m3u8|webm)(?:[^"\']*)?)["\']',
                r'(?:file|url)\s*[:=]\s*["\']([^"\']+\.(?:mp4|m3u8|webm)(?:[^"\']*)?)["\']',
                r'(?:videoUrl|video_url|mediaUrl)\s*[:=]\s*["\']([^"\']+)["\']',
            ],
            webpage, 'video url', default=None,
        )
        if video_url:
            return {
                'id': video_id,
                'title': self._og_search_title(webpage, default=video_id),
                'url': video_url,
                'thumbnail': self._og_search_thumbnail(webpage),
                'description': self._og_search_description(webpage),
            }

        # 2d. og:video meta tag
        og_video = self._og_search_video_url(webpage, default=None)
        if og_video:
            return {
                'id': video_id,
                'title': self._og_search_title(webpage, default=video_id),
                'url': og_video,
                'thumbnail': self._og_search_thumbnail(webpage),
                'description': self._og_search_description(webpage),
            }

        raise ExtractorError(
            'Unable to extract video URL from vider.info', expected=True,
        )

    def _build_info_from_api(self, video_id, data):
        formats = []

        for src in data.get('sources') or []:
            src_url = url_or_none(src.get('file') or src.get('src') or src.get('url'))
            if not src_url:
                continue
            label = str_or_none(src.get('label') or src.get('quality') or '')
            height = int_or_none(self._search_regex(
                r'(\d+)[pP]', label, 'height', default=None,
            )) if label else None
            is_hls = 'm3u8' in src_url
            fmt = {
                'url': src_url,
                'ext': 'm3u8' if is_hls else 'mp4',
                'format_id': label or None,
                'height': height,
            }
            if is_hls:
                fmt['protocol'] = 'm3u8_native'
            formats.append(fmt)

        direct_url = url_or_none(data.get('url') or data.get('file'))
        if not formats and direct_url:
            formats.append({'url': direct_url})

        if not formats:
            return None

        return {
            'id': video_id,
            'title': str_or_none(data.get('title') or data.get('name')) or video_id,
            'description': str_or_none(data.get('description')),
            'thumbnail': url_or_none(
                data.get('thumbnail') or data.get('image') or data.get('poster')
            ),
            'duration': int_or_none(data.get('duration')),
            'upload_date': unified_strdate(
                str_or_none(data.get('upload_date') or data.get('created_at'))
            ),
            'view_count': int_or_none(data.get('views') or data.get('view_count')),
            'formats': formats,
        }

    def _build_info_from_config(self, video_id, cfg, webpage):
        if isinstance(cfg.get('playlist'), list) and cfg['playlist']:
            item = cfg['playlist'][0]
            sources = item.get('sources') or []
            title = str_or_none(item.get('title')) or self._og_search_title(webpage, default=video_id)
            image = url_or_none(item.get('image')) or self._og_search_thumbnail(webpage)
        else:
            sources = cfg.get('sources') or []
            title = str_or_none(cfg.get('title')) or self._og_search_title(webpage, default=video_id)
            image = url_or_none(cfg.get('image') or cfg.get('poster')) or self._og_search_thumbnail(webpage)

        formats = []
        for src in sources:
            src_url = url_or_none(src.get('file') or src.get('src') or src.get('url'))
            if not src_url:
                continue
            label = str_or_none(src.get('label') or '')
            height = int_or_none(self._search_regex(
                r'(\d+)[pP]', label, 'height', default=None,
            )) if label else None
            is_hls = 'm3u8' in src_url
            fmt = {
                'url': src_url,
                'ext': 'm3u8' if is_hls else 'mp4',
                'format_id': label or None,
                'height': height,
            }
            if is_hls:
                fmt['protocol'] = 'm3u8_native'
            formats.append(fmt)

        if not formats:
            direct = url_or_none(cfg.get('file') or cfg.get('url'))
            if direct:
                formats.append({'url': direct})

        if not formats:
            return None

        return {
            'id': video_id,
            'title': title,
            'thumbnail': image,
            'formats': formats,
        }
