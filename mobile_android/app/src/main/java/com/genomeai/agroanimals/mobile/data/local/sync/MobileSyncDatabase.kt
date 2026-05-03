package com.genomeai.agroanimals.mobile.data.local.sync

import androidx.room.Database
import androidx.room.RoomDatabase

@Database(
    entities = [SyncQueueEntity::class, SyncIncidentEntity::class],
    version = 1,
    exportSchema = false,
)
abstract class MobileSyncDatabase : RoomDatabase() {
    abstract fun syncQueueDao(): SyncQueueDao
    abstract fun syncIncidentDao(): SyncIncidentDao
}
