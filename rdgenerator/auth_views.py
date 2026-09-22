from datetime import timedelta
from functools import wraps
import ipaddress
import secrets
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model, login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LogoutView
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms import (
    ActivationCodeForm,
    ActivationCodeGenerationForm,
    ManagedSetPasswordForm,
    ManagedUserCreationForm,
    ManagedUserEditForm,
    PublicRegistrationForm,
    RegistrationEmailCodeRequestForm,
)
from .email_verification import (
    EmailVerificationDeliveryError,
    EmailVerificationError,
    EmailVerificationRateLimited,
    issue_registration_email_code,
)
from .membership import (
    ActivationCodeError,
    generate_activation_codes,
    redeem_activation_code,
)
from .models import ActivationCode, GithubRun, UserEntitlement


User = get_user_model()
ACTIVATION_GENERATION_TOKENS_SESSION_KEY = "activation_generation_tokens"
BUILD_STATUS_CHOICES = (
    ("queued", "排队中"),
    ("starting", "准备中"),
    ("in_progress", "构建中"),
    ("artifacts_pending", "等待文件"),
    ("success", "构建成功"),
    ("failure", "构建失败"),
    ("artifact_incomplete", "文件不完整"),
    ("dispatch_failed", "提交失败"),
    ("cancelled", "已取消"),
    ("timed_out", "已超时"),
    ("skipped", "已跳过"),
    ("action_required", "需要处理"),
    ("completed", "已完成"),
    ("finished", "已结束"),
)
BUILD_PLATFORM_CHOICES = (
    ("windows", "Windows 64 位"),
    ("windows-x86", "Windows 32 位"),
    ("linux", "Linux"),
    ("android", "Android"),
    ("macos", "macOS"),
)
BUILD_PERIOD_CHOICES = (
    ("24h", "最近 24 小时", 1),
    ("7d", "最近 7 天", 7),
    ("30d", "最近 30 天", 30),
    ("90d", "最近 90 天", 90),
)
BUILD_FAILED_STATUSES = {
    "failure",
    "artifact_incomplete",
    "dispatch_failed",
    "cancelled",
    "timed_out",
    "skipped",
    "action_required",
}
BUILD_TERMINAL_STATUSES = BUILD_FAILED_STATUSES | {"success", "completed", "finished"}


def staff_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapped


def _issue_activation_generation_token(request):
    token = secrets.token_urlsafe(24)
    tokens = list(request.session.get(ACTIVATION_GENERATION_TOKENS_SESSION_KEY, []))
    tokens.append(token)
    request.session[ACTIVATION_GENERATION_TOKENS_SESSION_KEY] = tokens[-10:]
    return token


def _consume_activation_generation_token(request, submitted_token):
    tokens = list(request.session.get(ACTIVATION_GENERATION_TOKENS_SESSION_KEY, []))
    matched_index = next(
        (
            index
            for index, token in enumerate(tokens)
            if submitted_token and secrets.compare_digest(token, submitted_token)
        ),
        None,
    )
    if matched_index is None:
        return False
    del tokens[matched_index]
    request.session[ACTIVATION_GENERATION_TOKENS_SESSION_KEY] = tokens
    return True


class PostOnlyLogoutView(LogoutView):
    http_method_names = ["post", "options"]


def _registration_client_ip(request):
    raw_ip = request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR")
    try:
        return str(ipaddress.ip_address((raw_ip or "").strip()))
    except ValueError:
        return None


@sensitive_post_parameters("email", "verification_code", "password1", "password2")
@never_cache
@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return redirect("generator")
    if request.method == "POST":
        form = PublicRegistrationForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
            except EmailVerificationError as exc:
                form.add_error("verification_code", str(exc))
            else:
                login(request, user)
                messages.success(request, "注册成功。请填写激活码开通会员。")
                return redirect("generator")
    else:
        form = PublicRegistrationForm()
    return render(request, "registration/register.html", {"form": form})


@sensitive_post_parameters("email")
@never_cache
@require_POST
def send_registration_email_code(request):
    if request.user.is_authenticated:
        return JsonResponse(
            {"ok": False, "message": "当前账号已经登录。"},
            status=400,
        )

    form = RegistrationEmailCodeRequestForm(request.POST)
    if not form.is_valid():
        message = next(
            (str(error) for errors in form.errors.values() for error in errors),
            "请输入有效的邮箱地址。",
        )
        return JsonResponse({"ok": False, "message": message}, status=400)

    try:
        result = issue_registration_email_code(
            email=form.cleaned_data["email"],
            request_ip=_registration_client_ip(request),
        )
    except EmailVerificationRateLimited as exc:
        return JsonResponse(
            {
                "ok": False,
                "message": str(exc),
                "retry_after": exc.retry_after,
            },
            status=429,
        )
    except EmailVerificationDeliveryError as exc:
        return JsonResponse(
            {"ok": False, "message": str(exc)},
            status=503,
        )

    return JsonResponse(
        {
            "ok": True,
            "message": "验证码已发送，请查看邮箱。",
            "retry_after": result.resend_after,
        }
    )


@sensitive_post_parameters("code")
@never_cache
@login_required
@require_POST
def activate_membership(request):
    if request.user.is_staff or request.user.is_superuser:
        messages.info(request, "管理员账号无需激活会员。")
        return redirect("generator")

    form = ActivationCodeForm(request.POST)
    if not form.is_valid():
        first_error = next(
            (str(error) for errors in form.errors.values() for error in errors),
            "请输入有效的激活码。",
        )
        messages.error(request, first_error)
        return redirect("generator")

    try:
        result = redeem_activation_code(
            user=request.user,
            raw_code=form.cleaned_data["code"],
        )
    except ActivationCodeError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, result.message)
    return redirect("generator")


def _managed_user_or_403(actor, user_id):
    user = get_object_or_404(User, pk=user_id)
    if user.is_superuser and not actor.is_superuser:
        raise PermissionDenied
    if user.is_staff and not actor.is_superuser and user.pk != actor.pk:
        raise PermissionDenied
    return user


@staff_required
def user_list(request):
    users = User.objects.order_by("username")
    if not request.user.is_superuser:
        users = users.filter(Q(is_staff=False) | Q(pk=request.user.pk))
    users = list(users.select_related("entitlement"))
    missing_entitlements = [
        UserEntitlement(user_id=user.pk)
        for user in users
        if not hasattr(user, "entitlement")
    ]
    if missing_entitlements:
        UserEntitlement.objects.bulk_create(missing_entitlements, ignore_conflicts=True)
        users = list(
            User.objects.filter(pk__in=[user.pk for user in users])
            .order_by("username")
            .select_related("entitlement")
        )
    return render(request, "users/user_list.html", {"users": users})


@never_cache
@login_required
@require_GET
def build_record_list(request):
    scoped_runs = GithubRun.objects.select_related("owner").order_by(
        "-created_at", "-pk"
    )
    if not request.user.is_staff:
        scoped_runs = scoped_runs.filter(owner=request.user)

    summary = {
        "total": scoped_runs.count(),
        "success": scoped_runs.filter(status="success").count(),
        "active": scoped_runs.exclude(status__in=BUILD_TERMINAL_STATUSES).count(),
        "failed": scoped_runs.filter(status__in=BUILD_FAILED_STATUSES).count(),
    }

    runs = scoped_runs
    query = request.GET.get("q", "").strip()[:100]
    selected_status = request.GET.get("status", "").strip()
    selected_platform = request.GET.get("platform", "").strip()
    selected_period = request.GET.get("period", "").strip()
    selected_owner = request.GET.get("owner", "").strip() if request.user.is_staff else ""

    valid_statuses = {value for value, _label in BUILD_STATUS_CHOICES}
    valid_platforms = {value for value, _label in BUILD_PLATFORM_CHOICES}
    period_days = {value: days for value, _label, days in BUILD_PERIOD_CHOICES}

    if query:
        query_filter = (
            Q(uuid__icontains=query)
            | Q(artifact_stem__icontains=query)
            | Q(owner__username__icontains=query)
        )
        if query.isdigit():
            query_filter |= Q(github_run_id=int(query))
        runs = runs.filter(query_filter)
    if selected_status in valid_statuses:
        runs = runs.filter(status=selected_status)
    else:
        selected_status = ""
    if selected_platform in valid_platforms:
        runs = runs.filter(platform=selected_platform)
    else:
        selected_platform = ""
    if selected_period in period_days:
        runs = runs.filter(
            created_at__gte=timezone.now() - timedelta(days=period_days[selected_period])
        )
    else:
        selected_period = ""

    filter_users = User.objects.none()
    if request.user.is_staff:
        filter_users = User.objects.order_by("username").only("id", "username")
        if selected_owner == "deleted":
            runs = runs.filter(owner__isnull=True)
        elif selected_owner.isdigit() and filter_users.filter(pk=int(selected_owner)).exists():
            runs = runs.filter(owner_id=int(selected_owner))
        else:
            selected_owner = ""

    page_obj = Paginator(runs, 30).get_page(request.GET.get("page"))
    status_labels = dict(BUILD_STATUS_CHOICES)
    platform_labels = dict(BUILD_PLATFORM_CHOICES)
    for build_run in page_obj.object_list:
        build_run.status_label = status_labels.get(
            build_run.status,
            build_run.status or "未知状态",
        )
        if build_run.status == "success":
            build_run.status_tone = "success"
        elif build_run.status == "action_required":
            build_run.status_tone = "warning"
        elif build_run.status in BUILD_FAILED_STATUSES:
            build_run.status_tone = "danger"
        else:
            build_run.status_tone = "pending"
        build_run.platform_label = platform_labels.get(
            build_run.platform,
            build_run.platform or "未记录",
        )

    filter_values = [
        ("q", query),
        ("owner", selected_owner),
        ("status", selected_status),
        ("platform", selected_platform),
        ("period", selected_period),
    ]
    filter_query = urlencode([(key, value) for key, value in filter_values if value])

    return render(
        request,
        "users/build_record_list.html",
        {
            "page_obj": page_obj,
            "summary": summary,
            "query": query,
            "filter_users": filter_users,
            "status_choices": BUILD_STATUS_CHOICES,
            "platform_choices": BUILD_PLATFORM_CHOICES,
            "period_choices": BUILD_PERIOD_CHOICES,
            "selected_owner": selected_owner,
            "selected_status": selected_status,
            "selected_platform": selected_platform,
            "selected_period": selected_period,
            "filter_query": filter_query,
            "now": timezone.now(),
        },
    )


@never_cache
@staff_required
@require_http_methods(["GET", "POST"])
def activation_code_list(request):
    generated_codes = []
    if request.method == "POST":
        generation_form = ActivationCodeGenerationForm(request.POST)
        token_valid = _consume_activation_generation_token(
            request,
            request.POST.get("request_token", ""),
        )
        form_valid = generation_form.is_valid()
        if token_valid and form_valid:
            generated_codes = generate_activation_codes(
                plan=generation_form.cleaned_data["plan"],
                quantity=generation_form.cleaned_data["quantity"],
                batch_label=generation_form.cleaned_data["batch_label"],
                created_by=request.user,
            )
            messages.success(
                request,
                f"已生成 {len(generated_codes)} 个激活码，请立即复制保存。",
            )
            generation_form = ActivationCodeGenerationForm(
                initial={"plan": generation_form.cleaned_data["plan"], "quantity": 1}
            )
        elif not token_valid:
            generation_form.add_error(
                None,
                "该生成请求已处理或页面已过期，请重新填写后提交。",
            )
    else:
        generation_form = ActivationCodeGenerationForm()
    next_request_token = _issue_activation_generation_token(request)
    if generation_form.is_bound:
        refreshed_data = generation_form.data.copy()
        refreshed_data["request_token"] = next_request_token
        token_error = generation_form.non_field_errors() if request.method == "POST" else []
        generation_form = ActivationCodeGenerationForm(refreshed_data)
        generation_form.is_valid()
        for error in token_error:
            generation_form.add_error(None, error)
    else:
        generation_form.initial["request_token"] = next_request_token

    codes = ActivationCode.objects.select_related(
        "created_by", "redeemed_by", "revoked_by"
    )
    selected_plan = request.GET.get("plan", "").strip()
    selected_status = request.GET.get("status", "").strip()
    query = request.GET.get("q", "").strip()
    valid_plans = {value for value, _label in ActivationCode.PLAN_CHOICES}
    if selected_plan in valid_plans:
        codes = codes.filter(plan=selected_plan)
    else:
        selected_plan = ""
    if selected_status == "unused":
        codes = codes.filter(redeemed_at__isnull=True, revoked_at__isnull=True)
    elif selected_status == "redeemed":
        codes = codes.filter(redeemed_at__isnull=False)
    elif selected_status == "revoked":
        codes = codes.filter(revoked_at__isnull=False, redeemed_at__isnull=True)
    else:
        selected_status = ""
    if query:
        codes = codes.filter(
            Q(batch_label__icontains=query)
            | Q(code_hint__iexact=query[-4:])
            | Q(redeemed_by__username__icontains=query)
        )

    page_obj = Paginator(codes, 50).get_page(request.GET.get("page"))
    return render(
        request,
        "users/activation_code_list.html",
        {
            "generation_form": generation_form,
            "generated_codes": generated_codes,
            "page_obj": page_obj,
            "plan_choices": ActivationCode.PLAN_CHOICES,
            "selected_plan": selected_plan,
            "selected_status": selected_status,
            "query": query,
        },
    )


@staff_required
@require_POST
def activation_code_revoke(request, code_id):
    activation_code = get_object_or_404(ActivationCode, pk=code_id)
    if activation_code.redeemed_at:
        messages.error(request, "已使用的激活码不能作废。")
    elif activation_code.revoked_at:
        messages.info(request, "该激活码已经作废。")
    else:
        updated = ActivationCode.objects.filter(
            pk=activation_code.pk,
            redeemed_at__isnull=True,
            revoked_at__isnull=True,
        ).update(revoked_at=timezone.now(), revoked_by=request.user)
        if updated:
            messages.success(request, "激活码已作废。")
        else:
            messages.error(request, "激活码状态已变化，请刷新后重试。")
    return redirect("users:activation_codes")


@sensitive_post_parameters("password1", "password2")
@staff_required
@require_http_methods(["GET", "POST"])
def user_create(request):
    if request.method == "POST":
        form = ManagedUserCreationForm(request.POST, actor=request.user)
        if form.is_valid():
            user = form.save()
            messages.success(request, f"账号 {user.username} 已创建。")
            return redirect("users:list")
    else:
        form = ManagedUserCreationForm(actor=request.user)
    return render(
        request,
        "users/user_form.html",
        {"form": form, "page_title": "创建账号", "submit_label": "创建账号"},
    )


@staff_required
@require_http_methods(["GET", "POST"])
def user_edit(request, user_id):
    user = _managed_user_or_403(request.user, user_id)
    if request.method == "POST":
        form = ManagedUserEditForm(request.POST, instance=user, actor=request.user)
        if form.is_valid():
            user = form.save()
            messages.success(request, f"账号 {user.username} 已更新。")
            return redirect("users:list")
    else:
        form = ManagedUserEditForm(instance=user, actor=request.user)
    return render(
        request,
        "users/user_form.html",
        {
            "form": form,
            "managed_user": user,
            "page_title": f"编辑 {user.username}",
            "submit_label": "保存更改",
        },
    )


@sensitive_post_parameters("new_password1", "new_password2")
@staff_required
@require_http_methods(["GET", "POST"])
def user_password(request, user_id):
    user = _managed_user_or_403(request.user, user_id)
    if request.method == "POST":
        form = ManagedSetPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            if user.pk == request.user.pk:
                update_session_auth_hash(request, user)
            messages.success(request, f"账号 {user.username} 的密码已重置。")
            return redirect("users:list")
    else:
        form = ManagedSetPasswordForm(user)
    return render(
        request,
        "users/password_form.html",
        {"form": form, "managed_user": user},
    )


@staff_required
@require_POST
def user_toggle(request, user_id):
    user = _managed_user_or_403(request.user, user_id)
    if user.pk == request.user.pk:
        messages.error(request, "不能停用当前登录账号。")
        return redirect("users:list")
    if user.is_superuser and user.is_active:
        has_another_superuser = User.objects.filter(
            is_superuser=True,
            is_active=True,
        ).exclude(pk=user.pk).exists()
        if not has_another_superuser:
            messages.error(request, "不能停用最后一个可用的超级管理员。")
            return redirect("users:list")
    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])
    state = "启用" if user.is_active else "停用"
    messages.success(request, f"账号 {user.username} 已{state}。")
    return redirect(reverse("users:list"))


@staff_required
@require_http_methods(["GET", "POST"])
def user_delete(request, user_id):
    user = _managed_user_or_403(request.user, user_id)
    if user.pk == request.user.pk:
        messages.error(request, "不能删除当前登录账号。")
        return redirect("users:list")
    if user.is_superuser:
        has_another_superuser = User.objects.filter(
            is_superuser=True,
        ).exclude(pk=user.pk).exists()
        if not has_another_superuser:
            messages.error(request, "不能删除系统中的最后一个超级管理员。")
            return redirect("users:list")

    if request.method == "POST":
        username = user.username
        user.delete()
        messages.success(request, f"账号 {username} 已删除。")
        return redirect("users:list")

    return render(
        request,
        "users/user_confirm_delete.html",
        {"managed_user": user},
    )


@login_required
def password_changed(request):
    return render(request, "accounts/password_change_done.html")
