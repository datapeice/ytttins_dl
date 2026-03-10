package me.datapeice.ytttins.database.repository;

import me.datapeice.ytttins.database.entity.ActiveUser;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface ActiveUserRepository extends JpaRepository<ActiveUser, Long> {

    boolean existsByUserIdAndDate(Long userId, String date);

    /** Returns distinct user IDs active since (inclusive) the given ISO date string. */
    @Query("SELECT DISTINCT a.userId FROM ActiveUser a WHERE a.date >= :since")
    List<Long> findDistinctUserIdsSince(@Param("since") String since);
}
