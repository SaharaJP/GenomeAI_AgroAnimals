package com.genomeai.agroanimals.mobile.navigation

import com.genomeai.agroanimals.mobile.domain.MobileDestination
import com.genomeai.agroanimals.mobile.domain.MobileNavigationPolicy
import com.genomeai.agroanimals.mobile.domain.Role

object RoleAwareNavigation {
    fun routes(role: Role): List<String> = MobileNavigationPolicy.allowedDestinations(role).map {
        when (it) {
            MobileDestination.TodayWorklists -> AppDestinations.TodayWorklists
            MobileDestination.AlertsNow -> AppDestinations.AlertsNow
            MobileDestination.QuickAnimalCard -> AppDestinations.QuickAnimalCard
            MobileDestination.QuickEventEntry -> AppDestinations.QuickEventEntry
            MobileDestination.TaskCompletion -> AppDestinations.TaskCompletion
            MobileDestination.ShiftHandover -> AppDestinations.ShiftHandover
        }
    }
}
