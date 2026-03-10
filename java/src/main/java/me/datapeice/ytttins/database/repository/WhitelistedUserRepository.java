package me.datapeice.ytttins.database.repository;

import me.datapeice.ytttins.database.entity.WhitelistedUser;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface WhitelistedUserRepository extends JpaRepository<WhitelistedUser, String> {
    boolean existsByUsername(String username);
}
