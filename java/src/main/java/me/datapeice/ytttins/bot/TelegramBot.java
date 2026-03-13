package me.datapeice.ytttins.bot;

import me.datapeice.ytttins.config.BotConfig;
import me.datapeice.ytttins.handler.AdminHandler;
import me.datapeice.ytttins.handler.UserHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.telegram.telegrambots.bots.TelegramLongPollingBot;
import org.telegram.telegrambots.meta.TelegramBotsApi;
import org.telegram.telegrambots.meta.api.methods.send.SendMessage;
import org.telegram.telegrambots.meta.api.objects.Update;
import org.telegram.telegrambots.meta.exceptions.TelegramApiException;
import org.telegram.telegrambots.updatesreceivers.DefaultBotSession;

import jakarta.annotation.PostConstruct;

/**
 * Core Telegram bot — routes incoming updates to {@link UserHandler} and
 * {@link AdminHandler}.
 *
 * <p>Uses long-polling mode ({@link TelegramLongPollingBot}) for simplicity.
 * For production webhook mode the same handler methods can be wired into a
 * {@code TelegramWebhookBot} subclass — the business logic is identical.
 *
 * <p>Equivalent to the bot setup inside {@code main.py} in the Python version.
 */
@Component
public class TelegramBot extends TelegramLongPollingBot {

    private static final Logger log = LoggerFactory.getLogger(TelegramBot.class);

    private final BotConfig config;
    private final UserHandler userHandler;
    private final AdminHandler adminHandler;

    public TelegramBot(BotConfig config, UserHandler userHandler, AdminHandler adminHandler) {
        super(config.getBotToken());
        this.config = config;
        this.userHandler = userHandler;
        this.adminHandler = adminHandler;
    }

    // ─── Bot identity ─────────────────────────────────────────────────────────────

    @Override
    public String getBotUsername() {
        // Telegram does not require the username for long-polling; return a placeholder.
        return "ytttins_dl_bot";
    }

    // ─── Registration ─────────────────────────────────────────────────────────────

    @PostConstruct
    public void register() {
        try {
            TelegramBotsApi botsApi = new TelegramBotsApi(DefaultBotSession.class);
            botsApi.registerBot(this);
            log.info("🚀 Bot registered in long-polling mode");
        } catch (TelegramApiException e) {
            log.error("Failed to register bot: {}", e.getMessage(), e);
            throw new RuntimeException(e);
        }
    }

    // ─── Update dispatch ─────────────────────────────────────────────────────────

    @Override
    public void onUpdateReceived(Update update) {
        try {
            if (update.hasCallbackQuery()) {
                String data = update.getCallbackQuery().getData();
                if (data != null && data.startsWith("admin:")) {
                    adminHandler.handleCallback(this, update.getCallbackQuery());
                } else {
                    userHandler.handleCallback(this, update.getCallbackQuery());
                }
            } else if (update.hasMessage() && update.getMessage().hasText()) {
                String text = update.getMessage().getText();
                String username = update.getMessage().getFrom().getUserName();

                if (isAdminCommand(text) && isAdmin(username)) {
                    adminHandler.handleMessage(this, update.getMessage());
                } else {
                    userHandler.handleMessage(this, update.getMessage());
                }
            } else if (update.hasMessage() && update.getMessage().hasDocument()) {
                // Cookie upload from admin
                String username = update.getMessage().getFrom().getUserName();
                if (isAdmin(username)) {
                    adminHandler.handleDocument(this, update.getMessage());
                }
            }
        } catch (Exception e) {
            log.error("Unhandled error processing update: {}", e.getMessage(), e);
        }
    }

    // ─── Helpers ─────────────────────────────────────────────────────────────────

    private boolean isAdmin(String username) {
        return username != null && username.equalsIgnoreCase(config.getAdminUsername());
    }

    private boolean isAdminCommand(String text) {
        return text.startsWith("/panel")
                || text.startsWith("/whitelist")
                || text.startsWith("/unwhitelist");
    }

    /**
     * Convenience method — executes {@link SendMessage} and swallows checked exceptions,
     * logging them instead (mirrors the Python {@code await message.answer(...)} pattern).
     */
    public void sendText(long chatId, String text) {
        SendMessage msg = new SendMessage(String.valueOf(chatId), text);
        try {
            execute(msg);
        } catch (TelegramApiException e) {
            log.error("Failed to send message to {}: {}", chatId, e.getMessage());
        }
    }
}
