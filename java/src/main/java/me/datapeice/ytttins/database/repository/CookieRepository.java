package me.datapeice.ytttins.database.repository;

import me.datapeice.ytttins.database.entity.BotCookie;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface CookieRepository extends JpaRepository<BotCookie, Long> {
}
