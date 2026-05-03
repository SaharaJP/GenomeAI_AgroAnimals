package com.genomeai.agroanimals.mobile.api

data class TodayWorklistItemDto(
    val id: String,
    val title: String,
    val dueLabel: String,
    val linkedAnimalId: String?,
    val linkedSiteId: String?,
    val priority: String,
    val explainabilityHint: String?,
)

data class AlertNowDto(
    val id: String,
    val title: String,
    val severity: String,
    val linkedAnimalId: String?,
    val linkedSiteId: String?,
    val reasonCodes: List<String>,
)

data class QuickAnimalCardDto(
    val animalId: String,
    val farmId: String,
    val siteId: String?,
    val status: String,
    val parity: Int?,
    val lactationStage: String?,
    val currentAlertCount: Int,
)

data class ObjectLinkageDto(
    val objectType: String,
    val objectId: String,
    val objectVersion: String? = null,
)

data class TaskWorklistOwnershipDto(
    val taskId: String? = null,
    val worklistId: String? = null,
    val ownerUserId: String? = null,
    val ownerRole: String? = null,
)

data class HandoverDto(
    val handoverId: String? = null,
    val shiftLabel: String? = null,
)

data class QuickEventEntryPayload(
    val animalId: String,
    val eventType: String,
    val occurredAtIso: String,
    val notes: String?,
    val objectLinkage: ObjectLinkageDto,
    val ownership: TaskWorklistOwnershipDto? = null,
)

data class TaskCompletionPayload(
    val taskId: String,
    val outcome: String,
    val notes: String?,
    val objectLinkage: ObjectLinkageDto,
    val ownership: TaskWorklistOwnershipDto,
    val handover: HandoverDto? = null,
)

data class ShiftHandoverPayload(
    val handoverId: String,
    val shiftLabel: String,
    val summary: String,
    val blockers: List<String>,
    val ownership: TaskWorklistOwnershipDto? = null,
    val objectLinkage: ObjectLinkageDto? = null,
)

data class FeedbackSubmissionPayload(
    val targetType: String,
    val targetId: String,
    val status: String,
    val comment: String?,
    val objectLinkage: ObjectLinkageDto,
    val ownership: TaskWorklistOwnershipDto? = null,
)

data class AssistantLinkedActionPayload(
    val assistantActionId: String,
    val actionType: String,
    val targetObjectType: String,
    val targetObjectId: String,
    val notes: String?,
    val objectLinkage: ObjectLinkageDto,
    val ownership: TaskWorklistOwnershipDto? = null,
    val handover: HandoverDto? = null,
)
