package com.genomeai.agroanimals.mobile.domain

object MobileNavigationPolicy {
    fun allowedDestinations(role: Role): Set<MobileDestination> = when (role) {
        Role.HerdManager -> setOf(
            MobileDestination.TodayWorklists,
            MobileDestination.AlertsNow,
            MobileDestination.QuickAnimalCard,
            MobileDestination.QuickEventEntry,
            MobileDestination.TaskCompletion,
            MobileDestination.ShiftHandover,
        )
        Role.Veterinarian -> setOf(
            MobileDestination.TodayWorklists,
            MobileDestination.AlertsNow,
            MobileDestination.QuickAnimalCard,
            MobileDestination.QuickEventEntry,
            MobileDestination.TaskCompletion,
            MobileDestination.ShiftHandover,
        )
        Role.ReproductionSpecialist -> setOf(
            MobileDestination.TodayWorklists,
            MobileDestination.AlertsNow,
            MobileDestination.QuickAnimalCard,
            MobileDestination.QuickEventEntry,
            MobileDestination.TaskCompletion,
            MobileDestination.ShiftHandover,
        )
        Role.Viewer -> setOf(
            MobileDestination.TodayWorklists,
            MobileDestination.AlertsNow,
            MobileDestination.QuickAnimalCard,
            MobileDestination.ShiftHandover,
        )
        Role.Admin -> MobileDestination.entries.toSet()
    }
}
