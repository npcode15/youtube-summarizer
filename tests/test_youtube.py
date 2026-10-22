from youtube_summarizer.youtube import videos_from_api, videos_from_rss

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">
  <title>Example Channel</title>
  <entry>
    <id>yt:video:abc123</id>
    <yt:videoId>abc123</yt:videoId>
    <title>First video</title>
    <published>2026-10-21T14:00:00+00:00</published>
  </entry>
  <entry>
    <title>Entry without a video id</title>
  </entry>
</feed>
"""

ITEMS = [
    {
        "snippet": {
            "title": "Big video",
            "channelTitle": "Chan",
            "publishedAt": "2026-10-21T14:00:00Z",
        },
        "contentDetails": {"videoId": "v1", "videoPublishedAt": "2026-10-21T14:00:00Z"},
    },
    {
        "snippet": {"title": "Private video"},
        "contentDetails": {"videoId": "v2"},
    },
]
DETAILS = {
    "v1": {"contentDetails": {"duration": "PT38M12S"}, "snippet": {"liveBroadcastContent": "none"}},
}


def test_videos_from_rss_parses_entries_and_skips_malformed_ones():
    videos = videos_from_rss(RSS)
    assert len(videos) == 1
    assert videos[0].id == "abc123"
    assert videos[0].title == "First video"
    assert videos[0].channel == "Example Channel"
    assert videos[0].duration_sec is None


def test_videos_from_api_skips_private_videos_and_parses_duration():
    videos = videos_from_api(ITEMS, DETAILS)
    assert [v.id for v in videos] == ["v1"]
    assert videos[0].duration_sec == 2292
    assert videos[0].live == "none"
    assert videos[0].url == "https://www.youtube.com/watch?v=v1"
