import uuid

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views import View

from apps.users.decorators import VerifiedUserRequiredMixin

from .choices import MembershipRole, MembershipStatus
from .context import get_user_merchant_memberships, set_active_merchant
from .exceptions import InvalidMerchantSelectionError
from .forms import MerchantOnboardingForm
from .models import MerchantMembership
from .services import create_merchant


class SwitchMerchantView(LoginRequiredMixin, View):
    """
    POST-only, CSRF-protected endpoint for switching the user's active merchant organization.

    Security & Invariants:
    - Rejects GET with 405 Method Not Allowed.
    - Requires authenticated user.
    - Validates target merchant membership server-side.
    - Modifies session state ONLY upon successful verification.
    - On failure, preserves the previous session selection intact.
    """

    http_method_names = ["post"]

    def post(self, request: HttpRequest) -> HttpResponse:
        target_merchant_id = request.POST.get("merchant_id", "").strip()
        redirect_to = request.POST.get("next") or request.GET.get("next") or "core:index"

        # Security check: ensure redirect URL is safe to prevent open redirect vulnerabilities
        if not url_has_allowed_host_and_scheme(
            url=redirect_to,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            redirect_to = "core:index"

        if not target_merchant_id:
            messages.error(request, _("Please select a valid merchant organization."))
            return redirect(redirect_to)

        try:
            membership = set_active_merchant(request, target_merchant_id)
            messages.success(
                request,
                _("Switched active organization to %(name)s.") % {"name": membership.merchant.name},
            )
        except InvalidMerchantSelectionError:
            messages.error(
                request,
                _("You do not have active access to the selected merchant organization."),
            )

        return redirect(redirect_to)


class MerchantOnboardingView(LoginRequiredMixin, VerifiedUserRequiredMixin, View):
    """
    Onboarding view for creating a new merchant organization.

    Security & Invariants:
    - Requires authenticated, active, and verified user account.
    - CSRF protected.
    - Uses session-backed submission tokens to mitigate accidental double submissions.
    - Calls atomic create_merchant() service establishing PENDING status and ACTIVE OWNER role.
    - Sets the newly created merchant as the active context upon success.
    - Never re-runs merchant creation if session context assignment encounters an issue.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        form_token = str(uuid.uuid4())
        request.session["onboarding_form_token"] = form_token
        form = MerchantOnboardingForm(
            initial={
                "email": request.user.email,
                "form_token": form_token,
            }
        )
        return render(request, "merchants/onboarding.html", {"form": form})

    def post(self, request: HttpRequest) -> HttpResponse:
        form = MerchantOnboardingForm(request.POST)
        submitted_token = request.POST.get("form_token", "").strip()
        session_token = request.session.get("onboarding_form_token")

        # Accidental duplicate submission prevention check
        if not session_token or submitted_token != session_token:
            recent_merchant_id = request.session.get("onboarding_merchant_id")
            if recent_merchant_id:
                # Safe recovery: redirect to recently onboarded confirmation
                return redirect(
                    "merchants:onboarding_success",
                    merchant_id=recent_merchant_id,
                )
            fresh_token = str(uuid.uuid4())
            request.session["onboarding_form_token"] = fresh_token
            messages.error(
                request,
                _(
                    "This registration submission has already been processed or expired. "
                    "Please review and try again."
                ),
            )
            form = MerchantOnboardingForm(request.POST, initial={"form_token": fresh_token})
            return render(request, "merchants/onboarding.html", {"form": form})

        # Token matches: consume it immediately before mutation
        del request.session["onboarding_form_token"]
        request.session.modified = True

        if not form.is_valid():
            # Form invalid: restore token so user can correct input and re-submit
            request.session["onboarding_form_token"] = submitted_token
            return render(request, "merchants/onboarding.html", {"form": form})

        try:
            merchant, owner_membership = create_merchant(
                owner_user=request.user,
                name=form.cleaned_data["name"],
                email=form.cleaned_data["email"],
                contact_number=form.cleaned_data["contact_number"],
                address=form.cleaned_data["address"],
                city=form.cleaned_data["city"],
                state=form.cleaned_data["state"],
                pin_code=form.cleaned_data["pin_code"],
                business_type=form.cleaned_data["business_type"],
                description=form.cleaned_data["description"],
            )
        except Exception:
            request.session["onboarding_form_token"] = submitted_token
            messages.error(
                request,
                _("An error occurred while creating your merchant organization. Please try again."),
            )
            return render(request, "merchants/onboarding.html", {"form": form})

        # Store created merchant id in session for onboarding confirmation verification
        request.session["onboarding_merchant_id"] = str(merchant.id)
        request.session.modified = True

        # Context establishment (safe recovery: merchant was already committed)
        try:
            set_active_merchant(request, merchant.id)
        except Exception:
            messages.warning(
                request,
                _(
                    "Your business was successfully registered, but could not be automatically "
                    "selected as the active session. You can switch to it from the organization switcher."
                ),
            )

        messages.success(
            request,
            _("Business organization '%(name)s' registered successfully.")
            % {"name": merchant.name},
        )
        return redirect("merchants:onboarding_success", merchant_id=merchant.id)


class MerchantOnboardingSuccessView(LoginRequiredMixin, VerifiedUserRequiredMixin, View):
    """
    Displays the confirmation screen for a newly registered merchant.

    Security & Invariants:
    - Verifies that merchant_id matches the session onboarding record.
    - Verifies that the current user holds an ACTIVE OWNER membership in this merchant.
    - Prevents URL manipulation or IDOR to inspect other merchants' onboarding confirmations.
    - Clearly displays PENDING status and explains activation requirements.
    """

    def get(self, request: HttpRequest, merchant_id: uuid.UUID) -> HttpResponse:
        session_onboarding_id = request.session.get("onboarding_merchant_id")
        if not session_onboarding_id or str(merchant_id) != session_onboarding_id:
            raise PermissionDenied(
                _("You do not have permission to view this onboarding confirmation.")
            )

        membership = (
            MerchantMembership.objects.select_related("merchant")
            .filter(
                user=request.user,
                merchant_id=merchant_id,
                role=MembershipRole.OWNER,
                status=MembershipStatus.ACTIVE,
            )
            .first()
        )
        if not membership:
            raise PermissionDenied(
                _("You do not hold an active owner membership in this merchant organization.")
            )

        return render(
            request,
            "merchants/onboarding_success.html",
            {
                "merchant": membership.merchant,
                "membership": membership,
            },
        )


class MerchantDashboardView(LoginRequiredMixin, VerifiedUserRequiredMixin, View):
    """
    Main workspace landing view for the active merchant organization.

    Access & Lifecycle Rules:
    - User must be authenticated and email-verified.
    - Resolves active memberships via get_user_merchant_memberships(request.user).
    - If 0 active memberships: redirects to 'merchants:onboarding'.
    - If >1 active memberships and request.merchant is None:
        renders 'merchants/dashboard_select.html' to let user choose organization.
    - If valid active merchant established (either auto-resolved for 1 membership,
      or resolved from session):
        renders 'merchants/dashboard_overview.html'.
    - Checks store existence defensively via hasattr/getattr.
    - Respects merchant lifecycle permissions and uses neutral suspension messaging.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        active_memberships = get_user_merchant_memberships(request.user)
        membership_count = active_memberships.count()

        # 1. User with no merchant memberships -> redirect to onboarding
        if membership_count == 0:
            messages.info(
                request,
                _(
                    "You do not belong to any business organization yet. "
                    "Please register your business to access the workspace."
                ),
            )
            return redirect("merchants:onboarding")

        # 2. User with multiple memberships and no active selection -> show organization selector
        if not request.merchant or not request.membership:
            return render(
                request,
                "merchants/dashboard_select.html",
                {
                    "memberships": active_memberships,
                },
            )

        # 3. Valid merchant context established
        merchant = request.merchant
        membership = request.membership

        # Resolve store safely
        store = getattr(merchant, "store", None)
        if store is not None:
            try:
                bool(store.pk)
            except Exception:
                store = None

        return render(
            request,
            "merchants/dashboard_overview.html",
            {
                "merchant": merchant,
                "membership": membership,
                "store": store,
                "user_memberships": active_memberships,
                "has_multiple_merchants": membership_count > 1,
            },
        )
