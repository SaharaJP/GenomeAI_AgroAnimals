package com.genomeai.agroanimals.mobile.domain

enum class Role {
    HerdManager,
    Veterinarian,
    ReproductionSpecialist,
    Viewer,
    Admin;

    companion object {
        fun fromServerValue(value: String?): Role = when ((value ?: "").trim()) {
            "Admin" -> Admin
            "Viewer" -> Viewer
            "Veterinarian" -> Veterinarian
            "ReproductionSpecialist" -> ReproductionSpecialist
            "Operator", "HerdManager" -> HerdManager
            else -> Viewer
        }
    }
}
