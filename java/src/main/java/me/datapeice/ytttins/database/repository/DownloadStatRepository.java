package me.datapeice.ytttins.database.repository;

import me.datapeice.ytttins.database.entity.DownloadStat;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface DownloadStatRepository extends JpaRepository<DownloadStat, String> {
}
