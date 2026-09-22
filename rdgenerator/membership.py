import re
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.core.signing import salted_hmac
from django.db import transaction
from django.utils import timezone

from .models import ActivationCode, UserEntitlement


ACTIVATION_CODE_SALT = "rdgenerator.membership.activation-code.v1"
CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
PLAN_PREFIXES = {
    ActivationCode.PLAN_SINGLE: "1X",
    ActivationCode.PLAN_THREE_DAY: "3D",
    ActivationCode.PLAN_WEEK: "7D",
    ActivationCode.PLAN_MONTH: "30D",
    ActivationCode.PLAN_LIFETIME: "LIFE",
}
PLAN_DURATIONS = {
    ActivationCode.PLAN_THREE_DAY: 3,
    ActivationCode.PLAN_WEEK: 7,
    ActivationCode.PLAN_MONTH: 30,
}


class ActivationCodeError(Exception):
    """Expected, user-facing activation failure."""


class InvalidActivationCode(ActivationCodeError):
    pass


class ActivationCodeUnavailable(ActivationCodeError):
    pass


class MembershipPlanConflict(ActivationCodeError):
    pass


@dataclass(frozen=True)
class GeneratedActivationCode:
    raw_code: str
    activation_code: ActivationCode


@dataclass(frozen=True)
class ActivationResult:
    activation_code: ActivationCode
    entitlement: UserEntitlement
    message: str


def normalize_activation_code(raw_code):
    return re.sub(r"[^A-Z0-9]", "", (raw_code or "").upper())


def activation_code_digest(raw_code):
    normalized = normalize_activation_code(raw_code)
    if not normalized:
        return ""
    return salted_hmac(
        ACTIVATION_CODE_SALT,
        normalized,
        algorithm="sha256",
    ).hexdigest()


def _new_raw_code(plan):
    prefix = PLAN_PREFIXES[plan]
    payload = "".join(secrets.choice(CODE_ALPHABET) for _ in range(16))
    groups = "-".join(payload[index : index + 4] for index in range(0, 16, 4))
    return f"RD-{prefix}-{groups}"


def generate_activation_codes(*, plan, quantity, created_by, batch_label=""):
    valid_plans = {value for value, _label in ActivationCode.PLAN_CHOICES}
    if plan not in valid_plans:
        raise ValueError("Unsupported activation-code plan")
    if not 1 <= int(quantity) <= 100:
        raise ValueError("Activation-code quantity must be between 1 and 100")

    generated = []
    seen_hashes = set()
    with transaction.atomic():
        while len(generated) < int(quantity):
            raw_code = _new_raw_code(plan)
            code_hash = activation_code_digest(raw_code)
            if code_hash in seen_hashes or ActivationCode.objects.filter(
                code_hash=code_hash
            ).exists():
                continue
            seen_hashes.add(code_hash)
            activation_code = ActivationCode.objects.create(
                code_hash=code_hash,
                code_hint=normalize_activation_code(raw_code)[-4:],
                plan=plan,
                batch_label=(batch_label or "").strip(),
                created_by=created_by,
            )
            generated.append(
                GeneratedActivationCode(
                    raw_code=raw_code,
                    activation_code=activation_code,
                )
            )
    return generated


def _switch_to_count_plan(entitlement):
    entitlement.expiration_mode = UserEntitlement.EXPIRATION_COUNT
    entitlement.expires_at = None
    entitlement.generation_limit = 1
    entitlement.generations_used = 0
    entitlement.reserved_generations = 0


def _grant_single_generation(entitlement, now):
    if entitlement.expiration_mode == UserEntitlement.EXPIRATION_TIME:
        if entitlement.expires_at is None or entitlement.expires_at > now:
            raise MembershipPlanConflict(
                "当前有效期会员已包含不限次数生成，请在会员到期后再使用次卡。"
            )
        _switch_to_count_plan(entitlement)
        return

    floor = entitlement.generations_used + entitlement.reserved_generations
    current_limit = max(entitlement.generation_limit or floor, floor)
    entitlement.generation_limit = current_limit + 1
    entitlement.expires_at = None


def _grant_duration(entitlement, days, now):
    if entitlement.expiration_mode == UserEntitlement.EXPIRATION_COUNT:
        if entitlement.reserved_generations:
            raise MembershipPlanConflict(
                "当前还有构建中的次数任务，请等待任务结束后再兑换时长卡。"
            )
        if (entitlement.remaining_generations or 0) > 0:
            raise MembershipPlanConflict(
                "当前次卡仍有剩余次数，请使用完后再兑换时长卡。"
            )
        entitlement.expiration_mode = UserEntitlement.EXPIRATION_TIME
        entitlement.generation_limit = None
        entitlement.generations_used = 0
        entitlement.reserved_generations = 0
        base_time = now
    else:
        if entitlement.expires_at is None:
            raise MembershipPlanConflict("当前账号已是终身会员，无需再兑换时长卡。")
        base_time = max(entitlement.expires_at, now)
    entitlement.expires_at = base_time + timedelta(days=days)


def _grant_lifetime(entitlement):
    if (
        entitlement.expiration_mode == UserEntitlement.EXPIRATION_TIME
        and entitlement.expires_at is None
    ):
        raise MembershipPlanConflict("当前账号已经是终身会员。")
    if (
        entitlement.expiration_mode == UserEntitlement.EXPIRATION_COUNT
        and entitlement.reserved_generations
    ):
        raise MembershipPlanConflict(
            "当前还有构建中的次数任务，请等待任务结束后再兑换终身卡。"
        )
    entitlement.expiration_mode = UserEntitlement.EXPIRATION_TIME
    entitlement.expires_at = None
    entitlement.generation_limit = None
    entitlement.generations_used = 0
    entitlement.reserved_generations = 0


def redeem_activation_code(*, user, raw_code, now=None):
    code_hash = activation_code_digest(raw_code)
    if not code_hash:
        raise InvalidActivationCode("请输入有效的激活码。")
    now = now or timezone.now()

    with transaction.atomic():
        try:
            activation_code = (
                ActivationCode.objects.select_for_update()
                .select_related("redeemed_by")
                .get(code_hash=code_hash)
            )
        except ActivationCode.DoesNotExist as exc:
            raise InvalidActivationCode("激活码无效，请检查后重试。") from exc

        if activation_code.redeemed_at:
            raise ActivationCodeUnavailable("该激活码已经使用。")
        if activation_code.revoked_at:
            raise ActivationCodeUnavailable("该激活码已作废。")

        entitlement, _created = UserEntitlement.objects.get_or_create(
            user=user,
            defaults={"expiration_mode": UserEntitlement.EXPIRATION_COUNT},
        )
        entitlement = UserEntitlement.objects.select_for_update().get(
            pk=entitlement.pk
        )

        if activation_code.plan == ActivationCode.PLAN_SINGLE:
            _grant_single_generation(entitlement, now)
            message = "激活成功，已增加 1 次生成额度。"
        elif activation_code.plan in PLAN_DURATIONS:
            days = PLAN_DURATIONS[activation_code.plan]
            _grant_duration(entitlement, days, now)
            local_expiry = timezone.localtime(entitlement.expires_at)
            message = (
                f"激活成功，会员已增加 {days} 天，有效期至 "
                f"{local_expiry:%Y-%m-%d %H:%M}。"
            )
        elif activation_code.plan == ActivationCode.PLAN_LIFETIME:
            _grant_lifetime(entitlement)
            message = "激活成功，当前账号已升级为终身会员。"
        else:
            raise InvalidActivationCode("激活码套餐无效，请联系管理员。")

        entitlement.save(
            update_fields=[
                "expiration_mode",
                "expires_at",
                "generation_limit",
                "generations_used",
                "reserved_generations",
                "updated_at",
            ]
        )
        claimed = ActivationCode.objects.filter(
            pk=activation_code.pk,
            redeemed_at__isnull=True,
            revoked_at__isnull=True,
        ).update(redeemed_by=user, redeemed_at=now)
        if claimed != 1:
            raise ActivationCodeUnavailable("该激活码已经使用或已作废。")
        activation_code.redeemed_by = user
        activation_code.redeemed_at = now

    return ActivationResult(
        activation_code=activation_code,
        entitlement=entitlement,
        message=message,
    )
