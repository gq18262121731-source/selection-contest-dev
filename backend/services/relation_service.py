from __future__ import annotations

from collections import OrderedDict

from backend.models.relation_model import FamilyRelationCreateRequest, FamilyRelationRecord
from backend.models.user_model import UserRole
from backend.services.user_service import UserService


class RelationService:
    """Stores elder-family relations separately from devices."""

    def __init__(self, user_service: UserService) -> None:
        self._user_service = user_service
        self._relations: OrderedDict[str, FamilyRelationRecord] = OrderedDict()

    def bind_family_to_elder(self, payload: FamilyRelationCreateRequest) -> FamilyRelationRecord:
        elder = self._require_user(payload.elder_user_id, expected_role=UserRole.ELDER)
        family = self._require_user(payload.family_user_id, expected_role=UserRole.FAMILY)
        if not elder or not family:
            raise ValueError("USER_NOT_FOUND")
        if self.has_relation(payload.elder_user_id, payload.family_user_id):
            raise ValueError("RELATION_ALREADY_EXISTS")
        if payload.is_primary:
            self._clear_primary(payload.elder_user_id)
        record = FamilyRelationRecord(
            elder_user_id=payload.elder_user_id,
            family_user_id=payload.family_user_id,
            relation_type=payload.relation_type.strip(),
            is_primary=payload.is_primary,
        )
        self._relations[record.id] = record
        return record

    def list_relations_by_elder(self, elder_user_id: str) -> list[FamilyRelationRecord]:
        return [relation for relation in self._relations.values() if relation.elder_user_id == elder_user_id]

    def list_relations_by_family(self, family_user_id: str) -> list[FamilyRelationRecord]:
        return [relation for relation in self._relations.values() if relation.family_user_id == family_user_id]

    def has_relation(self, elder_user_id: str, family_user_id: str) -> bool:
        return any(
            relation.elder_user_id == elder_user_id and relation.family_user_id == family_user_id
            for relation in self._relations.values()
        )

    def reset(self) -> None:
        self._relations.clear()

    def _clear_primary(self, elder_user_id: str) -> None:
        for relation_id, relation in list(self._relations.items()):
            if relation.elder_user_id == elder_user_id and relation.is_primary:
                self._relations[relation_id] = relation.model_copy(update={"is_primary": False})

    def _require_user(self, user_id: str, expected_role: UserRole):
        user = self._user_service.get_user(user_id)
        if user is None:
            raise ValueError("USER_NOT_FOUND")
        if user.role != expected_role:
            raise ValueError("INVALID_USER_ROLE")
        return user
