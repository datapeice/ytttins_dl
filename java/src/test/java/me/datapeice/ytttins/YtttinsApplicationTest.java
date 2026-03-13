package me.datapeice.ytttins;

import me.datapeice.ytttins.bot.TelegramBot;
import me.datapeice.ytttins.service.DownloaderService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.context.TestPropertySource;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Basic smoke test — verifies the Spring context loads and
 * core helper methods behave correctly.
 *
 * TelegramBot is mocked so the test doesn't require a real BOT_TOKEN
 * or a live connection to the Telegram API.
 */
@SpringBootTest
@TestPropertySource(properties = {
        "bot.token=1234567890:AAFakeTokenForTesting",
        "bot.admin-username=testadmin",
        "spring.datasource.url=jdbc:h2:mem:testdb;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.jpa.properties.hibernate.dialect=org.hibernate.dialect.H2Dialect"
})
class YtttinsApplicationTest {

    @MockBean
    TelegramBot telegramBot;

    @Autowired
    DownloaderService downloaderService;

    @Test
    void contextLoads() {
        assertNotNull(downloaderService);
    }

    @Test
    void getPlatformYouTube() {
        assertEquals("youtube", downloaderService.getPlatform("https://www.youtube.com/watch?v=dQw4w9WgXcQ"));
        assertEquals("youtube", downloaderService.getPlatform("https://youtu.be/dQw4w9WgXcQ"));
    }

    @Test
    void getPlatformTikTok() {
        assertEquals("tiktok", downloaderService.getPlatform("https://www.tiktok.com/@user/video/123"));
    }

    @Test
    void getPlatformInstagram() {
        assertEquals("instagram", downloaderService.getPlatform("https://www.instagram.com/reel/abc123/"));
    }

    @Test
    void getPlatformReddit() {
        assertEquals("reddit", downloaderService.getPlatform("https://www.reddit.com/r/videos/comments/abc/"));
        assertEquals("reddit", downloaderService.getPlatform("https://redd.it/abc"));
    }

    @Test
    void getPlatformTwitter() {
        assertEquals("twitter", downloaderService.getPlatform("https://twitter.com/user/status/123"));
        assertEquals("twitter", downloaderService.getPlatform("https://x.com/user/status/123"));
    }

    @Test
    void getPlatformUnknown() {
        assertEquals("unknown", downloaderService.getPlatform("not-a-url"));
    }

    @Test
    void isYouTubeMusicDetectsCorrectly() {
        assertTrue(downloaderService.isYoutubeMusic("https://music.youtube.com/watch?v=abc"));
        assertFalse(downloaderService.isYoutubeMusic("https://www.youtube.com/watch?v=abc"));
    }
}
