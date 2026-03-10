package me.datapeice.ytttins;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * Entry point for the Telegram media-downloader bot (Java rewrite).
 *
 * <p>Equivalent to {@code main.py} in the Python version.
 *
 * <p>The bot supports two operation modes:
 * <ul>
 *   <li><b>Webhook</b> – production mode; Telegram pushes updates to an HTTPS endpoint.</li>
 *   <li><b>Long-polling</b> – development/fallback mode; the bot polls Telegram for updates.</li>
 * </ul>
 *
 * <p>The active mode is selected via {@code bot.webhook-host} in {@code application.yml}
 * (or the {@code WEBHOOK_HOST} environment variable).  When the value is blank the bot
 * automatically falls back to long-polling.
 */
@SpringBootApplication
@EnableScheduling
public class YtttinsApplication {

    public static void main(String[] args) {
        SpringApplication.run(YtttinsApplication.class, args);
    }
}
