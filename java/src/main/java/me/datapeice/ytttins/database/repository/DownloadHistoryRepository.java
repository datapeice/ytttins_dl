package me.datapeice.ytttins.database.repository;

import me.datapeice.ytttins.database.entity.DownloadHistory;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface DownloadHistoryRepository extends JpaRepository<DownloadHistory, Long> {

    Page<DownloadHistory> findAll(Pageable pageable);

    /** Returns the most-recent username associated with the given Telegram user ID. */
    Optional<DownloadHistory> findFirstByUserIdOrderByTimestampDesc(Long userId);

    /** Returns all distinct user IDs that have at least one download record. */
    @Query("SELECT DISTINCT h.userId FROM DownloadHistory h WHERE h.userId IS NOT NULL")
    List<Long> findDistinctUserIds();
}
