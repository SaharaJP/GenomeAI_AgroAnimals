package com.genomeai.agroanimals.mobile.data.local.sync

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Dao
interface SyncQueueDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: SyncQueueEntity)

    @Query("SELECT * FROM sync_queue WHERE id = :id LIMIT 1")
    suspend fun findById(id: String): SyncQueueEntity?

    @Query("SELECT * FROM sync_queue ORDER BY id ASC")
    suspend fun listAll(): List<SyncQueueEntity>
}
