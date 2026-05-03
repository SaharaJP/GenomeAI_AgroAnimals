package com.genomeai.agroanimals.mobile.data.local.sync

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Dao
interface SyncIncidentDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(entity: SyncIncidentEntity)

    @Query("SELECT * FROM sync_incidents ORDER BY occurredAtIso DESC")
    suspend fun listAll(): List<SyncIncidentEntity>
}
